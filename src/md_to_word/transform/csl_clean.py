"""CSL 文件的规范化：去掉会覆盖模板样式的 direct formatting。

CSL 的 `<bibliography>` 标签可以带 `hanging-indent`、`second-field-align`、
`line-spacing` 三个属性。引文处理器会把它们写成**段落级直接格式**，而直接格式的优先级
高于样式——于是同一份 `format.txt`，换一个 CSL，悬挂缩进和行距就变了，
「同一份稿件重跑结果一致」这个承诺当场作废。

判据很简单：**段落格式归模板管，CSL 只管条目里写什么**。所以这三个属性一律去掉，
内置样式在发布前就已规范化，用户自带的在这里现剥。
"""

from __future__ import annotations

import re

DIRECT_FORMAT_ATTRS = ("hanging-indent", "second-field-align", "line-spacing")

_BIBLIOGRAPHY_TAG_RE = re.compile(r"(<bibliography)([^>]*)(>)")


def strip_direct_formatting(text: str) -> tuple[str, list[str]]:
    """去掉 `<bibliography>` 上的 direct formatting 属性。

    返回 (清理后的文本, 被去掉的属性名)。没找到 `<bibliography>` 时原样返回、属性列表为空
    ——「不是 CSL」由调用方另行判断，不能和「已经干净」混为一谈。
    """
    match = _BIBLIOGRAPHY_TAG_RE.search(text)
    if not match:
        return text, []

    attrs = match.group(2)
    removed: list[str] = []
    for attr in DIRECT_FORMAT_ATTRS:
        pattern = rf"\s+{re.escape(attr)}\s*=\s*[\"'][^\"']*[\"']"
        if re.search(pattern, attrs):
            removed.append(attr)
            attrs = re.sub(pattern, "", attrs)

    if not removed:
        return text, []

    cleaned = text[: match.start()] + match.group(1) + attrs + match.group(3) + text[match.end():]
    return cleaned, removed


def is_csl(text: str) -> bool:
    """粗判：有 `<style` 与 `<bibliography>` 才算 CSL 样式文件。"""
    return "<style" in text and "<bibliography" in text
