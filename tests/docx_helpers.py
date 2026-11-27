"""测试用的 docx 包级设置修改器。

python-docx 建出来的底模默认是兼容模式 14、标点压缩 doNotCompress；本工具的中文正文
是 15、compressPunctuation。测试底模要先对齐这些文档级设置，否则会被注入门禁拒绝。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _rewrite_settings(path: Path, change) -> Path:
    with zipfile.ZipFile(path) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    root = etree.fromstring(parts["word/settings.xml"])
    change(root)
    parts["word/settings.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in parts.items():
            z.writestr(name, blob)
    return path


def set_compat_mode(path: Path, value: str = "15") -> Path:
    def change(root) -> None:
        for el in root.iter(W + "compatSetting"):
            if el.get(W + "name") == "compatibilityMode":
                el.set(W + "val", value)

    return _rewrite_settings(path, change)


def remove_compat_mode(path: Path) -> Path:
    def change(root) -> None:
        for el in list(root.iter(W + "compatSetting")):
            if el.get(W + "name") == "compatibilityMode":
                el.getparent().remove(el)

    return _rewrite_settings(path, change)


def set_character_spacing(path: Path, value: str = "compressPunctuation") -> Path:
    def change(root) -> None:
        el = root.find(W + "characterSpacingControl")
        if el is None:
            el = etree.SubElement(root, W + "characterSpacingControl")
        el.set(W + "val", value)

    return _rewrite_settings(path, change)


def set_on_off(path: Path, tag: str, enabled: bool) -> Path:
    def change(root) -> None:
        el = root.find(W + tag)
        if enabled:
            if el is None:
                etree.SubElement(root, W + tag)
        elif el is not None:
            root.remove(el)

    return _rewrite_settings(path, change)


def align_base(
    path: Path,
    *,
    punctuation: str = "compressPunctuation",
    mirror: bool = False,
    even: bool = False,
) -> Path:
    """让 python-docx 建出来的底模和本工具正文的文档级设置对齐。"""
    set_compat_mode(path, "15")
    set_character_spacing(path, punctuation)
    set_on_off(path, "mirrorMargins", mirror)
    set_on_off(path, "evenAndOddHeaders", even)
    return path
