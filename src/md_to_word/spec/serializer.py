"""md_to_word.spec.serializer — TemplateSpec → 格式要求文本。

存在的意义是让 `parse_requirements` 与 `build_template` 能真正组合起来：
解析出来的 spec 可以直接拿去生成模板，不必回头再找原始文本。

写法一律用**正典**（`行距1.5倍`、`首行缩进2字符`），数字字号统一写成 `12pt`——
往返等价的判据是「再解析一遍得到同一个 spec」，不是「字节相同」。
"""

from __future__ import annotations

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt

from md_to_word.spec.models import MinLineSpacing, TemplateSpec

_ALIGN_TEXT = {
    WD_ALIGN_PARAGRAPH.CENTER: "居中",
    WD_ALIGN_PARAGRAPH.LEFT: "左对齐",
    WD_ALIGN_PARAGRAPH.RIGHT: "右对齐",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "两端对齐",
}
_TABLE_ALIGN = {"center": "居中", "left": "左对齐", "right": "右对齐"}
_TABLE_STYLE = {"three-line": "三线表", "grid": "全网格线", "top-bottom": "顶底线", "none": "无边框"}
_TABLE_VALIGN = {"center": "单元格垂直居中", "top": "单元格垂直顶端", "bottom": "单元格垂直底端"}
_BORDER_SIDE = {"top": "线宽上", "bottom": "线宽底", "header_bottom": "线宽表头下", "inside": "线宽内"}


def _pt(value) -> float:
    return round(value.pt if isinstance(value, Pt) else float(value), 2)


def _style_line(style: dict) -> str:
    parts: list[str] = []

    font = style.get("font_name")
    if font:
        parts.append("/".join(font) if len(font) > 1 else font[0])

    size = style.get("font_size")
    if size is not None:
        parts.append(f"{_pt(size):g}pt")

    if "bold" in style:
        parts.append("加粗" if style["bold"] else "不加粗")
    if "italic" in style:
        parts.append("倾斜" if style["italic"] else "不倾斜")

    align = style.get("alignment")
    if align is not None:
        parts.append(_ALIGN_TEXT.get(align, "左对齐"))

    spacing = style.get("line_spacing")
    if isinstance(spacing, MinLineSpacing):
        parts.append(f"行距最小值{spacing.pt:g}磅")
    elif isinstance(spacing, Pt):
        parts.append(f"行距{_pt(spacing):g}磅")
    elif spacing is not None:
        parts.append(f"行距{float(spacing):g}倍")

    if style.get("space_before") is not None:
        parts.append(f"段前{_pt(style['space_before']):g}磅")
    if style.get("space_after") is not None:
        parts.append(f"段后{_pt(style['space_after']):g}磅")

    indent = style.get("indent")
    if indent is not None:
        kind = "悬挂缩进" if style.get("indent_type") == "hanging" else "首行缩进"
        if style.get("indent_unit") == "pt":
            parts.append(f"{kind}{float(indent) / 72:g}英寸")
        else:
            parts.append(f"{kind}{float(indent):g}字符")

    if "left_indent_chars" in style:  # 0 也是显式声明，不能当没写
        parts.append(f"左缩进{float(style['left_indent_chars']):g}字符")
    if style.get("repeat_header"):
        parts.append("跨页重复")
    if style.get("keep_next"):
        parts.append("与下段同页")

    return f"{style['style_name']}：" + " ".join(parts)


def _table_line(table: dict) -> str:
    parts: list[str] = []
    if table.get("align"):
        parts.append(_TABLE_ALIGN.get(table["align"], "居中"))
    if table.get("style"):
        parts.append(_TABLE_STYLE.get(table["style"], "三线表"))
    for side, width in (table.get("widths") or {}).items():
        if side in _BORDER_SIDE:
            parts.append(f"{_BORDER_SIDE[side]}{float(width):g}磅")
    if table.get("valign"):
        parts.append(_TABLE_VALIGN.get(table["valign"], "单元格垂直居中"))
    return "表格：" + " ".join(parts)


def serialize_requirements(spec: TemplateSpec) -> str:
    """把 TemplateSpec 写回格式要求文本（正典写法）。"""
    lines: list[str] = [f"# schema: {spec.schema_version}"]

    lines.append(f"纸张：{spec.page_size.upper() if spec.page_size == 'letter' else spec.page_size}")
    if spec.margins:
        lines.append(
            "页边距：上{m[top]:g}cm 下{m[bottom]:g}cm 左{m[left]:g}cm 右{m[right]:g}cm".format(
                m=spec.margins
            )
        )
    if spec.gutter_cm:
        lines.append(f"装订线：{spec.gutter_cm:g}cm")
    if spec.default_latin:
        lines.append(f"西文字体：{spec.default_latin}")
    if spec.proofing_lang:
        lines.append(f"校对语言：{spec.proofing_lang}")
    if spec.doc_grid_lines:
        lines.append(f"文档网格：每页{spec.doc_grid_lines}行")

    for style in spec.styles:
        lines.append(_style_line(style))
    if spec.table:
        lines.append(_table_line(spec.table))
    if spec.table_header:
        lines.append(_style_line(spec.table_header))

    return "\n".join(lines) + "\n"
