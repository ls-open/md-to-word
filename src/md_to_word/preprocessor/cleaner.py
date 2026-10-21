"""md_to_word.preprocessor.cleaner — 稿件清理与注释剔除。"""

from __future__ import annotations

import re

_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_html_comments(text: str) -> str:
    """剔除稿件正文中的 HTML 注释 <!-- ... -->，严格保留代码块内部的注释。"""
    code_blocks: list[str] = []

    def save_block(m: re.Match) -> str:
        code_blocks.append(m.group(0))
        return f"__MD2WORD_CODE_BLOCK_{len(code_blocks)-1}__"

    # 保护 ``` 和 ~~~ 代码块
    masked = re.sub(r"(?:```.*?```|~~~.*?~~~)", save_block, text, flags=re.DOTALL)
    # 清理正文中的 HTML 注释
    cleaned = _RE_HTML_COMMENT.sub("", masked)
    # 还原代码块
    for i, block in enumerate(code_blocks):
        cleaned = cleaned.replace(f"__MD2WORD_CODE_BLOCK_{i}__", block)
    return cleaned
