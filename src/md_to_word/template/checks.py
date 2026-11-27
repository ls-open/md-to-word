"""格式文件的必填项与联动校验。"""

from __future__ import annotations

import logging
import re

from lxml import etree

from md_to_word.i18n import style_name as _style_name, t
from md_to_word.spec.constants import ROW_NAME_EN, STYLE_MAP, W
from md_to_word.template.core import _find_style, logger
from md_to_word.utils.skill_utils import TOC_MARKER_RE

# ── 所有文档无条件必填的基础样式骨架 ──
# 无论导出普通文档/报告还是学术论文，标题、一级章节与正文三态（Body Text / First Paragraph / Normal）
# 都是必现基础段落；其余结构（二级及以上标题、摘要、关键词、图表、参考文献、目录、引用块）
# 均通过下方 STRUCT_TRIGGERS 按「稿件实际用到即必填」精确拦截。
REQUIRED_STYLES = {
    'Title': '文档标题',
    'Heading 1': '一级标题',
    'Body Text': '正文',
    'First Paragraph': '首段',
    'Normal': '普通',
}

# ── **条件必填**：写了内容就必须给样式行 ──
# 页眉/页脚本身可有可无（不写＝不加，不算错）；但写了「页眉内容：」却不给「页眉：」
# 样式行，页眉就会套用底模默认字体——正是要防的那种静默错误。
# 值是（中文行名, 示例行的消息 key）：示例得按读者的语言给，写在词表里，测试里过一遍解析
CONDITIONAL_STYLE_ROWS = {
    'Header': ('页眉', 'template.example.header'),
    'Footer': ('页脚', 'template.example.footer'),
}

# ── **条件成套必填（学位论文目录）** ──
# 无目录时不强制写；一旦声明了目录相关样式中的任意一个，
# 目录标题 + 一/二/三级目录条目必须成套写齐，防止漏写某一级导致该级退回 Word 默认缩进。
# 三级是绝大多数规范的要求，故「成套」的最小集合到三级为止；四级、五级是可选延伸，
# 声明了就要连着声明（见 TOC_EXTRA_LEVELS 的连贯性检查）——中间空一级，那一级会静默
# 退回 Word 默认缩进。
TOC_STYLE_GROUP = {
    'TOC Heading': '目录标题',
    'TOC 1': '目录一级',
    'TOC 2': '目录二级',
    'TOC 3': '目录三级',
}

# 可选的更深一级：第 n 级写了，第 n-1 级必须也写
TOC_EXTRA_LEVELS = {4: ('TOC 4', '目录四级'), 5: ('TOC 5', '目录五级')}

# ── **稿件结构 → 必须声明的样式** ──
# 与 REQUIRED_STYLES（基础骨架无条件必填）互补：普通文档未必有摘要/关键词/参考文献/图表，
# 不必强求纯文档也声明全套学术论文样式；但**稿件里真出现了**这些结构，要求文件就必须
# 显式定义，否则静默回退到底模默认样式。
STRUCT_TRIGGERS = [
    (re.compile(r'^##\s+\S'), 'gate.feat.heading2', [('二级标题', 'Heading 2')]),
    (re.compile(r'^###\s+\S'), 'gate.feat.heading3', [('三级标题', 'Heading 3')]),
    (re.compile(r'^####\s+\S'), 'gate.feat.heading4', [('四级标题', 'Heading 4')]),
    (re.compile(r'^#####\s+\S'), 'gate.feat.heading5', [('五级标题', 'Heading 5')]),
    (re.compile(r'^######\s+\S'), 'gate.feat.heading6', [('六级标题', 'Heading 6')]),
    (TOC_MARKER_RE, 'gate.feat.toc',
     [(cn, en) for en, cn in TOC_STYLE_GROUP.items()]),
    (re.compile(r'^>\s+\S'), 'gate.feat.block_text', [('引用块', 'Block Text')]),
    (re.compile(r'custom-style=(["\'])Abstract Title\1'), 'gate.feat.abstract_title', [('摘要标题', 'Abstract Title')]),
    (re.compile(r'custom-style=(["\'])Abstract\1'), 'gate.feat.abstract', [('摘要', 'Abstract')]),
    (re.compile(r'custom-style=(["\'])Keywords\1'), 'gate.feat.keywords', [('关键词', 'Keywords')]),
    (re.compile(r'custom-style=(["\'])References Title\1'), 'gate.feat.references_title', [('参考文献标题', 'References Title')]),
    (re.compile(r'(?:::\s*\{#refs\}|custom-style=(["\'])Bibliography\1)'), 'gate.feat.bibliography', [('参考文献', 'Bibliography')]),
    (re.compile(r'!\[[^\]]*\]\([^)]+\)'), 'gate.feat.image', [('图', 'Captioned Figure'), ('图片题注', 'Image Caption')]),
    (re.compile(r'custom-style=(["\'])Table Caption\1'), 'gate.feat.table_caption', [('表格题注', 'Table Caption')]),
    (re.compile(r'custom-style=(["\'])Table Note\1'), 'gate.feat.table_note', [('表注', 'Table Note')]),
    (re.compile(r'^\s*\|.*\|'), 'gate.feat.markdown_table', [
        ('紧凑', 'Compact'),
        ('表格', '__ROW_table__'),
        ('表头', '__ROW_table_header__'),
    ]),
]


def missing_styles_for_body(
    masked_body: str, declared: set, start_line: int = 1, lang: str = "zh"
) -> list:
    """稿件正文用到的结构 → 要求文件漏声明的样式或配置行。

    `masked_body` 是**已掩码代码块**的正文（`skill_utils.mask_code_fences`）——方法学论文
    常在代码块里演示语法，那里的 `>`、`###` 不是稿件结构。
    返回 [(行号, 结构描述, 中文写法, Word 样式名)]，空列表 = 都声明了。
    结构描述按 `lang` 取词（`gate.feat.*`）：报错里说「二级标题 (##)」还是
    「level-2 heading (##)」，跟读者的稿子走。
    """
    issues, reported = [], set()
    for i, line in enumerate(masked_body.split('\n'), start_line):
        for pat, feat_key, styles in STRUCT_TRIGGERS:
            if not pat.search(line):
                continue
            for cn, en in styles:
                if en not in declared and (feat_key, en) not in reported:
                    reported.add((feat_key, en))
                    issues.append((i, t(feat_key, lang), cn, en))
    return issues

_PARA = ['font_name', 'font_size', 'alignment', 'line_spacing', 'space_before', 'space_after']
# 「字距」是可选的字符级属性，**不进下面的必填表**——列进去就等于逼每个样式行都写它，
# 现有格式要求文件会全部判为缺字段。
_TITLE = _PARA + ['bold', 'italic']   # 标题类：加粗/倾斜状态必须显式，否则继承底模设定

REQUIRED_FIELDS_BY_STYLE = {
    k: v + ['indent'] for k, v in {
        'Title': _TITLE,
        'Subtitle': _TITLE,
        'Heading 1': _TITLE,
        'Heading 2': _TITLE,
        'Heading 3': _TITLE,
        'Heading 4': _TITLE,
        'Heading 5': _TITLE,
        'Heading 6': _TITLE,
        'Abstract Title': _TITLE,
        'References Title': _TITLE,
        'TOC Heading': _TITLE,
        # 目录条目同样是 basedOn Normal，不显式写缩进就会被正文的 2 字符带跑
        'TOC 1': _PARA,
        'TOC 2': _PARA,
        'TOC 3': _PARA,
        'TOC 4': _PARA,
        'TOC 5': _PARA,
        'Abstract': _PARA,
        'Keywords': _PARA,
        'Table Caption': _PARA,
        'Table Note': _PARA,
        'Image Caption': _PARA,
        'Body Text': _PARA,
        'First Paragraph': _PARA,
        'Compact': _PARA,
        'Normal': _PARA,
        'Bibliography': _PARA,
        'Block Text': _PARA,
        'Footnote Text': _PARA,
        'Author': _PARA,
        'Date': _PARA,
        'Header': _PARA,
        'Footer': _PARA,
        # 图片段落不带文字，字体字号无意义；要紧的只有缩进 0 与居中
        'Captioned Figure': ['alignment', 'line_spacing', 'space_before', 'space_after'],
    }.items()
}
# 「缩进」为什么每个契约样式都必填：不是每个样式都需要缩进，而是**不写就会继承**。
# 正文写「首行缩进2字符」之后 Normal 就带上了 firstLineChars=200，凡 basedOn Normal
# 又没自己写 w:ind 的样式都会跟着缩进 2 字符。图片段落、表格单元格这类一行就结束的，
# 被顶右 2 字符再叠加居中会顶出右边界——肉眼看是"图片没居中"，实则是继承来的缩进。

# 字段名与「该写什么」都在 `i18n` 的词表里（`template.field.*` / `template.hint.*`）：
# 英文那栏的示例是**能直接放进样式行**的片段，测试里逐个过 `parse_format`。
FIELD_KEYS = (
    'font_name', 'font_size', 'alignment', 'line_spacing',
    'space_before', 'space_after', 'indent', 'bold', 'italic',
)


def _row_label(row: str, lang: str) -> str:
    """要求文件「行名」的英文回显：先查正典名（页眉 → Header），再查表格配置行（表格 → Table）。"""
    return row if lang != "en" else (STYLE_MAP.get(row) or ROW_NAME_EN.get(row) or row)


_LINKED_SECTION_TITLES = ('Abstract Title', 'References Title')
_STYLEREF_STYLE_NAMES = {k.lower(): v for k, v in STYLE_MAP.items()}


def _has_toc_styles(req_by_style: dict) -> bool:
    return any(s in req_by_style for s in TOC_STYLE_GROUP) or any(
        s in req_by_style for s in ('TOC 4', 'TOC 5')
    )


def _has_heading_styleref(spec) -> bool:
    return any(
        name.strip().lower().startswith('heading')
        for name in collect_styleref_names(spec)
    )


def _check_linkage_fields(spec, lang: str = "zh") -> list[str]:
    """联动必填校验：
    - 声明目录样式组时，Abstract Title / References Title 必须显式写明 join-toc 或 no-toc；
    - 页眉/页脚含 {样式标题:Heading ...} 时，Abstract Title / References Title 必须显式写明 join-header 或 no-header；
    - 禁止不入目录 + 加入页眉（标准 Word TOC \\o \\u 物理限制）。
    """
    req_by_style = {r['style_name']: r for r in spec.styles}
    has_toc = _has_toc_styles(req_by_style)
    has_header = _has_heading_styleref(spec)
    errors: list[str] = []
    # 页眉/页脚里的 {样式标题:X} 必须是 Word 样式名；写成中文别名或笔误时，
    # Word 会直接显示 `Error! No text of specified style`，预检先拦下来。
    for name in collect_styleref_names(spec):
        canonical = _STYLEREF_STYLE_NAMES.get(name.lower())
        if canonical == name:
            continue
        errors.append(t('template.linkage.unknown_styleref', lang,
                        name=name, canonical=canonical or 'Heading 1'))
    for style_name in _LINKED_SECTION_TITLES:
        req = req_by_style.get(style_name)
        if req is None:
            continue
        alias = req.get('alias') or _style_name(style_name, lang)
        if req.get('join_toc') is False and req.get('join_header') is True:
            errors.append(t('template.linkage.conflict_no_toc_join_header', lang,
                            alias=alias, style=style_name))
        if has_toc and 'join_toc' not in req:
            errors.append(t('template.linkage.join_toc_missing', lang,
                            alias=alias, style=style_name))
        if has_header and 'join_header' not in req:
            errors.append(t('template.linkage.join_header_missing', lang,
                            alias=alias, style=style_name))
    return errors


def _style_line_numbers(fmt_content: str) -> dict[str, int]:
    """样式名 → 它在格式文件里的行号。

    缺字段时只说样式名，用户还得自己在一份几十行的文件里找那一行；而「不认识属性词」
    那条早就报行号了。判据一样，位置也得一样。
    """
    lines: dict[str, int] = {}
    for i, line in enumerate(fmt_content.split("\n"), 1):
        m = re.match(r"^\s*([^#:：\s][^:：]*?)\s*[：:]", line)
        if m:
            lines.setdefault(m.group(1).strip(), i)
    return lines


def _check_required_fields(
    spec, lang: str = "zh", fmt_content: str | None = None,
    sink: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """校验必填项是否齐备：必填样式 / 样式的必填字段 / 条件成套必填行 / 联动必填。

    返回 `(是否有错, 联动错误列表)`：联动错误**不回显**，由调用方拼进异常；不要在这里
    或调用方再打一次日志，否则同一句会打印两遍。

    `fmt_content` 给得出时，缺字段的那条会带上它在格式文件里的行号。
    `sink` 给得出时，同一条消息也追加进去，供 `--json` / MCP 把明细带进异常。
    这让调用方不必劫持 logger——并发导出时，劫持会收到别的请求的日志。
    """
    req_by_style = {r['style_name']: r for r in spec.styles}

    missing_required = []   # (别名, 字段)
    missing_styles = []     # (样式名, 别名)
    missing_rows = []       # (行名, 示例的消息 key)

    for style_name, cn_alias in REQUIRED_STYLES.items():
        alias = style_name if lang == "en" else cn_alias
        if style_name not in req_by_style:
            missing_styles.append((style_name, alias))
            continue
        req = req_by_style[style_name]
        required_fields = REQUIRED_FIELDS_BY_STYLE.get(style_name, [])
        for fname in required_fields:
            if fname == 'indent':
                if 'indent' not in req or 'indent_type' not in req:
                    missing_required.append((alias, fname))
            elif fname not in req or req[fname] is None or req[fname] == '':
                missing_required.append((alias, fname))

    # 检查用户声明了但非无条件必选的样式（如二~六级标题、摘要、参考文献、页眉页脚、目录等）：声明了就必须全字段显式覆盖
    for req in spec.styles:
        style_name = req['style_name']
        alias = req.get('alias') or _style_name(style_name, lang)
        if style_name in REQUIRED_FIELDS_BY_STYLE and style_name not in REQUIRED_STYLES:
            required_fields = REQUIRED_FIELDS_BY_STYLE[style_name]
            for fname in required_fields:
                if fname == 'indent':
                    if 'indent' not in req or 'indent_type' not in req:
                        missing_required.append((alias, fname))
                elif fname not in req or req[fname] is None or req[fname] == '':
                    missing_required.append((alias, fname))

    # 条件成套必填 1：若声明了目录样式组中的任意一个，必须成套写齐全部 4 项
    if any(s in req_by_style for s in TOC_STYLE_GROUP):
        for s_name in TOC_STYLE_GROUP:
            if s_name not in req_by_style:
                missing_styles.append((s_name, t('template.style.toc_group', lang,
                                                  name=_style_name(s_name, lang))))

    # 条件成套必填 1b：目录四级/五级可选，但声明了第 n 级就得连着声明到第 n-1 级
    for level, (s_name, _alias) in TOC_EXTRA_LEVELS.items():
        if s_name in req_by_style:
            prev_name, prev_alias = (f'TOC {level - 1}', f'目录{["", "一", "二", "三", "四"][level - 1]}级')
            if prev_name not in req_by_style:
                missing_styles.append((prev_name, t(
                    'template.style.toc_prev_level', lang,
                    name=prev_name if lang == 'en' else prev_alias,
                    this=_style_name(s_name, lang),
                )))

    # 条件成套必填 2：若声明了「表格：」或「表头：」，则表格、表头、紧凑（单元格文字）三者必须配齐
    if spec.table or spec.table_header:
        if not spec.table:
            missing_rows.append(('表格', 'template.example.table'))
        if not spec.table_header:
            missing_rows.append(('表头', 'template.example.table_header'))
        if 'Compact' not in req_by_style:
            missing_styles.append(('Compact', t('template.style.compact_group', lang,
                                                name=_style_name('Compact', lang))))

    # 条件成套必填 3：图片与图片题注成套配齐
    if ('Captioned Figure' in req_by_style) != ('Image Caption' in req_by_style):
        if 'Captioned Figure' not in req_by_style:
            missing_styles.append(('Captioned Figure', t(
                'template.style.figure_group', lang,
                name=_style_name('Captioned Figure', lang))))
        else:
            missing_styles.append(('Image Caption', t(
                'template.style.image_caption_group', lang,
                name=_style_name('Image Caption', lang))))

    # 条件成套必填 4：写了摘要标题须配摘要正文；写了参考文献标题须配参考文献条目
    if 'Abstract Title' in req_by_style and 'Abstract' not in req_by_style:
        missing_styles.append(('Abstract', t('template.style.abstract_group', lang,
                                             name=_style_name('Abstract', lang))))
    if 'References Title' in req_by_style and 'Bibliography' not in req_by_style:
        missing_styles.append(('Bibliography', t('template.style.bibliography_group', lang,
                                                 name=_style_name('Bibliography', lang))))

    # 表头行（firstRow）字段完整性校验
    if spec.table_header:
        for fname in _PARA + ['indent']:
            if fname == 'indent':
                if 'indent' not in spec.table_header or 'indent_type' not in spec.table_header:
                    missing_required.append((_row_label('表头', lang), fname))
            elif (fname not in spec.table_header or spec.table_header[fname] is None
                  or spec.table_header[fname] == ''):
                missing_required.append((_row_label('表头', lang), fname))

    for style_name, (name, example) in CONDITIONAL_STYLE_ROWS.items():
        kind = 'header' if style_name == 'Header' else 'footer'
        written = any(k == kind for k, _ in spec.decor)
        if not written:
            # 分节自己的页眉页脚也算：`正文页眉内容：…` 与全局内容一样，没有样式行
            # 就会套底模自带样式——正是这条规则要防的静默回退。
            written = any(
                (role.header if kind == 'header' else role.footer)
                for role in spec.section_roles.values()
            )
        if written and style_name not in req_by_style:
            missing_rows.append((name, example))

    linkage_errors = _check_linkage_fields(spec, lang)
    has_errors = bool(missing_required or missing_styles or missing_rows or linkage_errors)

    def say(level: int, message: str) -> None:
        logger.log(level, message)
        if sink is not None:
            sink.append(message)

    if missing_styles:
        say(logging.WARNING, t('template.missing_styles_header', lang))
        for style_name, alias in missing_styles:
            say(logging.INFO, t('template.style_item', lang, alias=alias, style=style_name))
        say(logging.INFO, t('template.missing_styles_hint', lang))

    if missing_rows:
        say(logging.WARNING, t('template.missing_rows_header', lang))
        for name, example in missing_rows:
            say(logging.INFO, t('template.row_item', lang, name=_row_label(name, lang),
                                example=t(example, lang)))

    if missing_required:
        say(logging.WARNING, t('template.missing_fields_header', lang))
        style_lines = _style_line_numbers(fmt_content) if fmt_content else {}
        for alias, field in missing_required:
            hint = t(f'template.hint.{field}', lang) if field in FIELD_KEYS else field
            line_no = style_lines.get(alias)
            where = t('template.field_where', lang, line=line_no) if line_no else ""
            say(logging.INFO, t('template.field_item', lang, alias=alias, where=where,
                                field=t(f'template.field.{field}', lang) if field in FIELD_KEYS else field))
            say(logging.INFO, t('template.field_fix', lang, hint=hint))

    if has_errors:
        say(logging.ERROR, t('template.abort', lang))
        say(logging.ERROR, t('template.abort_hint', lang))
    else:
        logger.debug(t('template.check_ok', lang))

    # 联动错误只交回调用方，由它拼进异常；这里不打日志，调用方也别再打。
    return has_errors, linkage_errors


# ══════════════════════════════════════════════════════════════════
#  页眉 / 页脚 / 页码
#
#  参考模板会连同 header/footer 部件与 sectPr 一起带进产物：页面尺寸、页边距、
#  页眉与页脚都取自参考文档。一份模板只取**一个** section 的几何与引用，因此模板
#  必须是单节，奇偶页差异走 evenAndOddHeaders + default/even 两个 headerReference，
#  跨节改页码格式交给正文的 {{< section >}} 标记。
# ══════════════════════════════════════════════════════════════════

def collect_styleref_names(spec):
    """取出所有 {样式标题:X} 里的 X（去重、保序），含节角色自己的页眉页脚。"""
    names = []
    sources = list(spec.decor.values())
    for role in spec.section_roles.values():
        if role.header:
            sources.append(role.header)
        if role.footer:
            sources.append(role.footer)
    for parts in sources:
        for kind, val in parts:
            if kind != 'field':
                continue
            m = re.match(r'STYLEREF\s+"(.*?)"', val)
            if m and m.group(1) not in names:
                names.append(m.group(1))
    return names


def ensure_style_alias(doc, style_name, alias):
    """把 alias 注册为样式的 w:aliases，返回样式是否存在于模板。

    **为什么需要**：Word 的 STYLEREF 域按样式的**本地化显示名或别名**匹配，唯独不认
    w:name 的字面值。实测（中文版 Word）：样式 w:name="heading 1" 时，
    STYLEREF "heading 1" 与 STYLEREF "Heading 1" 都报"错误!未找到引用源"，
    只有 STYLEREF "标题 1" 能解析；给该样式加上别名 "Heading 1" 后两者才都能用。
    因此这里把要求在文件里写的那个名字原样注册成别名——用户写什么，域就用什么，
    不依赖使用者 Word 的界面语言。
    """
    style = _find_style(doc, style_name)
    if style is None:
        return False

    el = style.element
    al = el.find(W('aliases'))
    existing = [a.strip() for a in (al.get(W('val')) or '').split(',') if a.strip()] if al is not None else []
    if alias in existing:
        return True
    existing.append(alias)
    if al is None:
        al = etree.Element(W('aliases'))
        name_el = el.find(W('name'))
        if name_el is not None:
            name_el.addnext(al)
        else:
            el.insert(0, al)
    al.set(W('val'), ','.join(existing))
    return True

