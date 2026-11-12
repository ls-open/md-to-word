#!/usr/bin/env python3
"""skill_utils.py — md-to-word 内部共享基础设施。

整合以下三部分核心能力：
  1. 统一日志配置（stderr 输出，不污染 stdout 报告）
  2. OOXML 主题属性净化（清除 asciiTheme/eastAsiaTheme/themeColor 等，防止覆盖显式样式）
  3. Markdown 文本解析与块级/标题结构校验（frontmatter 拆分、代码块掩码、短代码与块级分隔、CSL/bib 路径解析）
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from lxml import etree

from md_to_word.i18n import t
from md_to_word.utils.masking import mask_html_comments
from md_to_word.preprocessor.blocks import hard_break

# ══════════════════════════════════════════════════════════════════════
# 1. 统一日志配置
# ══════════════════════════════════════════════════════════════════════

_LOG_CONFIGURED = False


def configure_logging(level: str = "INFO", *, force: bool = False) -> logging.Logger:
    """初始化根 logger：stderr handler + 统一格式。幂等（只配一次，除非 force）。"""
    global _LOG_CONFIGURED
    if _LOG_CONFIGURED and not force:
        return logging.getLogger("md2word")

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
    root.setLevel(getattr(logging, str(level).upper(), logging.INFO))
    _LOG_CONFIGURED = True
    return logging.getLogger("md2word")


def get_logger(name: str = "md2word") -> logging.Logger:
    """获取模块级 logger。"""
    return logging.getLogger(name)


# ══════════════════════════════════════════════════════════════════════
# 2. OOXML 主题属性净化
# ══════════════════════════════════════════════════════════════════════

NS_W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

# rFonts 上的主题字体属性（`cstheme` 与 `csTheme` 两种拼写都在真实模板里出现过，都清）
FONT_THEME_ATTRS = ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme', 'csTheme')
# color 上的主题颜色属性
COLOR_THEME_ATTRS = ('themeColor', 'themeTint', 'themeShade')
# 底纹上的主题填充属性：`w:shd` 同时写了 fill 与 themeFill 时以主题色为准，同样是「设了不生效」
FILL_THEME_ATTRS = ('themeFill', 'themeFillTint', 'themeFillShade')
# 全树通杀用（主题属性不只挂在 rFonts/color 上，如 rPrChange 里的旧属性）
THEME_ATTRS = FONT_THEME_ATTRS + COLOR_THEME_ATTRS + FILL_THEME_ATTRS


def _drop_theme_attrs(el, attrs) -> bool:
    """删除 el 上 attrs 列出的主题属性，返回是否真的删掉了东西。"""
    removed = False
    for attr in attrs:
        key = f'{{{NS_W}}}{attr}'
        if key in el.attrib:
            del el.attrib[key]
            removed = True
    return removed


def clear_font_theme_attrs(el) -> bool:
    """清除 el（rFonts）上的主题字体属性。返回是否真的清掉了。"""
    return _drop_theme_attrs(el, FONT_THEME_ATTRS)


def clear_color_theme_attrs(el) -> bool:
    """清除 el（color）上的主题颜色属性。返回是否真的清掉了。"""
    return _drop_theme_attrs(el, COLOR_THEME_ATTRS)


def strip_theme_attrs_from_xml(xml_bytes: bytes) -> bytes:
    """递归清除 XML 里任意层级的全部主题属性，返回同 XML 声明的字节流。"""
    root = etree.fromstring(xml_bytes)
    for el in root.iter():
        _drop_theme_attrs(el, THEME_ATTRS)
    return etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone='yes')


# ══════════════════════════════════════════════════════════════════════
# 3. Markdown 解析、块级分隔与路径工具
# ══════════════════════════════════════════════════════════════════════

def mask_code_fences(content: str) -> str:
    """围栏代码块（``` / ~~~）内各行掩码为 '.'，保留总行数与行号不变。"""
    out = []
    in_fence = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(".")
            continue
        out.append("." if in_fence else line)
    return "\n".join(out)


# 行内代码：`` `…` `` 或 ``` ``…`` ```。整段换成点号，保留长度与行号。
_INLINE_CODE_RE = re.compile(r"(?<!`)(`{1,3})[^`\n]*?\1(?!`)")


def mask_inline_code(content: str) -> str:
    """行内代码的内容掩码为 '.'，保留长度与行号。

    判据只该看「作者真写的正文」时用它：稿件里用反引号演示语法（`` `![alt](x.png)` ``）是
    正当的，不该被当成真图片去查磁盘。
    """
    return _INLINE_CODE_RE.sub(lambda m: "." * len(m.group(0)), content)


def mask_code(content: str) -> str:
    """围栏代码块 + 行内代码一起掩码。"""
    return mask_inline_code(mask_code_fences(content))


def split_frontmatter(text: str) -> tuple[str, str]:
    """拆分 YAML frontmatter，返回 (frontmatter_text, body_text)。
    无 frontmatter 时返回 ("", 原文本)。兼容 UTF-8 BOM、CRLF 行尾与空 frontmatter。
    """
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    # 收尾的 `---` 必须**行首那一条**。少写 MULTILINE、让它随便找一条 `---`，
    # 正文里的横向分隔线就会被当成前置区的结束符——它之前的内容整段被当成 YAML
    # 吃掉，而 YAML 允许纯注释，于是连报错都没有。
    # 收尾也认 `...`：Pandoc 与 CommonMark 都用它结束 YAML 前置区
    m = re.match(r"^---[ \t]*\r?\n(.*?)^(?:---|\.\.\.)[ \t]*(?:\r?\n|$)", text, re.DOTALL | re.M)
    if not m:
        return "", text
    return m.group(1) or "", text[m.end():]


# ── 块级标记：独占一行、并与正文隔开空行 ──────────────────────────────
_MATH_ONLY_RE = re.compile(r"^\s*\$\$(\s*\{#eq-[^}]+\})?\s*$")
_MATH_INLINE_RE = re.compile(r"^\s*\$\$\s*\S.*\$\$(\s*\{#eq-[^}]+\})?\s*$")
_PAGEBREAK_RE = re.compile(r"^\s*\{\{<\s*pagebreak\s*>\}\}\s*$")
TOC_MARKER_RE = re.compile(r"^\s*\{\{<\s*toc(?:\s+(?P<depth>\d+))?\s*>\}\}\s*$")
_SECTION_RE = re.compile(r"^\s*\{\{<\s*section\b[^>]*>\}\}\s*$")

_SHORTCODE_MARKERS = {
    "pagebreak": (_PAGEBREAK_RE, "gate.marker.pagebreak"),
    "toc": (TOC_MARKER_RE, "gate.marker.toc"),
    "section": (_SECTION_RE, "gate.marker.section"),
}
_SHORTCODE_RE = re.compile(r"\{\{<\s*([A-Za-z][\w-]*)")
_DIV_OPEN_RE = re.compile(r"^\s*:::\s*\{.*\}\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|")
_IMAGE_ONLY_RE = re.compile(r"^\s*!\[[^\]]*\]\([^)]+\)(\s*\{[^}]*\})?\s*$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")


# 列表标记行：`- 项目`、`1. 项目`（`---` 是分隔线，已在前面排除）
_LIST_ITEM_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s+\S")


def _is_prose_line(line: str) -> bool:
    """该行是不是正文（非空、非 ---、非标题、非任何块级标记行，也不含 `%%` 段落样式行）。"""
    s = line.strip()
    if not s or s == "---" or _HEADING_RE.match(line):
        return False
    if _LIST_ITEM_RE.match(s):
        return False  # 列表项各自成段，不参与「折行段落」判断
    if not s.strip("."):  # mask_code_fences 用「.」占位；占位行不是正文
        return False
    if s[0] in "|>!" or s.startswith(":::") or s.startswith("%%"):
        return False
    return not (_MATH_ONLY_RE.match(line) or _MATH_INLINE_RE.match(line)
                or any(rex.match(line) for rex, _ in _SHORTCODE_MARKERS.values()))


def _shortcode_marker(line: str):
    """该行出现的短代码名；不是「独占一行」表里的标记则返回 None。"""
    m = _SHORTCODE_RE.search(line)
    return m.group(1) if m and m.group(1) in _SHORTCODE_MARKERS else None


_INLINE_CODE_SPAN = re.compile(r"`[^`]*`")


def _strip_inline_code(line: str) -> str:
    """去掉行内代码的内容（保持列宽），用于标记检测。

    `` `{{< pagebreak >}}` `` 里那段是**字面量**：文档里引用一句写法，不等于要在
    这里插一个分页符。不剥掉，任何讲解写法的稿件都会被自己的示例拦下。
    """
    return _INLINE_CODE_SPAN.sub(lambda m: " " * len(m.group(0)), line)


def unknown_shortcode_issues(text: str) -> list:
    """不认识的短代码 → [(行号, 名字)]；空列表 = 没有。"""
    if not text:
        return []
    issues = []
    for i, line in enumerate(mask_code_fences(text).split("\n")):
        for m in _SHORTCODE_RE.finditer(_strip_inline_code(line)):
            if m.group(1) not in _SHORTCODE_MARKERS:
                issues.append((i + 1, m.group(1)))
    return issues


def block_marker_issues(text: str, lang: str = "zh") -> list:
    """块级标记写法问题 → [(行号, 说明)]；空列表 = 全部规范。"""
    if not text:
        return []
    lines = mask_code_fences(text).split("\n")
    issues: list[tuple[int, str]] = []

    def after_glued(i: int) -> bool:
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        return _is_prose_line(nxt) or bool(_HEADING_RE.match(nxt))

    def before_glued(i: int) -> bool:
        return i > 0 and _is_prose_line(lines[i - 1])

    in_math = False
    for i, line in enumerate(lines):
        no = i + 1
        scan = _strip_inline_code(line)  # 行内代码里的标记是字面量，不算标记
        if _MATH_ONLY_RE.match(scan):
            in_math = not in_math
            if not in_math and after_glued(i):
                issues.append((no, t("gate.block.math_close_no_blank", lang)))
            continue
        if in_math:
            continue
        if "$$" in scan:
            if not _MATH_INLINE_RE.match(scan):
                issues.append((no, t("gate.block.math_inline_with_text", lang)))
            elif after_glued(i):
                issues.append((no, t("gate.block.math_no_blank", lang)))
        elif (marker := _shortcode_marker(scan)) is not None:
            whole_line_re, label_key = _SHORTCODE_MARKERS[marker]
            label = t(label_key, lang)
            if not whole_line_re.match(scan):
                issues.append((no, t("gate.block.marker_not_alone", lang, label=label)))
            elif after_glued(i):
                issues.append((no, t("gate.block.marker_no_blank", lang, label=label)))
        elif _DIV_OPEN_RE.match(line):
            if before_glued(i):
                issues.append((no, t("gate.block.div_no_blank", lang)))
        elif _IMAGE_ONLY_RE.match(line):
            if before_glued(i):
                issues.append((no, t("gate.block.image_no_blank_before", lang)))
            if after_glued(i):
                issues.append((no, t("gate.block.image_no_blank_after", lang)))
        elif _TABLE_ROW_RE.match(line) and not (i and _TABLE_ROW_RE.match(lines[i - 1])):
            if before_glued(i):
                issues.append((no, t("gate.block.table_no_blank", lang)))
    return issues


_IMG_WIDTH_CM_RE = re.compile(r'!\[[^\]]*\]\([^)]+\)\s*\{[^}]*\bwidth\s*=\s*([\d.]+)cm')


def image_width_issues(text: str, content_cm: float, lang: str = "zh") -> list[tuple[int, str]]:
    """图片声明宽度超过版心 → [(行号, 说明)]。`content_cm` 是版心宽度（cm）。

    **写超了不会报错，会被静默改小**：实测 A4 + 2.54cm 边距下写 `{width=25cm}`，
    产物里是 15.90cm——算式是 `pgSz − pgMar`，与计算版心用的是同一条公式。
    作者以为排的是 25cm，拿到的是别的数；因此写超出一律提醒，并给出真实版心宽度。
    """
    if not text:
        return []
    issues = []
    for i, line in enumerate(mask_code_fences(text).split("\n")):
        if line.lstrip().startswith("|"):        # 表格行里的 `|` 不是图片语法
            continue
        for m in _IMG_WIDTH_CM_RE.finditer(line):
            w = float(m.group(1))
            if w > content_cm + 0.01:
                issues.append((
                    i + 1,
                    t("gate.image_width.over", lang, width=w, content=content_cm),
                ))
    return issues


def has_declared_image_width(text: str) -> bool:
    """稿件里有没有写过 `{width=Ncm}`——决定上面那条门禁有没有活要干。

    没给格式要求文件时算不出版心，门禁只能跳过；但该被跳过的是**有宽度可查**的稿件，
    一张宽度都没声明的稿子不必为它多出一行「未校验」。
    """
    if not text:
        return False
    return any(_IMG_WIDTH_CM_RE.search(line)
               for line in mask_code_fences(text).split("\n")
               if not line.lstrip().startswith("|"))


def malformed_table_issues(text: str, lang: str = "zh") -> list[tuple[int, str]]:
    """Markdown 表格各行列数不一致 → [(行号, 说明)]。

    **这不是排版问题，是内容丢失**：列数对不上时不报错，多出来的单元格连同其中的文字
    一并丢弃（实测：表头 3 列、分隔行 2 格、数据行 3 格 → 产物只剩前两列，第三列的文字
    全部缺失，全程零告警）。因此必须在导出前拦下。
    """
    if not text:
        return []
    lines = mask_code_fences(text).split("\n")
    issues: list[tuple[int, str]] = []
    i = 0
    while i < len(lines):
        if not _TABLE_ROW_RE.match(lines[i]):
            i += 1
            continue
        # 一块连续的表格行
        block = []
        while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
            block.append((i + 1, lines[i]))
            i += 1
        if len(block) < 2:
            continue
        from md_to_word.model.reader import split_table_cells
        def _cnt(line_str: str) -> int:
            s = line_str.strip()
            if s.startswith("|"):
                s = s[1:]
            if s.endswith("|"):
                s = s[:-1]
            return len(split_table_cells(s))

        counts = [(no, _cnt(line)) for no, line in block]
        expect = counts[0][1]
        bad = [(no, n) for no, n in counts[1:] if n != expect]
        if bad:
            first_bad, n = bad[0]
            issues.append((
                first_bad,
                t("gate.table.column_count", lang, expect=expect, line=first_bad, actual=n),
            ))
    return issues


def section_pagebreak_issues(text: str, lang: str = "zh") -> list[tuple[int, str]]:
    """`{{< section … >}}` 后面紧跟 `{{< pagebreak >}}` → [(行号, 说明)]。

    分节标记底层已自带「下一页」分节符，后面再加一个分页符会多顶出一页
    （实测：论文样例 5 页 → 6 页）。**只查这一个方向**——反过来（分页符写在
    分节标记之前）实测不产生多余页，5 页仍是 5 页，所以不报。
    """
    if not text:
        return []
    lines = mask_code_fences(text).split("\n")
    issues: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not _SECTION_RE.match(line):
            continue
        for j in range(i + 1, len(lines)):
            if not lines[j].strip():
                continue
            if _PAGEBREAK_RE.match(lines[j]):
                issues.append((j + 1, t("gate.section.extra_page", lang, section=i + 1)))
            break
    return issues


# ── 引文 key（`[@key]` / `@key`）──
# 字符集实测而来：首字符是字母数字或 `_`，其后允许 `: . - _ + / % &`（k1:2 / k-2 / k_3 /
# k.4 / k+5 / k%7 / k/7 / k&7 都被 citeproc 认作引文并能在 .bib 里命中）。
# `@` 前是 ASCII 字母数字则不算引文（`user@example.com` 原样输出）；汉字不算——「见@smith2020」是自然写法。
# `-@key`（抑制作者）的 `@` 前是 `-`，故 `-` 不能进排除集，否则那种写法会被整条漏掉。
# 尖括号里带 `@` 或 `://` 的整段：自动链接与邮箱，里面的 `@` 不是引文
_ANGLE_RE = re.compile(r"<[^>\s]*(?:@|://)[^>\s]*>")
_CITE_KEY_RE = re.compile(r'(?<![A-Za-z0-9_@])@(\w[\w:.\-+/%&]*)')
# .bib 条目头：`@article{key,` / `@book{key,`
_BIB_ENTRY_RE = re.compile(r'@\w+\s*\{\s*([^,\s}]+)\s*,')
# 行内代码 `` `...` `` —— mask_code_fences 只管围栏块，行内代码得在这里单独遮掉
_INLINE_CODE_RE = re.compile(r'`[^`]*`')
# 块级公式的围栏：`$$` 单独一行，收尾行可以带标签 `$$ {#eq-a}`
_DISPLAY_FENCE_RE = re.compile(r"^\$\$(?:\s*\{#[\w:.\-]+\})?$")
# 稿子里定义过的标签：`{#eq-dynamics}`、`{#tbl-main}`
_DEFINED_LABEL_RE = re.compile(r'\{#([\w:.\-]+)\}')
# 交叉引用标签前缀——`@eq-x` 这类是**交叉引用**，不是文献 key，
# 当文献 key 去 .bib 里找必然找不到（demo/01 的 `@eq-dynamics` 即属此类）。
_CROSSREF_PREFIX_RE = re.compile(r'^(?:eq|fig|tbl|sec|lst)-')
# `[@eq-x]` / `[@fig-x; @eq-y]`：方括号里的交叉引用（应为 `@eq-x`，不加方括号）
_BRACKETED_CITE_RE = re.compile(r'\[[^\]\n]*@([\w:.\-]+)[^\]\n]*\]')


def parse_bib_keys(bib_text: str) -> set:
    """从 .bib 文本里取出全部条目 key。"""
    return set(_BIB_ENTRY_RE.findall(bib_text or ''))


def cited_keys(text: str, line_offset: int = 0):
    """逐行产出 `(行号, key)`——正文里所有 `[@key]` / `@key` 的候选 key。

    已遮掉围栏块与行内代码，已剥掉句末句点。末尾句点必须剥：`@smith2023.` 在句末时
    citeproc 解析出的 key 是 `smith2023`（实测无 WARNING），而字符集含 `.`，
    不剥就会抽出 `smith2023.` 去报一个不存在的 key——**误报比漏报贵**，它拦的是合法导出。

    `line_offset` 是给「只拿到去掉 frontmatter 的正文」的调用方补行号用的：
    不补，报出来的行号会比稿件实际行号少掉 frontmatter 的行数，用户照着找必然错位。
    """
    for i, raw in enumerate(mask_code_fences(text or '').split("\n"), 1):
        # `<https://…>` 与 `<foo@bar>` 是自动链接，里面的 `@` 不是引文
        line = _ANGLE_RE.sub(" ", _INLINE_CODE_RE.sub(" ", raw))
        for m in _CITE_KEY_RE.finditer(line):
            key = m.group(1).rstrip('.')
            if key:
                yield i + line_offset, key


def defined_labels(text: str) -> set:
    """稿子里定义过的标签（`{#eq-dynamics}` 的 `eq-dynamics`）。"""
    return set(_DEFINED_LABEL_RE.findall(text or ''))


def unbalanced_math_issues(text: str) -> list[tuple[int, str]]:
    """公式里的花括号不配对 → [(行号, 片段)]。

    转换器对这种写法不会报错，它会**静默丢内容**：`\\frac{a}{b` 渲染出来只剩 `ab`，
    分子分母的结构整个没了。所以按行检查未转义的花括号，不配对即拦下。
    """
    issues: list[tuple[int, str]] = []
    in_display = False
    for i, line in enumerate(mask_code_fences(text).split("\n"), 1):
        stripped = line.strip()
        if _DISPLAY_FENCE_RE.match(stripped):
            in_display = not in_display
            continue
        segments = [line] if in_display or "$$" in line else re.findall(r"(?<!\$)\$[^$\n]+\$", line)
        for seg in segments:
            body = seg.replace("\\{", "").replace("\\}", "")
            if body.count("{") != body.count("}"):
                issues.append((i, stripped[:80]))
                break
    if in_display:
        # 围栏没闭合：那是「`$$` 未配对」，由方言检查单独报一次即可。顺着这个误判往下扫，
        # 后面每一行的 `%` / 花括号都会被算成公式内容，一屏假错误把真病因淹掉。
        return []
    return issues


def math_comment_issues(text: str) -> list[tuple[int, str]]:
    """公式里的裸 `%` → [(行号, 片段)]。

    LaTeX 里 `%` 是注释起始：`$a%b$` 转换出来只剩 `a`，后半截静默消失，退出码 0。
    字面百分号必须写 `\\%`——不改解析（LaTeX 语义本就如此），只把后果说清楚。
    """
    issues: list[tuple[int, str]] = []
    in_display = False
    for i, line in enumerate(mask_code_fences(text).split("\n"), 1):
        stripped = line.strip()
        if _DISPLAY_FENCE_RE.match(stripped):
            in_display = not in_display
            continue
        segments = [line] if in_display or "$$" in line else re.findall(r"(?<!\$)\$[^$\n]+\$", line)
        for seg in segments:
            if re.search(r"(?<!\\)%", seg):
                issues.append((i, stripped[:80]))
                break
    if in_display:
        # 围栏没闭合：那是「`$$` 未配对」，由方言检查单独报一次即可。顺着这个误判往下扫，
        # 后面每一行的 `%` / 花括号都会被算成公式内容，一屏假错误把真病因淹掉。
        return []
    return issues


def bracketed_crossref_issues(text: str, line_offset: int = 0, lang: str = "zh") -> list[tuple[int, str]]:
    """交叉引用写成了引文方括号（`[@eq-x]`）→ [(行号, 说明)]。

    方括号是引文写法，渲染期会拿 `eq-x` 去文献库里找，找不到就从 citeproc 深处抛异常，
    最后被兜底成「未预料到的内部错误…本工具的缺陷」——归因完全错了。交叉引用不带方括号
    （`@eq-x`），这一条能在预检里静态看出来，就该在预检说出来。

    与文献库无关：没写 `.bib` 的稿子同样要报，所以不放在 `citation_key_issues` 的
    `known_keys` 早退之后。
    """
    issues: list[tuple[int, str]] = []
    for i, raw in enumerate(mask_code_fences(text or "").split("\n"), 1):
        line = _ANGLE_RE.sub(" ", _INLINE_CODE_RE.sub(" ", raw))
        for m in _BRACKETED_CITE_RE.finditer(line):
            key = m.group(1).rstrip(".")
            if _CROSSREF_PREFIX_RE.match(key):
                issues.append((
                    i + line_offset,
                    t("gate.citation.bracketed_crossref", lang, key=key),
                ))
    return issues


def citation_key_issues(
    text: str, known_keys: set, line_offset: int = 0, lang: str = "zh"
) -> list[tuple[int, str]]:
    """正文引用了 `.bib` 里没有的 key → [(行号, 说明)]，每个 key 只报一次。

    属于「能确定」的一类：文献库是纯文本，正文引了哪些 key 也是纯文本，两边取差集即可，
    不需要渲染。不查的后果实测过——正文里留下 `[nosuchkey2020?]`（citeproc 的占位），
    参考文献列表里也不会有它，而三道门禁全绿。

    `known_keys` 为空时返回空：那种情况下每个被引 key 都会报，是噪声；**「文献库读到了
    却一条条目都没有」由调用方单独报**（`check_md.py` 的 1b），不在这里静默吞掉。

    只覆盖**能静态看出**的写法；citeproc 还有边角写法，故 `export.sh` 另有一层以它自己的
    WARNING 为准的兜底——两层互补，不是重复。
    """
    if not known_keys:
        return []
    labels = defined_labels(text)
    issues: list[tuple[int, str]] = []
    reported: set = set()
    for line_no, key in cited_keys(text, line_offset):
        # `@eq-x` 这类是交叉引用，归 undefined_crossref_issues 管，
        # 拿到 .bib 里找必然落空。
        if key in known_keys or key in labels or _CROSSREF_PREFIX_RE.match(key):
            continue
        if key in reported:
            continue
        reported.add(key)
        issues.append((line_no,
                       t("gate.citation.unknown_key", lang, key=key)
                       + _cjk_key_hint(key, lang)))
    return issues


_CJK_RE = re.compile(r"[㐀-䶿一-鿿]")


def _cjk_key_hint(key: str, lang: str) -> str:
    """key 里混进汉字时补一句"`@` 后要留空格"。

    汉字也可能是合法 key（`{#eq-甲}`），所以不改解析，只把话说清。
    """
    return t("gate.key.cjk_swallowed", lang) if _CJK_RE.search(key) else ""


def undefined_crossref_issues(
    text: str, line_offset: int = 0, lang: str = "zh"
) -> list[tuple[int, str]]:
    """正文引用了 `@eq-x` / `@fig-x` / `@tbl-x`，但稿子里没有 `{#eq-x}` 定义。

    与引文 key 是同一类失败：渲染成 **`?@eq-x`**，残骸直接印在正文里，而导出全程不报错。
    """
    labels = defined_labels(text)
    issues: list[tuple[int, str]] = []
    reported: set = set()
    for line_no, key in cited_keys(text, line_offset):
        if not _CROSSREF_PREFIX_RE.match(key) or key in labels or key in reported:
            continue
        reported.add(key)
        issues.append((line_no,
                       t("gate.crossref.undefined", lang, key=key)
                       + _cjk_key_hint(key, lang)))
    return issues


def citations_without_bibliography(text: str, line_offset: int = 0) -> list[int]:
    """正文里出现**文献引用**语法的行号，保序去重。

    实测：YAML 没有 `bibliography:` 时**引文完全不处理**——`[@somekey2020]` 不是渲染成
    `(somekey2020?)` 那种占位符，而是**这十三个字符原样印进 docx 正文**，导出照样报成功。
    所以这属于「能确定」的一类。

    **交叉引用不算文献引用**：`@eq-model1`（或稿子里定义过的 `{#标签}`）照常渲染，
    没有 `bibliography:` 也不受影响。把它算进来，会让「有公式编号、没有参考文献」的常规
    报告被误拦。交叉引用自身的失效由 `undefined_crossref_issues` 负责。
    """
    labels = defined_labels(text)
    seen: set = set()
    out: list[int] = []
    for line_no, key in cited_keys(text, line_offset):
        if key in labels or _CROSSREF_PREFIX_RE.match(key):
            continue
        if line_no not in seen:
            seen.add(line_no)
            out.append(line_no)
    return out


def heading_issues(text: str, lang: str = "zh") -> list[tuple[int, str]]:
    """检查标题层级的规范问题 → [(行号, 说明)]。

    检查项：
      1. 正文第一个 `#` 标题必须是 1 级（不能从 `##` 开始）
      2. `#` 标题层级必须连续（不能从 `#` 直接跳到 `###`）
      3. 带数字编号的章节标题（如 `1.`、`2.1`、`2.1.1`），其编号深度必须等于 `#` 的数量
         （防止把论文大标题写成 `# 标题` 导致全文编号章节被挤到 `## 1.` / `### 1.1`）
    """
    if not text:
        return []
    _, body = split_frontmatter(text)
    start_offset = text.count("\n") - body.count("\n")
    lines = mask_code_fences(body).split("\n")

    issues: list[tuple[int, str]] = []
    prev_level = 0

    for idx, line in enumerate(lines):
        line_no = start_offset + idx + 1
        stripped = line.strip()

        m_head = re.match(r'^(#{1,6})\s+(.+?)\s*$', stripped)
        if not m_head:
            continue

        hashes, raw_title = m_head.group(1), m_head.group(2)
        title = _UNLISTED_HEADING_ATTR_RE.sub("", raw_title).rstrip().rstrip("#").rstrip()
        if not title:
            continue
        level = len(hashes)

        # 1. 第一个标题必须是 1 级
        if prev_level == 0 and level != 1:
            issues.append((
                line_no,
                t("gate.heading.first_level", lang, level=level, hashes=hashes, title=title[:30]),
            ))
        # 2. 标题不得跳级
        elif prev_level > 0 and level > prev_level + 1:
            issues.append((
                line_no,
                t("gate.heading.level_jump", lang, prev=prev_level, level=level, hashes=hashes,
                  title=title[:30], expected="#" * (prev_level + 1)),
            ))

        # 3. 章节数字编号深度必须等于 # 数量（如 # 1. / ## 2.1 / ### 2.1.1）
        num_match = re.match(r'^(\d+(?:\.\d+)*)\.?\s+\S', title)
        if num_match:
            number_str = num_match.group(1)
            number_depth = number_str.count('.') + 1
            if number_depth != level:
                issues.append((
                    line_no,
                    t("gate.heading.number_depth", lang, hashes=hashes, title=title[:30], level=level,
                      number=number_str, depth=number_depth),
                ))

        prev_level = level

    return issues


def resolve_manuscript_path(
    value: str,
    md_path: Path,
    skill_csl_dir: Optional[Path] = None,
) -> tuple[Path, str]:
    """解析稿件 YAML 里的路径值（csl / bibliography），返回 (解析到的路径, 命中的写法)。

    支持三种写法：
      - `'absolute'`      — 绝对路径；
      - `'doc-relative'`  — 相对**稿件所在目录**的路径；
      - `'skill-builtin'` — 仅当传入 `skill_csl_dir` 时，若本地不存在，自动在技能内置 `csl/` 目录按文件名匹配；
      - `''`              — 都没命中（返回最可能的目标路径，供报错展示）。
    """
    p = Path(value).expanduser()
    if p.is_absolute():
        return (p, "absolute") if p.exists() else (p, "")
    cand = md_path.parent / p
    if cand.exists():
        return (cand, "doc-relative")
    if skill_csl_dir is not None and skill_csl_dir.is_dir() and p.parent == Path("."):
        # 仅当填写纯文件名（如 `apa.csl`）时，在技能内置 resources/csl/ 目录下匹配
        builtin_cand = skill_csl_dir / p.name
        if builtin_cand.exists():
            return (builtin_cand.resolve(), "skill-builtin")
    return (cand, "")


# 句末标点算「这段写完了」；`；`/`：` 后面显然还有话，不算。
_TERMINAL_PUNCT = "。！？…!?）)」』”'"


def soft_wrap_issues(text: str) -> list:
    """相邻两行都是正文、且上一行没有句末标点 → [(行号, 上一行片段)]。

    本引擎按「一行一段」读取（Markdown 里一段本来就能写成一行，不需要延续规则）。
    稿件里若把一段折成多行，会被拆成几段，每段各吃一次首行缩进，版面上看得出来，
    因此提醒一句，不阻断。
    """
    if not text:
        return []
    _, body = split_frontmatter(text)
    offset = text.count("\n") - body.count("\n")  # 前置区也占行号，报错要对得上原稿
    lines = mask_code_fences(body).split("\n")
    # `$$` 块里的每一行都是公式，不是折行的正文：多行公式会被误报成「折行段落」
    in_math: set[int] = set()
    open_at = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("$$") and stripped.count("$$") == 1:
            if open_at is None:
                open_at = index
            else:
                in_math.update(range(open_at, index + 1))
                open_at = None
        elif open_at is not None:
            in_math.add(index)
    issues: list[tuple[int, str]] = []
    for i in range(len(lines) - 1):
        if i in in_math or i + 1 in in_math:
            continue
        here, nxt = lines[i], lines[i + 1]
        if not (_is_prose_line(here) and _is_prose_line(nxt)):
            continue
        if here.rstrip().endswith(tuple(_TERMINAL_PUNCT)):
            continue
        if hard_break(here)[1]:
            continue  # 行尾写了 `\` / 两个空格 = 作者要的就是段内换行，不是折行
        snippet = here.strip()
        issues.append((i + 2 + offset, snippet[:24] + ("…" if len(snippet) > 24 else "")))
    return issues


# ── 未实现的 Markdown 方言 ────────────────────────────────────────────
# 判据只有一条：**按这种写法写下去，原始语法会不会漏进成品**。会漏的拦下并给出替代写法；
# 只是排版细节不同的不拦——预检是契约检查，不是 Markdown 语法考试。
_HTML_TAG_RE = re.compile(
    r"</?(?:a|b|br|center|div|em|font|hr|i|img|p|span|strong|sub|sup|table|td|th|tr|u)\b[^>]*>",
    re.I,
)
# 自动链接：`<https://…>` 与 `<foo@bar>` 两种形态，正文里都不支持
_AUTOLINK_RE = re.compile(r"<[^<>\s]*(?:://|@)[^<>\s]*>")
_HR_RE = re.compile(r"^\s{0,3}(?:\*\s*){3,}$|^\s{0,3}(?:-\s*){3,}$|^\s{0,3}(?:_\s*){3,}$")
_SETEXT_RE = re.compile(r"^\s{0,3}=+\s*$")
_DEF_LIST_RE = re.compile(r"^\s{0,3}:\s+\S")
_TASK_ITEM_RE = re.compile(r"^\s*[-*+]\s+\[[ xX]\]\s")
_NOEDGE_TABLE_RE = re.compile(r"^\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+$")
_NESTED_QUOTE_RE = re.compile(r"^\s*>\s*>")
_WIDE_STYLE_RE = re.compile(r"^\s*％％")
# 引用式链接：`[文字][ref]` 与定义行 `[ref]: url`。本引擎只认内联式，不拦就印成字面量。
# `[^1]` 是脚注，不是链接标签
_REF_LINK_RE = re.compile(r"\[(?!\^)[^\]]+\]\[[^\]]*\]")
_REF_LINK_DEF_RE = re.compile(r"^\s{0,3}\[(?!\^)[^\]]+\]:\s*\S")
_EMPTY_HEADING_RE = re.compile(r"^\s*#{1,6}\s*$")
_UNLISTED_HEADING_ATTR_RE = re.compile(r"\s*\{(?:\.unlisted|不入目录)\}\s*$")
_HIGHLIGHT_RE = re.compile(r"==[^=\s][^=]*?==")
_SPAN_ATTR_RE = re.compile(r"\[[^\]]*\]\{\s*(?P<attr>[.#][^}]*)\}")
_PAREN_MATH_RE = re.compile(r"\\\(.+?\\\)")
# `\[…\]` 与 `\(…\)` 是同一种失败：原样印进 Word。前面紧挨反斜杠的是转义写法的
# 一部分（LaTeX 换行 `\\[2pt]`），不是这里要拦的括号。
_BRACKET_MATH_RE = re.compile(r"(?<!\\)\\[\[\]]")
_NO_SPACE_HEADING_RE = re.compile(r"^\s*#{1,6}[^\s#]")
# 图片行能带的属性只有宽度；`{align=right}` 这类「写了等于没写」的写法要拦下来
_IMAGE_ATTR_RE = re.compile(r"!\[[^\]]*\]\([^)\s]+\)\s*\{(?P<attrs>[^}]*)\}")
_IMAGE_ATTR_OK = re.compile(r"^\s*(?:width\s*=\s*[\d.]+\s*(?:cm|mm|in|pt)?)?\s*$")
_INDENT_CODE_RE = re.compile(r"^(?: {4,}|\t)\S")
_LIST_ITEM_ANY_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\S")


def _looks_like_block_start(line: str) -> bool:
    """缩进行是不是另一块的开始（列表项、标记、表格、图片、标题、公式）。"""
    stripped = line.strip()
    return bool(
        not stripped
        or _LIST_ITEM_ANY_RE.match(line)
        or stripped.startswith(("{{<", "%%", "|", "$$", "#", ":::", "!["))
    )


def dialect_issues(text: str, lang: str = "zh") -> list[tuple[int, str]]:
    """稿件里用了本引擎没实现的 Markdown 写法 → [(行号, 说明)]；空列表 = 全部规范。

    这些写法不会报错，只会把原始语法原样印进 Word：`---` 印成三条短横、`<br>` 印成
    尖括号、`**` 跨行时印成星号。静默印错比报错难查得多，所以在导出前拦下来。
    """
    if not text:
        return []
    _, body = split_frontmatter(text)
    offset = text.count("\n") - body.count("\n")
    # 先掩码围栏、再挖掉 HTML 注释（换成等量换行，行号不挪）：注释在导出时会被剔除，
    # 里面的 `<br>` 不该被当成正文字面量拦下来。
    masked = mask_code_fences(body)
    masked = mask_html_comments(masked)
    lines = masked.split("\n")
    issues: list[tuple[int, str]] = []

    in_display_math = False
    opened_at = 0
    for index, line in enumerate(lines):
        line_no = index + 1 + offset
        code_free = _strip_inline_code(line)
        if re.match(r"^\s*#{1,6}\s+", code_free):
            # 允许在 # 标题行尾写 `{.unlisted}` / `{不入目录}` 标记单个标题不入目录
            code_free = _UNLISTED_HEADING_ATTR_RE.sub("", code_free)

        # `$$` 独占一行是块级公式的围栏，要成对切换；单行的 `$$…$$` 整行都是公式，
        # 既不切换状态、也不需要检查符号配对——两者混为一谈会让后面所有的 `$` 检查失效。
        if _DISPLAY_FENCE_RE.match(code_free.strip()):
            in_display_math = not in_display_math
            if in_display_math:
                opened_at = line_no
            continue
        if code_free.strip().startswith("$$"):
            continue

        if _HTML_TAG_RE.search(code_free) or _AUTOLINK_RE.search(code_free):
            issues.append((line_no, t("gate.dialect.html", lang)))
            continue
        if _REF_LINK_RE.search(code_free) or _REF_LINK_DEF_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.ref_link", lang)))
            continue
        if _HR_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.hr", lang)))
            continue
        if _SETEXT_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.setext", lang)))
            continue
        if _DEF_LIST_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.def_list", lang)))
            continue
        if _TASK_ITEM_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.task_item", lang)))
            continue
        if _NO_SPACE_HEADING_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.heading_no_space", lang)))
            continue
        for img in _IMAGE_ATTR_RE.finditer(code_free):
            attrs = img.group('attrs')
            if '%' in attrs:
                issues.append((line_no, t("gate.dialect.image_percent", lang)))
                break
            if not _IMAGE_ATTR_OK.match(attrs):
                issues.append((line_no, t("gate.dialect.image_attr", lang)))
                break
        if _HIGHLIGHT_RE.search(code_free):
            issues.append((line_no, t("gate.dialect.highlight", lang)))
            continue
        span = _SPAN_ATTR_RE.search(code_free)
        if span and span.group("attr").strip() != ".underline":
            # `{.underline}` 是引擎支持的写法，其余属性落到字面量，拦下来
            issues.append((line_no, t("gate.dialect.span_attr", lang)))
            continue
        if _PAREN_MATH_RE.search(code_free):
            issues.append((line_no, t("gate.dialect.inline_math_paren", lang)))
            continue
        if _BRACKET_MATH_RE.search(code_free):
            issues.append((line_no, t("gate.dialect.block_math_bracket", lang)))
            continue
        if _EMPTY_HEADING_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.empty_heading", lang)))
            continue
        if _NOEDGE_TABLE_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.table_no_edge", lang)))
            continue
        if _NESTED_QUOTE_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.nested_quote", lang)))
            continue
        if _WIDE_STYLE_RE.match(code_free):
            issues.append((line_no, t("gate.dialect.wide_style_marker", lang)))
            continue
        if (
            # 缩进看**原始行**：`code_free` 把行内代码换成了等长空格，拿它判缩进的话，
            # 以行内代码开头的一段正文（`` `code` 开头… ``）会凭空多出空格被当成代码块。
            _INDENT_CODE_RE.match(line)
            and (index == 0 or not lines[index - 1].strip())
            and not _LIST_ITEM_ANY_RE.match(code_free)
        ):
            issues.append((line_no, t("gate.dialect.indented_code", lang)))
            continue

        # 行内公式必须在同一行内闭合：不配对时后文会被整段当成公式吞掉
        unescaped_dollars = re.sub(r"\\\$", "", code_free)
        if not in_display_math and unescaped_dollars.count("$") % 2:
            issues.append((line_no, t("gate.dialect.unclosed_dollar", lang)))
            continue

    if in_display_math:
        # 报**开围栏那一行**：报文件末尾等于让作者去猜哪一条没闭合
        issues.append((opened_at or len(lines) + offset,
                       t("gate.dialect.unclosed_display_math", lang)))

    # 首尾不带竖线的表格：连续两行都有竖线，却都不以竖线开头。按规则二维网格读不到，
    # 只会一行一段地把竖线原样印出去。
    for index in range(len(lines) - 1):
        here, nxt = lines[index], lines[index + 1]
        if "|" in here and "|" in nxt and not here.lstrip().startswith("|") \
                and not nxt.lstrip().startswith("|") and not _LIST_ITEM_ANY_RE.match(here):
            issues.append((index + 1 + offset, t("gate.dialect.table_needs_pipes", lang)))
            break

    # 列表项后面的缩进段落：Markdown 里算列表项的第二段，本引擎会当成独立正文段落，
    # 位置从列表里跑出去。看得见，但结构已经变了，所以拦下。
    for index in range(len(lines) - 2):
        if not _LIST_ITEM_ANY_RE.match(lines[index]):
            continue
        if lines[index + 1].strip() or not lines[index + 2].strip():
            continue
        if lines[index + 2].startswith(("  ", "\t")) and not _looks_like_block_start(lines[index + 2]):
            issues.append(
                (index + 1 + offset, t("gate.dialect.list_second_paragraph", lang))
            )
    return sorted(issues)
