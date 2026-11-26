"""表格样式、条件格式与边框。"""

from __future__ import annotations

from lxml import etree

from md_to_word.i18n import t
from md_to_word.spec.constants import TWIPS_PER_CM, W, split_fonts
from md_to_word.template.core import (
    TemplateError, _STYLE_ORDER, _TBLPR_ORDER, _TBLSTYLEPR_ORDER, _TCPR_ORDER,
    _pt_to_border_sz, ensure_ordered_child, logger,
    write_para_props, write_run_props,
)

# ══════════════════════════════════════════════════════════════════
#  表格
#
#  表内所有段落都映射为 Compact 样式，字体字号缩进由「紧凑：」那一行控制；表头行与
#  单元格无法用段落样式区分，只能写进 Table 样式的条件格式（tblStylePr firstRow /
#  wholeTable）。
#
#  ⚠ 条件格式里边框走 tcPr、字符/段落属性走 rPr/pPr；容器写错的那部分静默不生效，
#    而模板 XML 看上去完全正常。
# ══════════════════════════════════════════════════════════════════

# 各边框样式的默认线宽（磅）——与历史行为一致，未显式声明时用它
TABLE_DEFAULT_WIDTHS = {
    'three-line': {'top': 1.5, 'bottom': 1.5, 'header_bottom': 0.75},
    'grid': {'inside': 0.5},
    'top-bottom': {'top': 1.5, 'bottom': 1.5},
}

TABLE_BORDER_SIDES = ('top', 'left', 'bottom', 'right', 'insideH', 'insideV')

# ── 表格单元格内边距 ──
# 默认跟 Word 的 Normal Table 一致：左右 0.19cm、上下 0。上下留 0 是为了不把行撑高，
# 左右留一点是为了三线表没有竖线时相邻列的文字不粘在一起。显式写
# 「单元格内边距Ncm」时仍按四周同一个值处理，想四周留白就写出来。
TABLE_CELL_MARGIN_DEFAULT_LR_CM = 0.19
TABLE_CELL_MARGIN_DEFAULT_TB_CM = 0.0


def cell_margin_twips(table: dict | None = None) -> dict[str, int]:
    """单元格四边内边距（twips）：显式声明按四周同值，否则用 Word 的左右 0.19 / 上下 0。"""
    if table and 'cell_margin_cm' in table:
        value = int(round(float(table['cell_margin_cm']) * TWIPS_PER_CM))
        return {side: value for side in ('top', 'left', 'bottom', 'right')}
    lr = int(round(TABLE_CELL_MARGIN_DEFAULT_LR_CM * TWIPS_PER_CM))
    tb = int(round(TABLE_CELL_MARGIN_DEFAULT_TB_CM * TWIPS_PER_CM))
    return {'top': tb, 'left': lr, 'bottom': tb, 'right': lr}


def table_border_widths(style: str, declared: dict) -> dict:
    """表格样式 + 要求文件声明的线宽 → {边: 磅值，None = 不画线}。

    **生成（写 XML）与导出后对账（读 XML）都从这里取期望值**：两边各推一次时，
    「全网格线的上下外框能不能单独加粗」这种细节会两处不一致——对账按 `线宽内` 取期望，
    于是把"写了 `线宽上` 却不生效"的产物判成通过。
    """
    w = dict(TABLE_DEFAULT_WIDTHS.get(style, {}))
    w.update(declared or {})
    if style == 'three-line':
        return {'top': w.get('top', 1.5), 'bottom': w.get('bottom', 1.5),
                'left': None, 'right': None, 'insideH': None, 'insideV': None}
    if style == 'top-bottom':
        return {side: (w.get(side, 1.5) if side in ('top', 'bottom') else None)
                for side in TABLE_BORDER_SIDES}
    if style == 'grid':
        # 全网格线：上下外框可单独加粗（`线宽上`/`线宽底`），左右与内部横竖线用 `线宽内`
        line = w.get('inside', 0.5)
        return {'top': w.get('top', line), 'bottom': w.get('bottom', line),
                'left': line, 'right': line, 'insideH': line, 'insideV': line}
    return {}


def _get_tbl_style_pr(style_element, cond_type):
    """取/建 w:tblStylePr[type=…]。同类型只能有一个，边框与表头格式共用它。"""
    for el in style_element.findall(W('tblStylePr')):
        if el.get(W('type')) == cond_type:
            return el
    el = etree.SubElement(style_element, W('tblStylePr'))
    el.set(W('type'), cond_type)
    return el


def _add_border(parent, side, sz='none'):
    el = etree.SubElement(parent, W(side))
    if sz == 'none':
        el.set(W('val'), 'none')
    else:
        el.set(W('val'), 'single')
        el.set(W('sz'), sz)
        el.set(W('space'), '0')
        el.set(W('color'), '000000')


def _write_borders(tbl_pr, sides):
    """把 w:tblBorders 重建到 tbl_pr（幂等）。

    `sides` 是 {边: 线宽磅|'none'}，**只写列出的边**。
    条件格式（tblStylePr）里的 tblBorders 是**按边覆盖**的：没列出的边会继承
    全表边框；若在此处补一圈 'none'，反而会把三线表的顶线/底线抹掉。
    """
    old = tbl_pr.find(W('tblBorders'))
    if old is not None:
        tbl_pr.remove(old)
    borders = ensure_ordered_child(tbl_pr, 'tblBorders', _TBLPR_ORDER)
    for side, width in sides.items():
        _add_border(borders, side, 'none' if width is None else _pt_to_border_sz(width))
    return borders


def _write_cell_borders(tbl_style_pr, sides):
    """把边框写进条件格式的 `tcPr/tcBorders`（**单元格级**）。

    ⚠ 条件格式（tblStylePr）里的边框**只能**走这里，不能走 `tblPr/tblBorders`：
    写在表级会被全表 `tblBorders` 的 `insideH="none"` 压掉，Word 渲染时那条线
    根本不出现——而 XML 看上去完全正常。实测三线表的表头下线：写表级 → 只有
    上下两条线；写单元格级 → 三条线齐。
    （同一个条件格式里的 `pPr`/`rPr`——对齐、字体——一直是正常生效的，
      所以只改边框这一处、不逐条渲染核对，极易漏判成"三线表没问题"。）
    """
    tc_pr = ensure_ordered_child(tbl_style_pr, 'tcPr', _TBLSTYLEPR_ORDER)
    old = tc_pr.find(W('tcBorders'))
    if old is not None:
        tc_pr.remove(old)
    borders = ensure_ordered_child(tc_pr, 'tcBorders', _TCPR_ORDER)
    for side, width in sides.items():
        _add_border(borders, side, 'none' if width is None else _pt_to_border_sz(width))
    return borders


def apply_table_format(doc, spec, default_latin=None, lang: str = "zh"):
    """写 Table 样式：对齐、边框（含三线表线宽）、表头行条件格式、单元格垂直对齐"""
    table = spec.table or {}
    table_align = table.get('align', 'center')
    table_style = table.get('style') or 'three-line'
    if table_style not in ('three-line', 'grid', 'top-bottom', 'none'):
        raise TemplateError(t('template.table_style_unsupported', lang, style=table_style))
    # 线宽旋钮只在**画得出来**的地方有意义：声明了却不生效比报错难查得多。
    declared_widths = table.get('widths') or {}
    if declared_widths and table_style == 'none':
        raise TemplateError(t('template.table_widths_without_lines', lang, widths=declared_widths))
    # 「线宽内」只对全网格线有意义：三线表/顶底线按定义没有内部横线，写了也不会生效。
    if 'inside' in declared_widths and table_style in ('three-line', 'top-bottom'):
        raise TemplateError(t('template.table_no_inside_line', lang, style=table_style))

    try:
        style_el = doc.styles['Table'].element
    except KeyError:
        logger.warning(t('template.table_style_missing', lang))
        return

    tbl_pr = ensure_ordered_child(style_el, 'tblPr', _STYLE_ORDER)

    # jc 必须排在 tblBorders 之前，否则 Word 忽略 jc（表格仍左对齐）
    old_jc = tbl_pr.find(W('jc'))
    if old_jc is not None:
        tbl_pr.remove(old_jc)
    jc_el = ensure_ordered_child(tbl_pr, 'jc', _TBLPR_ORDER)
    jc_el.set(W('val'), table_align)
    logger.debug(f' ✓ Table: 表格对齐={table_align}（通过 Table 样式 jc 控制）')

    if table_style != 'none':
        declared = table.get('widths', {})
        widths = dict(TABLE_DEFAULT_WIDTHS.get(table_style, {}))
        widths.update(declared)                    # 格式文件显式声明的线宽覆盖默认
        style_names = {'three-line': '三线表', 'grid': '全网格线', 'top-bottom': '顶底线'}
        logger.debug(f' ✓ Table: 已应用{style_names.get(table_style, table_style)}边框'
              + (f'（线宽 {widths} 磅）' if declared else ''))
        _write_borders(tbl_pr, table_border_widths(table_style, declared))

        # 表头下线属「表头行」条件区域，必须写到**单元格级**（表级会被 insideH 压掉）。
        # 三线表按定义就该有这条线（默认 0.75 磅）；全网格线只有显式声明才写，
        # 否则表头那条线会跟周围网格线不一样粗。
        if table_style == 'three-line' or 'header_bottom' in declared:
            _write_cell_borders(_get_tbl_style_pr(style_el, 'firstRow'),
                                {'bottom': widths.get('header_bottom', 0.75)})

    # ── 表头行格式（复用段落的属性写入器，只是容器换成 tblStylePr）──
    if spec.table_header:
        props = spec.table_header
        cjk, latin = split_fonts(props.get('font_name'), default_latin)
        tsp = _get_tbl_style_pr(style_el, 'firstRow')
        write_run_props(ensure_ordered_child(tsp, 'rPr', _TBLSTYLEPR_ORDER), props, cjk=cjk, latin=latin)
        write_para_props(ensure_ordered_child(tsp, 'pPr', _TBLSTYLEPR_ORDER), props)
        # 「跨页重复」不在这里写：`w:tblHeader` 是行属性，Word 只认正文第一行上的那份
        # （写出器按 spec.table_header.repeat_header 补）。
        logger.debug(' ✓ Table: 已设置表头行格式')

    # 单元格内边距：不写时跟 Word 默认（左右 0.19、上下 0）；写了「单元格内边距」按
    # 四周同值。无论声明与否都**写进产物**，不让底模的继承链替我们决定。
    margins = cell_margin_twips(table)
    cell_mar = ensure_ordered_child(tbl_pr, 'tblCellMar', _TBLPR_ORDER)
    for side in ('top', 'left', 'bottom', 'right'):
        el = ensure_ordered_child(cell_mar, side, ('top', 'left', 'bottom', 'right'))
        el.set(W('w'), str(margins[side]))
        el.set(W('type'), 'dxa')
    if 'cell_margin_cm' in table:
        logger.debug(f' ✓ Table: 单元格内边距={table["cell_margin_cm"]}cm')

    if table.get('valign'):
        tsp = _get_tbl_style_pr(style_el, 'wholeTable')
        tc_pr = ensure_ordered_child(tsp, 'tcPr', _TBLSTYLEPR_ORDER)
        ensure_ordered_child(tc_pr, 'vAlign', _TCPR_ORDER).set(W('val'), table['valign'])
        logger.debug(f' ✓ Table: 单元格垂直对齐={table["valign"]}')

