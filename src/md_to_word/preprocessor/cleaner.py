"""md_to_word.preprocessor.cleaner — 稿件清理与注释剔除。"""

from __future__ import annotations

import re

_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def strip_html_comments(text: str) -> str:
    """剔除稿件中的 HTML 注释 <!-- ... -->。"""
    return _RE_HTML_COMMENT.sub("", text)
