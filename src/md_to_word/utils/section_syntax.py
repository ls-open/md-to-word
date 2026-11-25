"""分节标记的语法：`{{< section >}}` 与 `{{< section 正文 >}}`。

读取器与导前预检共用这一份解析：两边各写一套时，一处放行、另一处拦下，
用户看到的就会是「预检通过、产物按另一个节名排版」。

标记只接受**一个节名**。节名由格式文件声明（`分节：正文`）；不在这里判断
是否存在——稿件读取阶段还拿不到格式文件。
"""

from __future__ import annotations

import re

# 节名：字母、数字、下划线、连字符、CJK。不允许空白与 `=`——分节标记没有参数，
# `页码=…` 这类写法不是「旧参数」，在这个语法里就是无法识别的文本。
ROLE_NAME_RE = re.compile(r"^[A-Za-z0-9_\-㐀-鿿]+$")


class SectionSyntaxError(ValueError):
    """分节标记写法不合法。`arg` 是尖括号里那段原文，供报错引用。"""

    def __init__(self, arg: str) -> None:
        self.arg = arg
        super().__init__(f"invalid section marker argument: {arg!r}")


def parse_section_arg(rest: str) -> str | None:
    """`{{< section` 之后的文本 → 节名；空表示「普通分节」。

    写法不对时抛 `SectionSyntaxError`，由调用方本地化（读取器与预检同一套文案）。
    """
    arg = (rest or "").strip()
    if not arg:
        return None
    if ROLE_NAME_RE.match(arg):
        return arg
    raise SectionSyntaxError(arg)
