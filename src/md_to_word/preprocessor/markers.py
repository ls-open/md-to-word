"""md_to_word.preprocessor.markers — 目录域与分节块的 OOXML 片段。

`{{< toc >}}` 与 `{{< section … >}}` 由读取器识别成模型节点，写出器来这里取 XML 片段。
"""

from __future__ import annotations

import copy
from typing import Optional
from xml.sax.saxutils import escape

from lxml import etree
from md_to_word.i18n import t
from md_to_word.template.core import _SECTPR_ORDER

_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W = "{" + _NS + "}"

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



def toc_xml(level: Optional[int] = None, lang: str = "zh") -> str:
    """目录域（`w:sdt` 内的 TOC 域代码），供写出器直接插入文档树。"""
    depth = level if level is not None else 3
    if not 1 <= depth <= _MAX_TOC_DEPTH:
        raise MarkerError(t("markers.toc_depth", lang, max=_MAX_TOC_DEPTH, depth=depth))
    # 前后各留一个空格：与 Word 自己写出的域代码同形，用户在 Word 里改域时不会对不上。
    instr = f' TOC \\o "1-{depth}" \\h \\z \\u '
    placeholder = escape(t("markers.toc_placeholder", lang))
    return (
        '<w:sdt xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:sdtPr><w:docPartObj>'
        '<w:docPartGallery w:val="Table of Contents"/><w:docPartUnique/>'
        "</w:docPartObj></w:sdtPr><w:sdtContent>"
        '<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve">{instr}</w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"<w:r><w:t>{placeholder}</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        "</w:sdtContent></w:sdt>"
    )





def new_section_sectpr(template_sect):
    """分节用的 sectPr：复制模板末尾那一个，去掉只属于「最后一节」的设置。"""
    sect = (
        copy.deepcopy(template_sect)
        if template_sect is not None
        else etree.Element(_W + "sectPr", nsmap={"w": _NS})
    )
    for tag in ("titlePg", "type"):
        for el in sect.findall(_W + tag):
            sect.remove(el)
    return sect


def set_next_page(sect) -> None:
    type_el = etree.Element(_W + "type")
    type_el.set(_W + "val", "nextPage")
    _insert_ordered(sect, type_el, "type")


def set_page_number(sect, fmt: Optional[str], start: Optional[int]) -> None:
    """页码格式与起始：`start=None` 表示接着上一节编（去掉起始值）。"""
    pg = sect.find(_W + "pgNumType")
    if pg is None:
        if fmt is None and start is None:
            return
        pg = etree.Element(_W + "pgNumType")
        _insert_ordered(sect, pg, "pgNumType")
    if fmt is not None:
        pg.set(_W + "fmt", fmt)
    if start is None:
        pg.attrib.pop(_W + "start", None)
    else:
        pg.set(_W + "start", str(start))


def section_paragraph_xml(sect) -> str:
    """承载 sectPr 的空段落。外层 p/pPr 也带命名空间声明：sectPr 上的声明只覆盖它自己。"""
    return (
        f'<w:p xmlns:w="{_NS}"><w:pPr>'
        + etree.tostring(sect, encoding="unicode")
        + "</w:pPr></w:p>"
    )



