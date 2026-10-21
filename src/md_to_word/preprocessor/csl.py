"""md_to_word.preprocessor.csl — CSL 文件规范化。

去除 CSL <bibliography> 标签上的 direct formatting 属性，
确保参考文献样式由 Word 模板完全控制。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

DIRECT_FORMAT_ATTRS = {"hanging-indent", "second-field-align", "line-spacing"}


def normalize_csl_content(content: str) -> tuple[Optional[str], list[str]]:
    """规范化 CSL XML 文本。

    返回: (规范化后的内容字符串或 None[非 CSL], 被去除的属性列表)
    """
    pattern = r"(<bibliography)([^>]*)(>)"
    m = re.search(pattern, content)
    if not m:
        return None, []

    attrs_str = m.group(2)
    removed: list[str] = []
    new_attrs = attrs_str

    for attr in DIRECT_FORMAT_ATTRS:
        attr_pattern = rf'\s+{re.escape(attr)}\s*=\s*["\'][^"\']*["\']'
        if re.search(attr_pattern, new_attrs):
            removed.append(attr)
            new_attrs = re.sub(attr_pattern, "", new_attrs)

    if not removed:
        return content, []

    new_tag = m.group(1) + new_attrs + m.group(3)
    new_content = content[: m.start()] + new_tag + content[m.end() :]
    return new_content, removed


def normalize_csl_file(
    input_path: Path | str, output_path: Optional[Path | str] = None
) -> tuple[bool, list[str]]:
    """读取文件并就地或输出规范化后的 CSL 文件。"""
    p_in = Path(input_path)
    p_out = Path(output_path) if output_path else p_in

    content = p_in.read_text(encoding="utf-8")
    new_content, removed = normalize_csl_content(content)
    if new_content is None:
        return False, []

    if removed and p_out:
        p_out.write_text(new_content, encoding="utf-8")
        return True, removed
    return False, []
