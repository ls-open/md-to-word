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

# `{width=13cm}` / `{width=50%}`。数字必须完整：`[\d.]+` 会放行 `.` / `1.2.3`，
# 随后 `float()` 抛 ValueError，整次导出被报成“工具内部错误”。单位后面不能再跟字母，
# 否则 `13cmx` 会被截成合法宽度并悄悄忽略剩下的字符。
IMAGE_WIDTH_RE = re.compile(
    r"\bwidth\s*=\s*(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>cm|mm|in|pt|%)?(?![A-Za-z.\d])",
    re.IGNORECASE,
)
# 只用来发现“写了 width= 但值不合法”；匹配不到值本身。
IMAGE_WIDTH_HINT_RE = re.compile(r"\bwidth\s*=", re.IGNORECASE)


def parse_image_width(attrs: str) -> tuple[float, str] | None:
    """从图片属性串里取 `(数值, 单位)`；没写或写坏都返回 None。

    写坏要由预检单独报 `gate.image_width.malformed`；读取器拿到 None 时退回默认宽度，
    不能因为一个畸形属性把整篇导出打断。
    """
    found = IMAGE_WIDTH_RE.search(attrs or "")
    if found is None:
        return None
    unit = (found.group("unit") or "cm").lower()
    return float(found.group("value")), unit


def image_target(raw: str) -> str:
    """去掉尖括号与标题，得到磁盘上的路径字符串。"""
    value = (raw or "").strip()
    if value.startswith("<") and value.endswith(">"):
        value = value[1:-1].strip()
    return value
