"""md_to_word.utils.masking — 行号安全的文本掩码。

把「不该被当成正文」的部分换成等量换行：内容不参与后面的检查，行号一个不挪。
预检（validator）、防丢数（audit）、方言检查（utils）、清理器（preprocessor）四层
都要用同一份判据，各写一份就会出现「同一份稿子，两层给出不同结论」。

单独成一个模块而不是挂在哪一层上：这四处互相导入，放在任何一处都会绕出循环导入。
"""

from __future__ import annotations

import re

HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

# 行内代码：`` `…` `` 或 ``` ``…`` ```。整段换成点号，保留长度与行号。
_INLINE_CODE_RE = re.compile(r"(?<!`)(`{1,3})[^`\n]*?\1(?!`)")
_URL_RE = re.compile(r"https?://\S+")
_MATH_BLOCK_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_MATH_INLINE_RE = re.compile(r"\$[^$\n]+\$")
_CITATION_KEY_RE = re.compile(r"@[\w:.\-]+")
_FRONTMATTER_RE = re.compile(
    r"\A---[ \t]*\r?\n.*?^(?:---|\.\.\.)[ \t]*(?:\r?\n|$)", re.DOTALL | re.MULTILINE
)


def mask_html_comments(text: str) -> str:
    """把 HTML 注释换成等量换行：内容不算数，行号不变。"""
    return HTML_COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def mask_code_fences(content: str) -> str:
    """围栏代码块（``` / ~~~）内各行掩码为 '.'，保留总行数与行号不变。"""
    out = []
    in_fence = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(".")
            continue
        out.append("." if in_fence else line)
    return "\n".join(out)


def mask_inline_code(content: str) -> str:
    """行内代码的内容掩码为 '.'，保留长度与行号。

    判据只该看「作者真写的正文」时用它：稿件里用反引号演示语法（`` `![alt](x.png)` ``）是
    正当的，不该被当成真图片去查磁盘。
    """
    return _INLINE_CODE_RE.sub(lambda m: "." * len(m.group(0)), content)


def mask_code(content: str) -> str:
    """围栏代码块 + 行内代码一起掩码。"""
    return mask_inline_code(mask_code_fences(content))


def mask_prose_noise(text: str) -> str:
    """只留「自然语言正文」：去掉代码、frontmatter、URL、公式、引文键与 HTML 注释。

    语言判定用它：中文技术稿里夹着大段英文代码时，代码不该把中文判成英文稿。
    """
    text = _FRONTMATTER_RE.sub(" ", text)
    text = mask_code(text)
    text = HTML_COMMENT_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _MATH_BLOCK_RE.sub(" ", text)
    text = _MATH_INLINE_RE.sub(" ", text)
    text = _CITATION_KEY_RE.sub(" ", text)
    return text
