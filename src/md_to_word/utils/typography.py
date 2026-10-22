"""md_to_word.utils.typography — 排印层面的文字规整。

只做一件小事：直引号 → 弯引号。中文稿里 `"…"` 若原样印进 Word，两边会是两个 ASCII
直引号，与中文排版习惯不符；代码与公式不走这里。
"""

from __future__ import annotations

_OPENERS = "([{（【「‘“"


def smart_quotes(text: str) -> str:
    """直引号 → 弯引号：`"甲"` → `“甲”`，`don't` → `don’t`。

    单靠"前一个字符是不是空白"判断开合，在中文里行不通：中文引号紧贴汉字
    （`不作"无遗漏变量偏误"的断言`），前一个字符永远是汉字，一判就全成了闭引号。
    所以改成**成对翻转**：见到可作开引号的位置就翻一次。空格/括号/行首仍是明确的
    开引号位置，这一条保留，用来照顾西文里的 `"quoted"` 与英寸符号。
    """
    if '"' not in text and "'" not in text:
        return text
    out: list[str] = []
    open_double = open_single = True
    for i, ch in enumerate(text):
        prev = out[-1] if out else ""
        boundary = not prev or prev.isspace() or prev in _OPENERS
        if ch == '"':
            if boundary or open_double:
                out.append("“")
                open_double = False
            else:
                out.append("”")
                open_double = True
        elif ch == "'":
            if prev.isalnum():
                out.append("’")  # 撇号：don't / O'Brien / consumers'（前面是字母就是撇号）
            elif boundary or open_single:
                out.append("‘")
                open_single = False
            else:
                out.append("’")
                open_single = True
        else:
            out.append(ch)
    return "".join(out)
