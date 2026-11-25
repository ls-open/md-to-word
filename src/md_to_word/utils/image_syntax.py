"""独立成行的图片语法（读取器与预检共用一份）。

CommonMark 的图片目标允许尖括号包起带空格的路径，也允许成对的圆括号
（`fig(1).png`、`Screen Shot (2).png`）。旧正则用 `[^)\\s]+`，路径在第一个
右括号或空格处被截断，预检报「文件不存在」、写出器印出字面 `![](...)`。
"""

from __future__ import annotations

import re

# 目标：`<任意非 > 字符>`，或由普通字符与**一层**成对括号组成的串。
_TARGET = r"(?:<[^>\n]+>|(?:[^()\n]|\([^()\n]*\))*?)"

IMAGE_LINE_RE = re.compile(
    r"^!\[(?P<alt>[^\]]*)\]\(\s*(?P<path>" + _TARGET + r")"
    r'\s*(?P<title>"[^"]*")?\s*\)\s*(?P<attrs>\{[^}]*\})?\s*$'
)

# 行内出现图片语法（不管目标能不能解析）——图片必须独立成行。
IMAGE_HINT_RE = re.compile(r"!\[[^\]]*\]\(")


def image_target(raw: str) -> str:
    """去掉尖括号与标题，得到磁盘上的路径字符串。"""
    value = (raw or "").strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    return value
