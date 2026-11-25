"""引文 key 的语法。

正文读取（`model.reader`）与预检（`utils.skill_utils`）必须认同一套字符：
预检认了 `k+5`、读取器只读到 `k`，就会出现「预检通过、产物引错条目」。
字符集由 citeproc 实测而来——`k1:2` / `k-2` / `k_3` / `k.4` / `k+5` / `k%7` / `k/7` / `k&7`
都能在 `.bib` 里命中。
"""

from __future__ import annotations

# 首字符是字母数字或 `_`；其后允许 `: . - _ + / % &`
CITE_KEY_PATTERN = r"\w[\w:.\-+/%&]*"

# `@` 前是 ASCII 字母数字或 `_` 时不算引文（`user@example.com` 原样输出）；
# `-@key`（抑制作者）的 `@` 前是 `-`，所以 `-` 不能进排除集。
CITE_KEY_RE = __import__("re").compile(rf"(?<![A-Za-z0-9_@])@({CITE_KEY_PATTERN})")
