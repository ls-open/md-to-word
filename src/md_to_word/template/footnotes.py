"""脚注两个样式：默认参数与序号上标。"""

from __future__ import annotations

from docx.enum.style import WD_STYLE_TYPE

from md_to_word.spec.constants import ALIGN_CN, SIZE_MAP, W
from md_to_word.spec.parser import parse_style_props
from md_to_word.template.core import (
    _RPR_ORDER, _props_from_req, ensure_ordered_child, ensure_rpr,
    logger, modify_style,
)

# ── 脚注的两个样式 ──
# 脚注段落与脚注序号是渲染器**一定会打标记**的结构（`FootnoteText` / `FootnoteReference`），
# 而标记指不到定义时，OOXML 里不是"无格式"，是落到默认段落样式 Normal——也就是正文那一套
# （实测：脚注与正文同为 12pt、序号不是上标）。所以这两个样式**写没写要求文件都要落定义**。
_FOOTNOTE_STYLE = 'Footnote Text'
_FOOTNOTE_REF_STYLE = 'Footnote Reference'


def _footnote_default_line(spec) -> str:
    """没写「脚注：」时的默认样式行：字体与对齐跟着正文走，字号按 SIZE_MAP 降一档。

    降一档的依据是本工具自己的排版原则（注释比正文小 1.5~2 磅）：小四正文 → 五号脚注。
    行距单倍、段前后 0、首行缩进 0——脚注是几行的注释，跟正文同为两端对齐时再带
    2 字符首行缩进会顶成锯齿。
    """
    body = next((r for r in spec.styles if r.get('style_name') == 'Body Text'), None) or {}
    fonts = '/'.join(body.get('font_name') or ['宋体', 'Times New Roman'])
    align = ALIGN_CN.get(body.get('alignment') or '', '两端对齐')
    size_pt = (body.get('font_size') or SIZE_MAP['小四']).pt
    size_name = next((name for name, sz in SIZE_MAP.items() if sz.pt < size_pt), '八号')
    return (f'{fonts} {size_name} 不加粗 不倾斜 {align} '
            f'行距1.0倍 段前0磅 段后0磅 首行缩进0字符')


def apply_footnote_format(doc, spec, page_size, margins, default_latin=None, gutter_cm=None):
    """给两个脚注样式落定义：写了「脚注：」用写的，没写从正文推一套默认。

    另：脚注序号唯一要紧的属性是**上标**——不设它，正文里的序号就是个大号数字，
    读起来和普通数字分不开。
    """
    declared = any(r.get('style_name') == _FOOTNOTE_STYLE for r in spec.styles)
    if not declared:
        req = parse_style_props(_FOOTNOTE_STYLE, _footnote_default_line(spec))
        modify_style(doc, _FOOTNOTE_STYLE,
                     _props_from_req(req, page_size, margins, gutter_cm=gutter_cm),
                     default_latin=default_latin)
        logger.debug(f' ✓ {_FOOTNOTE_STYLE}: 要求文件未写「脚注」，已按正文推定默认')

    try:
        ref = doc.styles[_FOOTNOTE_REF_STYLE]
    except KeyError:
        ref = doc.styles.add_style(_FOOTNOTE_REF_STYLE, WD_STYLE_TYPE.CHARACTER)
    va = ensure_ordered_child(ensure_rpr(ref.element), 'vertAlign', _RPR_ORDER)
    va.set(W('val'), 'superscript')
    logger.debug(f' ✓ {_FOOTNOTE_REF_STYLE}: 已设为上标')

