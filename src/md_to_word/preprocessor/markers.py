"""md_to_word.preprocessor.markers — 短代码与结构标记展开器。

在渲染前将结构标记（{{< toc >}}、{{< section >}} 等）展开为符合 OOXML Schema 的 {=openxml} 块。
"""

from __future__ import annotations

from typing import Any

import copy
import re
import zipfile
from pathlib import Path
from typing import Optional
from lxml import etree

from md_to_word.spec.constants import PAGE_NUMBER_FMT

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

_TOC_RE = re.compile(r"^\s*\{\{<\s*toc(?:\s+(?P<level>\d+))?\s*>\}\}\s*$")
_SECTION_RE = re.compile(r"^\s*\{\{<\s*section\b(?P<params>[^>]*)>\}\}\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
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


def _openxml_block(xml: str) -> str:
    return "```{=openxml}\n" + xml + "\n```"


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


def toc_block(level: Optional[int] = None) -> str:
    return _openxml_block(toc_xml(level))


def parse_section_params(raw: str) -> dict[str, Any]:
    params: dict[str, str] = {}
    for token in raw.split():
        if "=" not in token:
            raise MarkerError(f"分节标记的参数要写成 键=值，收到 {token!r}")
        key, val = token.split("=", 1)
        if key in params:
            raise MarkerError(f"分节标记的参数重复：{key}")
        params[key] = val

    out: dict[str, Any] = {}
    # 支持中文「页码=」与英文「page_number= / format=」
    pg_key = next((k for k in ("页码", "format", "fmt") if k in params), None)
    if pg_key:
        val = params[pg_key]
        if val not in PAGE_NUMBER_FMT:
            raise MarkerError(f"页码格式不认识: {val!r}")
        out["fmt"] = PAGE_NUMBER_FMT[val]

    start_key = next((k for k in ("起始", "start") if k in params), None)
    if start_key:
        if not params[start_key].isdigit():
            raise MarkerError(f"起始页码须为正整数: {params[start_key]!r}")
        out["start"] = int(params[start_key])

    return out


def template_section(template_path: Optional[Path | str]):
    if not template_path:
        return None
    try:
        with zipfile.ZipFile(template_path) as z:
            doc = z.read("word/document.xml")
    except Exception as exc:
        raise MarkerError(f"无法读取模板分节属性: {template_path} ({exc})") from exc

    root = etree.fromstring(doc)
    body = root.find(_W + "body")
    return body.find(_W + "sectPr") if body is not None else None


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


def section_block(params: dict, template_sect) -> str:
    return _openxml_block(section_paragraph_xml(params, template_sect))


def expand_markers(text: str, template_path: Optional[Path | str] = None) -> tuple[str, dict[str, int]]:
    """展开 Markdown 文本中的全部结构标记，返回 (展开后的文本, 统计字典)。"""
    template_sect = None
    counts = {"toc": 0, "section": 0}
    out = []
    in_fence = False

    for line in text.split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        m_toc = _TOC_RE.match(line)
        if m_toc:
            lvl = int(m_toc.group("level")) if m_toc.group("level") else None
            out.append(toc_block(lvl))
            counts["toc"] += 1
            continue

        m_sec = _SECTION_RE.match(line)
        if m_sec:
            if template_sect is None and template_path:
                template_sect = template_section(template_path)
            params = parse_section_params(m_sec.group("params"))
            out.append(section_block(params, template_sect))
            counts["section"] += 1
            continue

        out.append(line)

    return "\n".join(out), counts
