"""模板生成的共享底层：常量、页面几何、属性写入与样式修改。"""

from __future__ import annotations

from docx.enum.style import WD_STYLE_TYPE
from docx.shared import Pt
from lxml import etree

from md_to_word.spec.constants import (
    ALIGN_ENUM_VAL, TWIPS_PER_CM, W, page_size_cm, split_fonts,
)
from md_to_word.spec.models import MinLineSpacing
from md_to_word.utils.skill_utils import (
    clear_color_theme_attrs, clear_font_theme_attrs, get_logger,
)

logger = get_logger(__name__)


def join_reasons(parts, lang: str = "zh") -> str:
    """把若干条原因拼成一句：分隔符跟着消息语言走。"""
    return ("; " if lang == "en" else "；").join(parts)


def page_size_twips(page_size: str) -> tuple:
    """纸张 → (宽, 高) twips（对账侧与写入侧共用，避免各写一份常量）。"""
    w_cm, h_cm = page_size_cm(page_size)
    return int(round(w_cm * TWIPS_PER_CM)), int(round(h_cm * TWIPS_PER_CM))


def ensure_rpr(element):
    """确保元素有 rPr 子元素，返回 rPr"""
    rpr = element.find(W('rPr'))
    if rpr is None:
        rpr = etree.SubElement(element, W('rPr'))
    return rpr


# ── OOXML 子元素顺序 ──
# Word 对 w:rPr / w:pPr / w:tblStylePr / w:settings 的子元素顺序有 schema 强制要求，
# 顺序错了 Word 会**整段忽略**（不报错）。按位置插入，不无脑 append。
_RPR_ORDER = ['rStyle', 'rFonts', 'b', 'bCs', 'i', 'iCs', 'caps', 'smallCaps', 'strike',
              'dstrike', 'outline', 'shadow', 'emboss', 'imprint', 'noProof', 'snapToGrid',
              'vanish', 'webHidden', 'color', 'spacing', 'w', 'kern', 'position', 'sz', 'szCs',
              'highlight', 'u', 'effect', 'bdr', 'shd', 'fitText', 'vertAlign', 'rtl', 'cs',
              'em', 'lang', 'eastAsianLayout', 'specVanish', 'oMath']
_PPR_ORDER = ['pStyle', 'keepNext', 'keepLines', 'pageBreakBefore', 'framePr', 'widowControl',
              'numPr', 'suppressLineNumbers', 'pBdr', 'shd', 'tabs', 'suppressAutoHyphens',
              'kinsoku', 'wordWrap', 'overflowPunct', 'topLinePunct', 'autoSpaceDE', 'autoSpaceDN',
              'bidi', 'adjustRightInd', 'snapToGrid', 'spacing', 'ind', 'contextualSpacing',
              'mirrorIndents', 'suppressOverlap', 'jc', 'textDirection', 'textAlignment',
              'textboxTightWrap', 'outlineLvl', 'divId', 'cnfStyle', 'rPr', 'sectPr', 'pPrChange']
_STYLE_ORDER = ['name', 'aliases', 'basedOn', 'next', 'link', 'autoRedefine', 'hidden',
                'uiPriority', 'semiHidden', 'unhideWhenUsed', 'qFormat', 'locked', 'personal',
                'personalCompose', 'personalReply', 'rsid', 'pPr', 'rPr', 'tblPr', 'trPr',
                'tcPr', 'tblStylePr']
_TBLSTYLEPR_ORDER = ['pPr', 'rPr', 'tblPr', 'trPr', 'tcPr']
_TBLPR_ORDER = ['tblStyle', 'tblpPr', 'tblOverlap', 'bidiVisual', 'tblStyleRowBandSize',
                'tblStyleColBandSize', 'tblW', 'jc', 'tblCellSpacing', 'tblInd', 'tblBorders',
                'shd', 'tblLayout', 'tblCellMar', 'tblLook', 'tblCaption', 'tblDescription']
_TCPR_ORDER = ['cnfStyle', 'tcW', 'gridSpan', 'hMerge', 'vMerge', 'tcBorders', 'shd', 'noWrap',
               'tcMar', 'textDirection', 'tcFitText', 'vAlign', 'hideMark']
_SECTPR_ORDER = ['headerReference', 'footerReference',
                 'footnotePr', 'endnotePr', 'type', 'pgSz', 'pgMar', 'paperSrc', 'pgBorders',
                 'lnNumType', 'pgNumType', 'cols', 'formProt', 'vAlign', 'noEndnote',
                 'titlePg', 'textDirection', 'bidi', 'rtlGutter', 'docGrid', 'printerSettings']
_SETTINGS_ORDER = [
    'zoom', 'mirrorMargins', 'bordersDoNotSurroundHeader', 'bordersDoNotSurroundFooter',
    'defaultTabStop', 'drawingGridVerticalSpacing',
    'displayHorizontalDrawingGridEvery', 'displayVerticalDrawingGridEvery',
    'evenAndOddHeaders', 'characterSpacingControl', 'compat', 'mathPr',
    'themeFontLang', 'clrSchemeMapping', 'decimalSymbol', 'listSeparator',
]
# ── 段落下边框（页眉下的那条线就靠它）──
# OOXML 的边框线型里，「双线」不是一种，而是一族：两条线的**粗细顺序**（上细下粗 /
# 上粗下细 / 等宽）与**间距**（小 / 中 / 大）各有一组取值。这里固定用「中」间距，
# 只把粗细顺序做成可选的写法——间距再拆一档就是三倍词表，实际几乎无人指定。
BOTTOM_BORDER_STYLE = {
    'single': 'single',                    # 一条实线
    'double': 'thinThickMediumGap',        # 双线：上细下粗（学位论文页眉的常见写法）
    'even': 'double',                      # 双线：等宽（看着最轻）
    'thickThin': 'thickThinMediumGap',     # 双线：上粗下细
    'triple': 'thinThickThinMediumGap',    # 三线：细粗细
}
BOTTOM_BORDER_DEFAULT_PT = {'single': 0.5, 'double': 1.5, 'even': 0.5,
                            'thickThin': 1.5, 'triple': 1.0}

# ── 版心宽度（twips）──
# 目录的「点线制表位」要把页码顶到版心右边界，位置得由纸张与页边距算，不能写死：
# 换纸张或改页边距后，写死的制表位会顶出边界或提前断线。
def content_width(width, left, right, gutter=0):
    """版心宽度：纸张宽 − 左边距 − 右边距 − 装订线。

    只统一公式，单位与数据源由调用方负责（写入/读出侧是 twips，校验侧是 cm）。
    """
    return width - left - right - (gutter or 0)


def _content_width_twips(page_size, margins, gutter_cm=None) -> int:
    """正文可用宽度（twips）：纸宽 - 左边距 - 右边距 - 原生装订线。"""
    width_cm = page_size_cm(page_size)[0]
    return int(round(content_width(
        width_cm, margins['left'], margins['right'], gutter_cm) * TWIPS_PER_CM))


def body_line_spacing_multiple(styles) -> float:
    """正文的行距**倍数**——文档网格补偿按它算。

    `styles` 是任一含 `style_name` / `line_spacing` 的序列（写入侧是 `spec.styles`，
    读取侧是解析出来的样式行）。优先「正文」，退回「普通」；固定值行距（`行距20磅`）
    不是倍数、不参与相乘（Word 只把行高向上取整到网格），故返回 1.0。
    """
    for st in styles:
        if st.get('style_name') in ('Body Text', 'Normal'):
            ls = st.get('line_spacing')
            if isinstance(ls, float) and ls > 0:
                return ls
    return 1.0


def _body_height_twips(page_size, margins) -> int:
    _, h_cm = page_size_cm(page_size)
    return int(round((h_cm - margins['top'] - margins['bottom']) * TWIPS_PER_CM))


def doc_grid_pitch(spec, margins) -> int:
    """`文档网格：每页N行` → `w:docGrid/@w:linePitch`（每行多少 twips）。

    写入侧、导出后对账侧共用这一份，免得两边各算一遍、算法漂移还看不出来。
    """
    # **行距的「倍数」会把网格间距再乘一遍**：声明 每页22行 时，配 1.5 倍行距实测只落
    # 14 行、配 2.0 倍只落 11 行（正好是 22÷倍数）。作者要的是「每页 N 行」，就把这个
    # 倍数除掉，让**结果**真的是 N 行——而不是反过来要求他改行距。
    return int(_body_height_twips(spec.page_size, margins)
               / spec.doc_grid_lines / body_line_spacing_multiple(spec.styles))


def doc_grid_lines_from_pitch(pitch: int, line_multiple: float, page_size, margins) -> int:
    """`w:docGrid/@linePitch` → 声明的「每页 N 行」。是 `doc_grid_pitch` 的逆，
    读参考 .docx 时用（把别人模板里的网格反推成本工具的写法）。"""
    return max(1, int(round(_body_height_twips(page_size, margins) / pitch / line_multiple)))


# 单倍行距下，一行中文文字的高度约等于字号的这个倍数（实测小四 12pt → 15.6pt）。
_CJK_LINE_HEIGHT_RATIO = 1.3


def body_line_height_pt(spec) -> float:
    """正文一行实际占多高（磅）：固定值就用那个值，倍数按 1.3×字号 折算。"""
    for name in ('Body Text', 'Normal'):
        style = spec.get_style(name)
        if not style:
            continue
        size = style.get('font_size')
        size_pt = size.pt if hasattr(size, 'pt') else 12.0
        spacing = style.get('line_spacing')
        if hasattr(spacing, 'pt'):
            return float(spacing.pt)  # 固定值 / 最小值：交给 Word 的就是这个磅数
        multiple = spacing if isinstance(spacing, float) and spacing > 0 else 1.0
        return _CJK_LINE_HEIGHT_RATIO * size_pt * multiple
    return _CJK_LINE_HEIGHT_RATIO * 12.0


def max_doc_grid_lines(spec) -> int:
    """声明「每页 N 行」能兑现到几行：版心高度 ÷ 正文行高。

    超过这个数的 N 兑现不了——Word 会把行高向上取整到网格的整数倍，实际行数反而更少，
    产物比不声明网格还差。所以这个数要报给作者，而不是默默按他的 N 排。
    """
    margins = spec.margins or {}
    if not all(k in margins for k in ('top', 'bottom')):
        return 0
    height_pt = _body_height_twips(spec.page_size, margins) / 20.0
    return int(height_pt // body_line_height_pt(spec))

def ensure_ordered_child(parent, tag, order):
    """按 schema 顺序取/建子元素。顺序表外的标签追加在末尾。"""
    el = parent.find(W(tag))
    if el is not None:
        return el
    el = etree.Element(W(tag))
    idx = order.index(tag) if tag in order else len(order)
    for i, ch in enumerate(parent):
        ln = etree.QName(ch).localname
        if ln in order and order.index(ln) > idx:
            parent.insert(i, el)
            return el
    parent.append(el)
    return el


def _neutralize_inherited_first_line(ind):
    """设置悬挂缩进时，显式将继承的首行缩进置零，避免二者冲突。"""
    ind.set(W('firstLineChars'), '0')
    ind.attrib.pop(W('firstLine'), None)


def write_run_props(rpr, props, cjk=None, latin=None):
    """写入字符级属性（字体、字号、加粗、倾斜、颜色）。"""
    if cjk or latin:
        rfonts = ensure_ordered_child(rpr, 'rFonts', _RPR_ORDER)
        if cjk:
            rfonts.set(W('eastAsia'), cjk)
        if latin:
            rfonts.set(W('ascii'), latin)
            rfonts.set(W('hAnsi'), latin)
        clear_font_theme_attrs(rfonts)

    if props.get('font_size'):
        half_pt = str(int(round(props['font_size'].pt * 2)))
        ensure_ordered_child(rpr, 'sz', _RPR_ORDER).set(W('val'), half_pt)
        # 同步复杂文字字号（szCs），保持多语言环境下字号一致
        sz_cs = rpr.find(W('szCs'))
        if sz_cs is not None:
            sz_cs.set(W('val'), half_pt)

    # 显式设置加粗状态（开/关），避免底模样式的加粗属性隐式继承
    if props.get('bold') is not None:
        b = ensure_ordered_child(rpr, 'b', _RPR_ORDER)
        if not props['bold']:
            b.set(W('val'), '0')
        else:
            b.attrib.pop(W('val'), None)
        b_cs = rpr.find(W('bCs'))
        if b_cs is not None:
            if not props['bold']:
                b_cs.set(W('val'), '0')
            else:
                b_cs.attrib.pop(W('val'), None)

    # 显式设置倾斜状态（开/关），避免底模样式的倾斜属性隐式继承
    if props.get('italic') is not None:
        it = ensure_ordered_child(rpr, 'i', _RPR_ORDER)
        if not props['italic']:
            it.set(W('val'), '0')
        else:
            it.attrib.pop(W('val'), None)
        it_cs = rpr.find(W('iCs'))
        if it_cs is not None:
            if not props['italic']:
                it_cs.set(W('val'), '0')
            else:
                it_cs.attrib.pop(W('val'), None)

    # 颜色：要求文件写了「颜色#RRGGBB」就用它，没写一律黑色。同时清除主题色，
    # 以及底模可能残留的字符间距加宽（spacing）与字距调整（kern）。
    color = ensure_ordered_child(rpr, 'color', _RPR_ORDER)
    color.set(W('val'), props.get('color') or '000000')
    clear_color_theme_attrs(color)
    for tag in ('spacing', 'kern'):
        el = rpr.find(W(tag))
        if el is not None:
            rpr.remove(el)
    # 作者写了「字距N磅」才写回去（val 单位是 1/20 磅）
    if props.get('char_spacing_pt'):
        sp = ensure_ordered_child(rpr, 'spacing', _RPR_ORDER)
        sp.set(W('val'), str(int(round(props['char_spacing_pt'] * 20))))


def write_para_props(ppr, props):
    """把**段落级**属性写进任意 pPr 容器（样式 pPr，或 w:tblStylePr/pPr）。"""
    if props.get('alignment') is not None:
        jc = ensure_ordered_child(ppr, 'jc', _PPR_ORDER)
        jc.set(W('val'), ALIGN_ENUM_VAL.get(props['alignment'], 'left'))

    spacing = None
    if props.get('line_spacing') is not None:
        spacing = ensure_ordered_child(ppr, 'spacing', _PPR_ORDER)
        ls = props['line_spacing']
        if isinstance(ls, MinLineSpacing):
            spacing.set(W('line'), str(int(round(ls.pt * 20))))
            spacing.set(W('lineRule'), 'atLeast')
        elif isinstance(ls, Pt):
            spacing.set(W('line'), str(int(round(ls.pt * 20))))
            spacing.set(W('lineRule'), 'exact')
        else:
            spacing.set(W('line'), str(int(round(float(ls) * 240))))
            spacing.set(W('lineRule'), 'auto')

    if 'space_before' in props:
        spacing = spacing if spacing is not None else ensure_ordered_child(ppr, 'spacing', _PPR_ORDER)
        spacing.set(W('before'), str(int(round(props['space_before'].pt * 20))))
    if 'space_after' in props:
        spacing = spacing if spacing is not None else ensure_ordered_child(ppr, 'spacing', _PPR_ORDER)
        spacing.set(W('after'), str(int(round(props['space_after'].pt * 20))))

    if props.get('left_indent_chars') is not None:
        ind = ensure_ordered_child(ppr, 'ind', _PPR_ORDER)
        ind.set(W('leftChars'), str(int(props['left_indent_chars'] * 100)))
        ind.attrib.pop(W('left'), None)

    if props.get('dot_leader_tab'):
        tabs = ensure_ordered_child(ppr, 'tabs', _PPR_ORDER)
        for old in tabs.findall(W('tab')):
            tabs.remove(old)
        tab = etree.SubElement(tabs, W('tab'))
        tab.set(W('val'), 'right')
        tab.set(W('leader'), 'dot')
        tab.set(W('pos'), str(props['dot_leader_pos']))

    if props.get('join_toc') is True:
        outline = ensure_ordered_child(ppr, 'outlineLvl', _PPR_ORDER)
        outline.set(W('val'), '0')
    elif props.get('join_toc') is False:
        outline = ensure_ordered_child(ppr, 'outlineLvl', _PPR_ORDER)
        outline.set(W('val'), '9')

    if props.get('keep_next'):
        ensure_ordered_child(ppr, 'keepNext', _PPR_ORDER)
    if props.get('keep_lines'):
        ensure_ordered_child(ppr, 'keepLines', _PPR_ORDER)
    if props.get('page_break_before'):
        ensure_ordered_child(ppr, 'pageBreakBefore', _PPR_ORDER)
    if props.get('widow_control') is not None:
        wc = ensure_ordered_child(ppr, 'widowControl', _PPR_ORDER)
        wc.set(W('val'), '1' if props['widow_control'] else '0')

    if props.get('no_border') or props.get('bottom_border') == 'none':
        p_bdr = ppr.find(W('pBdr'))
        if p_bdr is not None:
            ppr.remove(p_bdr)

    if props.get('bottom_border') in BOTTOM_BORDER_STYLE:
        p_bdr = ppr.find(W('pBdr'))
        if p_bdr is None:
            p_bdr = ensure_ordered_child(ppr, 'pBdr', _PPR_ORDER)
        old = p_bdr.find(W('bottom'))
        if old is not None:
            p_bdr.remove(old)
        bot = etree.SubElement(p_bdr, W('bottom'))
        bot.set(W('val'), BOTTOM_BORDER_STYLE[props['bottom_border']])
        bot.set(W('sz'), _pt_to_border_sz(props.get('border_width_pt', BOTTOM_BORDER_DEFAULT_PT[props['bottom_border']])))
        bot.set(W('space'), '1')
        bot.set(W('color'), 'auto')

    if props.get('indent') is not None:
        ind = ensure_ordered_child(ppr, 'ind', _PPR_ORDER)
        indent_type = props['indent_type']
        indent_val = props['indent']
        # 「左缩进」与「悬挂缩进」是 `w:ind` 上**两个不同的属性**（left/leftChars 是段落
        # 整体左移，hanging/hangingChars 只是首行相对回退），写悬挂时顺手把 left 也设成
        # 同一个值，只是为了让「没写左缩进」的悬挂缩进（英文参考文献那种）首行落在 0。
        # 作者显式写了左缩进时，那个值必须留着——两行都写是合法组合，不是冲突。
        has_left = props.get('left_indent_chars') is not None
        if props.get('indent_unit', 'pt') == 'chars':
            # 字符单位用 firstLineChars/hangingChars，Word 根据段落字号自动换算实际缩进，
            # 字号变化时比例自动保持；与 firstLine（绝对 pt）不同，故两者互斥地清掉一个。
            if indent_type == 'first_line':
                ind.set(W('firstLineChars'), str(int(indent_val * 100)))
                ind.attrib.pop(W('firstLine'), None)
            elif indent_type == 'hanging':
                ind.set(W('hangingChars'), str(int(indent_val * 100)))
                if not has_left:
                    ind.set(W('leftChars'), str(int(indent_val * 100)))
                    ind.attrib.pop(W('left'), None)
                _neutralize_inherited_first_line(ind)
                ind.attrib.pop(W('hanging'), None)
        else:
            twips = str(int(round(indent_val * 20)))  # indent_val 单位为 pt
            if indent_type == 'first_line':
                ind.set(W('firstLine'), twips)
                ind.attrib.pop(W('firstLineChars'), None)
            elif indent_type == 'hanging':
                ind.set(W('hanging'), twips)
                if not has_left:
                    ind.set(W('left'), twips)
                    ind.attrib.pop(W('leftChars'), None)
                _neutralize_inherited_first_line(ind)
                ind.attrib.pop(W('hangingChars'), None)


class TemplateError(ValueError):
    """格式要求或模板无法生成。

    作为库调用时（`run_export_pipeline`、`build_template`）必须抛这个异常，不能
    `sys.exit`：调用方的进程不该被一份写错的格式文件直接终结。
    """


# ── 样式操作函数 ──

# Word 内置的目录条目样式：styleId = TOC1…TOC5，名字是小写的 "toc 1/2/3"，
# 且**不能带 `w:customStyle="1"`**。带了这个标记，Word 就把它们当用户自建样式，
# 更新目录域时会按自己的内置默认重建，我们写的字体/字号/加粗全部丢失。
_BUILTIN_TOC = {
    f"TOC {n}": (f"TOC{n}", f"toc {n}") for n in range(1, 6)
}


def _ensure_builtin_toc_style(style, style_name: str) -> None:
    """把目录条目样式写成 Word 的**内置**样式，而不是自建样式。"""
    builtin = _BUILTIN_TOC.get(style_name)
    if builtin is None:
        return
    style_id, name = builtin
    element = style.element
    element.attrib.pop(W('customStyle'), None)
    element.set(W('styleId'), style_id)
    name_el = element.find(W('name'))
    if name_el is None:
        name_el = etree.SubElement(element, W('name'))
    name_el.set(W('val'), name)


def _find_style(doc, name: str):
    """按名字或 styleId 找样式。

    目录条目会被改写成 Word 的内置样式（`TOC 1` → 名 `toc 1`、id `TOC1`），此后按
    名字就查不到了。python-docx 的 `doc.styles[name]` 会退回按 id 查、并对这种用法发
    弃用警告——每次导出刷一屏无关警告。这里自己按「名字或 id」找，不触发那条路径。
    """
    for style in doc.styles:
        if style.name == name or style.style_id == name:
            return style
    return None


def modify_style(doc, style_name, props, default_latin=None):
    """修改或创建样式的属性"""
    style = _find_style(doc, style_name)
    if style is None:
        style = doc.styles.add_style(style_name, WD_STYLE_TYPE.PARAGRAPH)
        try:
            normal_style = doc.styles['Normal']
            style.base_style = normal_style
        except KeyError:
            pass
        logger.debug(f' ✓ {style_name}: 已创建新样式（basedOn Normal）')

    _ensure_builtin_toc_style(style, style_name)

    cjk, latin = split_fonts(props.get('font_name'), default_latin)
    if not cjk and not latin and default_latin:
        latin = default_latin

    rpr = ensure_rpr(style.element)
    ppr = ensure_ordered_child(style.element, 'pPr', _STYLE_ORDER)

    if props.get('no_border') and ppr.find(W('pBdr')) is not None:
        logger.debug(f' ✓ {style_name}: 已去除段落边框')

    write_run_props(rpr, props, cjk=cjk, latin=latin)
    write_para_props(ppr, props)

    # 同步更新关联的字符样式（w:link），保证段落与字符级属性一致
    link_el = style.element.find(W('link'))
    if link_el is not None:
        link_id = link_el.attrib.get(W('val'))
        parent = style.element.getparent()
        if link_id and parent is not None:
            for s in parent.findall(W('style')):
                if s.attrib.get(W('styleId')) == link_id:
                    link_rpr = ensure_rpr(s)
                    write_run_props(link_rpr, props, cjk=cjk, latin=latin)
                    break

    logger.debug(f' ✓ {style_name}: 已应用修改')
    return True


def apply_proofing_language(doc, lang):
    """把校对语言写进 docDefaults。

    只设 `eastAsia` 槽（中文、日文这些字符用的槽）——西文槽保持底模的 en-US，
    否则中文文档里的英文词会被拿去按中文词典查。底模两个槽都是 en-US，不写中文
    语言，Word 就用英文词典查中文，整篇标成拼写错误。
    """
    root = doc.styles.element
    defaults = root.find(W('docDefaults'))
    if defaults is None:
        defaults = etree.Element(W('docDefaults'))
        root.insert(0, defaults)
    rpr_default = ensure_ordered_child(defaults, 'rPrDefault', ['rPrDefault', 'pPrDefault'])
    rpr = ensure_ordered_child(rpr_default, 'rPr', ['rPr'])
    lang_el = ensure_ordered_child(rpr, 'lang', _RPR_ORDER)
    lang_el.set(W('eastAsia'), lang)


def resolve_punctuation_compression(mode: str | None, proofing_lang: str | None = None) -> str:
    """确定标点压缩模式：显式声明优先，否则按校对语言推导默认值。

    - zh-TW / zh-HK / zh-MO / zh-hant（繁体全角标点居中）及非中日韩语种默认 doNotCompress；
    - 其余 zh*（如 zh-CN / zh-SG）默认 compressPunctuation；
    - ja* 默认 compressPunctuationAndJapaneseKana。
    """
    if mode in ('compressPunctuation', 'doNotCompress', 'compressPunctuationAndJapaneseKana'):
        return mode
    tag = (proofing_lang or '').strip().lower().replace('_', '-')
    if tag.startswith(('zh-tw', 'zh-hk', 'zh-mo', 'zh-hant')):
        return 'doNotCompress'
    if tag.startswith('zh'):
        return 'compressPunctuation'
    if tag.startswith('ja'):
        return 'compressPunctuationAndJapaneseKana'
    return 'doNotCompress'


def apply_punctuation_compression(doc, mode: str | None = None, proofing_lang: str | None = None) -> str:
    """把标点压缩模式写进 settings.xml/w:characterSpacingControl。"""
    want = resolve_punctuation_compression(mode, proofing_lang)
    node = ensure_ordered_child(doc.settings.element, 'characterSpacingControl', _SETTINGS_ORDER)
    node.set(W('val'), want)
    return want


def apply_mirror_margins(doc, enabled: bool) -> None:
    """把对称页边距开关写进 settings.xml/w:mirrorMargins。"""
    el = doc.settings.element.find(W('mirrorMargins'))
    if enabled:
        if el is None:
            ensure_ordered_child(doc.settings.element, 'mirrorMargins', _SETTINGS_ORDER)
    elif el is not None:
        doc.settings.element.remove(el)


def _props_from_req(req, page_size, margins, gutter_cm=None):
    """样式行解析结果 → modify_style 吃的那份属性 dict。

    唯一一份：主循环与脚注默认都走这里，免得两条路上的可选属性各自漏一项。
    """
    props = {
        'font_name': req.get('font_name'),
        'font_size': req.get('font_size'),
        'bold': req.get('bold', False),
        'italic': req.get('italic', False),
        'alignment': req.get('alignment'),
        'line_spacing': req.get('line_spacing'),
        'indent': req.get('indent'),
        'indent_type': req.get('indent_type'),
        'indent_unit': req.get('indent_unit', 'pt'),
    }
    for key in ('space_before', 'space_after', 'no_border', 'bottom_border',
                'border_width_pt', 'left_indent_chars', 'char_spacing_pt', 'color',
                'keep_lines', 'page_break_before', 'widow_control'):
        if key in req:
            props[key] = req[key]
    if req.get('dot_leader_tab'):
        props['dot_leader_tab'] = True
        props['dot_leader_pos'] = _content_width_twips(page_size, margins, gutter_cm=gutter_cm)
    if 'join_toc' in req:
        props['join_toc'] = bool(req['join_toc'])
    if 'join_header' in req:
        props['join_header'] = bool(req['join_header'])
    if req.get('keep_next'):
        props['keep_next'] = True
    return props


def _pt_to_border_sz(pt):
    """磅 → OOXML 边框 sz（1/8 磅），下限 2（1/4 磅，Word 最细单实线）"""
    return str(max(2, int(round(pt * 8))))

