"""md_to_word.preprocessor.blocks — 自定义结构块的短写法。

投稿人不必写 `::: {custom-style="Table Caption"}` 这种带属性的围栏，直接写
`::: 表格题注` 即可；本模块把它改写成 Pandoc 认的 fenced div。

为什么不自己展开成 OOXML：块级样式要包住**后面若干段落**，自己发 OOXML 得先把
这几段解析成段落再套 `w:pStyle`，那是把 Pandoc 的活重做一遍。改写成 div 让 Pandoc
继续负责段落包裹，我们只负责「名字认不认」——规则在我们手里，执行在别人手里。

`{custom-style="…"}` 的老写法继续有效（既成稿件与上游搬运版都在用）。
"""

from __future__ import annotations

import re

from md_to_word.spec.constants import STYLE_MAP

# `::: 名字` —— 后面紧跟花括号的是 Pandoc 原生属性写法，不归本模块管
_STYLE_BLOCK_RE = re.compile(r"^(?P<indent>[ \t]*):::[ \t]+(?P<name>[^{}\s][^{}]*?)[ \t]*$")


def resolve_style_alias(name: str) -> str | None:
    """把用户写的结构名解析成 Word 样式名；不认识的返回 None。"""
    return STYLE_MAP.get(name.strip())


def expand_style_blocks(text: str) -> str:
    """`::: 摘要` → `::: {custom-style="Abstract"}`；不认识的名字原样保留，交给预检报错。"""
    out: list[str] = []
    in_fence = False
    for line in (text or "").split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        m = _STYLE_BLOCK_RE.match(line)
        if not m:
            out.append(line)
            continue

        resolved = resolve_style_alias(m.group("name"))
        if resolved is None or resolved == m.group("name"):
            # 认不出，或者本来就是 Word 样式名（`::: Title` 这种）——保持原样
            out.append(line if resolved is None else f'{m.group("indent")}::: {{custom-style="{resolved}"}}')
            continue
        out.append(f'{m.group("indent")}::: {{custom-style="{resolved}"}}')
    return "\n".join(out)


def style_block_names(text: str) -> list[tuple[int, str, str | None]]:
    """稿件里所有 `::: 名字` 写法 → [(行号, 用户写的名字, 解析结果或 None)]。"""
    found: list[tuple[int, str, str | None]] = []
    in_fence = False
    for i, line in enumerate((text or "").split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _STYLE_BLOCK_RE.match(line)
        if m:
            found.append((i, m.group("name"), resolve_style_alias(m.group("name"))))
    return found
