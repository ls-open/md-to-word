"""md_to_word.preprocessor.markers — 目录域与分节块的 OOXML 片段。

`{{< toc >}}` 与 `{{< section … >}}` 由读取器识别成模型节点，写出器来这里取 XML 片段。
"""

from __future__ import annotations

import copy
from typing import Optional

from lxml import etree

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{" + _NS + "}"

_SECTPR_ORDER = (
    "headerReference",
    "footerReference",
    "footnotePr",
    "endnotePr",
    "type",
    "pgSz",
    "pgMar",
    "paperSrc",
    "pgBorders",
    "lnNumType",
    "pgNumType",
    "cols",
    "formProt",
    "vAlign",
    "noEndnote",
    "titlePg",
    "textDirection",
    "bidi",
    "rtlGutter",
    "docGrid",
    "printerSettings",
)

_MAX_TOC_DEPTH = 9


class MarkerError(Exception):
    """标记语法错误。"""


def _insert_ordered(parent, element, tag: str) -> None:
    idx = _SECTPR_ORDER.index(tag)
    for child in parent:
        name = etree.QName(child).localname
        if name in _SECTPR_ORDER and _SECTPR_ORDER.index(name) > idx:
            child.addprevious(element)
            return
    parent.append(element)



def toc_xml(level: Optional[int] = None) -> str:
    """目录域（`w:sdt` 内的 TOC 域代码），供写出器直接插入文档树。"""
    depth = level if level is not None else 3
    if not 1 <= depth <= _MAX_TOC_DEPTH:
        raise MarkerError(f"目录收录级数要在 1–{_MAX_TOC_DEPTH} 之间，收到 {depth}")
    # 前后各留一个空格：与 Word 自己写出的域代码同形，也让两条流水线的产物逐字节可比。
    instr = f' TOC \\o "1-{depth}" \\h \\z \\u '
    return (
        '<w:sdt xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:sdtPr><w:docPartObj>'
        '<w:docPartGallery w:val="Table of Contents"/><w:docPartUnique/>'
        "</w:docPartObj></w:sdtPr><w:sdtContent>"
        '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve">{instr}</w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        "<w:r><w:t>（打开文档后目录会自动生成）</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        "</w:sdtContent></w:sdt>"
    )





def section_paragraph_xml(params: dict, template_sect) -> str:
    """分节段落：pPr 里挂 sectPr，结束它上面那一节。"""
    sect = (
        copy.deepcopy(template_sect)
        if template_sect is not None
        else etree.Element(_W + "sectPr", nsmap={"w": _NS})
    )
    for tag in ("headerReference", "titlePg", "type", "pgNumType"):
        for el in sect.findall(_W + tag):
            sect.remove(el)

    type_el = etree.Element(_W + "type")
    type_el.set(_W + "val", "nextPage")
    _insert_ordered(sect, type_el, "type")

    pg = etree.Element(_W + "pgNumType")
    if "fmt" in params:
        pg.set(_W + "fmt", params["fmt"])
    if "start" in params:
        pg.set(_W + "start", str(params["start"]))
    _insert_ordered(sect, pg, "pgNumType")

    # 外层 p/pPr 也带命名空间声明：sectPr 上的声明只覆盖它自己，外层没有 w 前缀会解析失败
    return (
        f'<w:p xmlns:w="{_NS}"><w:pPr>'
        + etree.tostring(sect, encoding="unicode")
        + "</w:pPr></w:p>"
    )



