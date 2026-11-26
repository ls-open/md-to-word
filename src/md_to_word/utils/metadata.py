"""md_to_word.utils.metadata — 文档属性（盲审）清理。

`--base-template` 灌入的是用户提供的 `.docx`：它的 `docProps/` 会原样跟着成品走，
里面可能留着作者、单位、学号、封面缩略图与批注作者。正文排版再干净，这些字段也会
把身份带出去。

这里只做**文件属性**的清理：core/app 属性、自定义属性、缩略图、批注与修订作者。
正文里的姓名、封面文字、页眉不在此列——那要作者自己替换，谎称做了反而危险。

清理在临时产物上完成、再原子替换；失败不发布，与导出门禁同一套原则。
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from md_to_word.i18n import t

_CORE = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
_DC = "http://purl.org/dc/elements/1.1/"
_DCTERMS = "http://purl.org/dc/terms/"
_APP = "http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_REL_CUSTOM = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
# 删掉 comments 部件后，正文里仍指着它们的这些标记必须一并剥掉，否则包是坏的。
_COMMENT_ANCHORS = (
    f"{{{_W}}}commentRangeStart",
    f"{{{_W}}}commentRangeEnd",
    f"{{{_W}}}commentReference",
)
_REL_THUMBNAIL = "http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"

# 这些部件带的是身份，不是正文：整件丢弃，同时清掉关系与内容类型。
_DROP_PREFIXES = (
    "docProps/custom.xml",
    "docProps/thumbnail.",
    "word/comments.xml",
    "word/commentsExtended.xml",
    "word/commentsIds.xml",
    "word/commentsExtensible.xml",
    "word/people.xml",
)

_CORE_FIELDS = (
    (f"{{{_DC}}}title", "title"),
    (f"{{{_DC}}}subject", "subject"),
    (f"{{{_DC}}}creator", "creator"),
    (f"{{{_CORE}}}keywords", "keywords"),
    (f"{{{_DC}}}description", "description"),
    (f"{{{_CORE}}}lastModifiedBy", "lastModifiedBy"),
    (f"{{{_CORE}}}category", "category"),
    (f"{{{_CORE}}}contentStatus", "contentStatus"),
)
# 这几个元素要**整件删除**，不能把文本清空：Word 把空的 `cp:lastPrinted` 判成损坏，
# 打开时直接弹「文件已损坏」，而且是在所有门禁之后才发生。日期元素同理。
_CORE_DROP = (
    f"{{{_DCTERMS}}}created",
    f"{{{_DCTERMS}}}modified",
    f"{{{_CORE}}}lastPrinted",
)
_APP_FIELDS = (
    (f"{{{_APP}}}Company", "company"),
    (f"{{{_APP}}}Manager", "manager"),
    (f"{{{_APP}}}Template", "template"),
    (f"{{{_APP}}}HyperlinkBase", "hyperlinkBase"),
)


class MetadataError(RuntimeError):
    """清理失败：产物保持不变。"""


@dataclass(frozen=True)
class IdentityFinding:
    """一处可识别的文档属性。`code` 用于本地化与提示，`detail` 是原值或数量。"""

    code: str
    detail: str = ""


def _text_of(root, tag: str) -> str:
    el = root.find(tag)
    return (el.text or "").strip() if el is not None else ""


def identifying_metadata(path: Path | str) -> list[IdentityFinding]:
    """底模/成品里有哪些会带出身份的文档属性。按固定顺序返回，便于测试与提示。"""
    found: list[IdentityFinding] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "docProps/core.xml" in names:
                root = etree.fromstring(archive.read("docProps/core.xml"))
                for tag, code in _CORE_FIELDS:
                    value = _text_of(root, tag)
                    if not value:
                        continue
                    # 本工具自己写的出处备注不是身份信息：`md-to-word <版本> · <格式文件> · sha256:…`
                    # 出现在底模里时，提醒「交盲审前请清理作者/单位」就会变成误报。
                    if code == "description" and value.startswith("md-to-word "):
                        continue
                    found.append(IdentityFinding(code, value))
            if "docProps/app.xml" in names:
                root = etree.fromstring(archive.read("docProps/app.xml"))
                for tag, code in _APP_FIELDS:
                    # 模板名/超链接基址/上次打印时间不是身份：清理时一起清，但不报警，
                    # 否则每个底模都会提示一遍「Normal.dotm」，提醒就失去意义。
                    if code in ("template", "hyperlinkBase"):
                        continue
                    value = _text_of(root, tag)
                    if value:
                        found.append(IdentityFinding(code, value))
    except (OSError, zipfile.BadZipFile, etree.XMLSyntaxError):
        return found
    if any(name.startswith("docProps/custom.xml") for name in names):
        found.append(IdentityFinding("custom"))
    if any(name.startswith("docProps/thumbnail.") for name in names):
        found.append(IdentityFinding("thumbnail"))
    if any(name.startswith("word/comments") for name in names):
        found.append(IdentityFinding("comments"))
    if "word/people.xml" in names:
        found.append(IdentityFinding("people"))
    return found


def _is_dropped(name: str) -> bool:
    return any(name == prefix or name.startswith(prefix) for prefix in _DROP_PREFIXES)


def _drop_relationships(blob: bytes, *, doc_props: bool) -> bytes:
    root = etree.fromstring(blob)
    for rel in list(root):
        target = rel.get("Target", "")
        rel_type = rel.get("Type", "")
        if doc_props:
            if rel_type in (_REL_CUSTOM, _REL_THUMBNAIL) or target.startswith("docProps/custom.xml") \
                    or target.startswith("docProps/thumbnail."):
                root.remove(rel)
        else:
            if rel_type.endswith(("/comments", "/commentsExtended", "/commentsIds",
                                  "/commentsExtensible", "/people")):
                root.remove(rel)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _drop_content_type_overrides(blob: bytes) -> bytes:
    root = etree.fromstring(blob)
    for override in list(root):
        part = override.get("PartName", "").lstrip("/")
        if _is_dropped(part):
            root.remove(override)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clear_core(blob: bytes) -> bytes:
    root = etree.fromstring(blob)
    for tag, _code in _CORE_FIELDS:
        el = root.find(tag)
        if el is not None:
            el.text = None
    for tag in _CORE_DROP:
        el = root.find(tag)
        if el is not None:
            root.remove(el)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _clear_app(blob: bytes) -> bytes:
    root = etree.fromstring(blob)
    for tag, _code in _APP_FIELDS:
        el = root.find(tag)
        if el is not None:
            el.text = None
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _neutralize_authors(blob: bytes) -> bytes:
    """修订与批注里的作者名换成中性值；内容不动。"""
    root = etree.fromstring(blob)
    author, initials = f"{{{_W}}}author", f"{{{_W}}}initials"
    for el in root.iter():
        if author in el.attrib:
            el.set(author, "Author")
        if initials in el.attrib:
            el.set(initials, "A")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _strip_comment_anchors(blob: bytes) -> bytes:
    root = etree.fromstring(blob)
    for el in list(root.iter(*_COMMENT_ANCHORS)):
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _verify_scrubbed(path: Path, lang: str = "zh") -> None:
    """清理后的包必须仍然自洽。

    清理在所有验真门禁之后运行，写坏了的包不会被前面的检查发现——这里就是在原子替换
    之前最后过一遍：关系都有目标、XML 都能解析、批注锚点确实没了、身份部件确实删了。
    """
    import posixpath

    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        for name in names:
            if not name.endswith(".rels"):
                continue
            base = posixpath.dirname(posixpath.dirname(name))
            root = etree.fromstring(archive.read(name))
            for rel in root:
                if rel.get("TargetMode") == "External":
                    continue
                target = rel.get("Target", "")
                if target.startswith("/"):
                    resolved = target.lstrip("/")
                else:
                    resolved = posixpath.normpath(posixpath.join(base, target))
                if resolved not in names:
                    raise MetadataError(t("metadata.verify.missing_rel", lang,
                                          name=name, target=target))
        if "word/document.xml" in names:
            document = archive.read("word/document.xml").decode("utf-8")
            for tag in ("commentRangeStart", "commentRangeEnd", "commentReference"):
                if tag in document:
                    raise MetadataError(t("metadata.verify.comment_anchor", lang, tag=tag))
        for name in names:
            if name.endswith((".xml", ".rels")):
                etree.fromstring(archive.read(name))
        leftover = [name for name in names
                    if any(name.startswith(prefix) for prefix in _DROP_PREFIXES)]
        if leftover:
            raise MetadataError(t("metadata.verify.identity_part", lang, name=leftover[0]))


def scrub_metadata(path: Path | str, lang: str = "zh") -> None:
    """就地清理一份 .docx 的文档属性；写临时文件后原子替换，失败不留下半成品。"""
    target = Path(path)
    temp = target.with_name(f".{target.name}.blind-review")
    try:
        with zipfile.ZipFile(target) as source, zipfile.ZipFile(temp, "w") as sink:
            for info in source.infolist():
                name = info.filename
                if _is_dropped(name):
                    continue
                data = source.read(name)
                if name == "docProps/core.xml":
                    data = _clear_core(data)
                elif name == "docProps/app.xml":
                    data = _clear_app(data)
                elif name == "_rels/.rels":
                    data = _drop_relationships(data, doc_props=True)
                elif name == "word/_rels/document.xml.rels":
                    data = _drop_relationships(data, doc_props=False)
                elif name == "[Content_Types].xml":
                    data = _drop_content_type_overrides(data)
                elif name.startswith("word/") and name.endswith(".xml") and (
                    b"w:commentRange" in data or b"w:commentReference" in data
                ):
                    data = _strip_comment_anchors(data)
                elif name.startswith("word/") and name.endswith(".xml") and (
                    b"w:author=" in data or b"w:initials=" in data
                ):
                    data = _neutralize_authors(data)
                # 用原 ZipInfo 写回：保留条目顺序与时间戳，同一输入产出同样的字节
                sink.writestr(info, data)
        _verify_scrubbed(temp, lang)
        os.replace(temp, target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
