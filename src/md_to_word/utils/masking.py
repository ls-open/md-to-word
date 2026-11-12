"""md_to_word.utils.masking — 行号安全的文本掩码。

把「不该被当成正文」的部分换成等量换行：内容不参与后面的检查，行号一个不挪。
预检（validator）、防丢数（audit）、方言检查（utils）、清理器（preprocessor）四层
都要用同一份判据，各写一份就会出现「同一份稿子，两层给出不同结论」。

单独成一个模块而不是挂在哪一层上：这四处互相导入，放在任何一处都会绕出循环导入。
"""

from __future__ import annotations

import re

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def mask_html_comments(text: str) -> str:
    """把 HTML 注释换成等量换行：内容不算数，行号不变。"""
    return HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
