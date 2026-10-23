"""md_to_word.preprocessor.blocks — 段落样式行。

写法：`%% <样式名> <正文>`

与 `# 标题` 同一条排布规则——符号在最前，内容跟在同行。区别在于标题的层级能用符号
编码（`#`/`##`…），段落样式有二十多种编码不了，所以名字写在符号后面。

单位是**段落**，不是区域：一行即一段，空行结束。没有闭合符号，也就没有"忘记闭合"。
读取器按这一行直接造段落节点，套对应样式；这里只做**认名字**与**挑毛病**两件事。
"""

from __future__ import annotations

import re

from md_to_word.i18n import style_examples, t
from md_to_word.spec.constants import STYLE_MAP

# `%%` 后必须有一个空格，再接样式名与正文
_STYLE_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)%%[ \t]+(?P<rest>\S.*)$")

# 标题类由 `#` 的个数决定，不接受第二套入口
_HEADING_STYLES = {"Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5", "Heading 6"}

# 参考文献列表由 .bib + csl 生成，不接受手写清单（否则会与生成结果并存、样式打架）
GENERATED_STYLES = {"Bibliography"}


def hard_break(line: str) -> tuple[str, bool]:
    """行尾的段内换行标记 → (去掉标记的行, 是否要接续下一行)。

    两种写法都收：行尾一个反斜杠、行尾两个以上空格。反斜杠成对出现是字面反斜杠
    （`C:\\tmp\\`），不接续——否则路径结尾会被吃掉一个字符。
    """
    trimmed = line.rstrip()
    if len(line) - len(trimmed) >= 2:
        return trimmed, True
    if trimmed.endswith("\\"):
        trailing = len(trimmed) - len(trimmed.rstrip("\\"))
        if trailing % 2:
            return trimmed[:-1].rstrip(), True
    return trimmed, False


# 长名优先：`摘要标题` 必须先于 `摘要` 命中，否则会被拆成 `摘要` + 内容「标题 …」
_NAMES_BY_LENGTH = sorted(STYLE_MAP, key=len, reverse=True)


def split_style_line(line: str) -> tuple[str, str] | None:
    """`%% 摘要 本文…` → (摘要, 本文…)；不是样式行返回 None。"""
    m = _STYLE_LINE_RE.match(line)
    if not m:
        return None
    rest = m.group("rest").strip()
    for name in _NAMES_BY_LENGTH:
        if rest == name:
            return name, ""
        if rest.startswith(name) and rest[len(name) : len(name) + 1] in (" ", "\t", "　"):
            return name, rest[len(name) :].strip()
    # 认不出名字：把第一个词当名字返回，交给调用方报错（保留原文便于提示）
    return rest.split(maxsplit=1)[0], rest.split(maxsplit=1)[1] if len(rest.split(maxsplit=1)) > 1 else ""


def resolve_style_name(name: str) -> str | None:
    return STYLE_MAP.get(name.strip())


def style_line_issues(text: str, lang: str = "zh") -> list[tuple[int, str]]:
    """样式行的三类错误 → [(行号, 说明)]：名字不认识、写成标题类、缺正文。"""
    issues: list[tuple[int, str]] = []
    lines = (text or "").split("\n")
    in_fence = False
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        split = split_style_line(line)
        if split is None:
            continue
        name, content = split
        resolved = resolve_style_name(name)
        if resolved is None:
            # 举例的样式名跟消息语言走：英文稿举 Abstract，中文稿举「摘要」
            issues.append(
                (i, t("gate.style.unknown_name", lang, name=name, examples=style_examples(lang)))
            )
        elif resolved in _HEADING_STYLES:
            issues.append((i, t("gate.style.heading_style", lang, name=name)))
        elif resolved in GENERATED_STYLES:
            issues.append((i, t("gate.style.manual_bibliography", lang)))
        elif not content:
            issues.append((i, t("gate.style.empty_content", lang, name=name)))
        elif _looks_like_continuation(lines, i - 1):
            issues.append((i, t("gate.style.continuation", lang, name=name)))
    return issues


_BLOCK_STARTERS = ("|", "#", "-", "*", "+", ">", "!", "$", "%", "`", "~", ":")


def _looks_like_continuation(lines: list[str], index: int) -> bool:
    """样式行的下一行是不是纯正文（而不是表格、标题、列表、图片等新块的开头）。"""
    if index + 1 >= len(lines):
        return False
    nxt = lines[index + 1].strip()
    if not nxt or nxt[0].isdigit():
        return False
    return not nxt.startswith(_BLOCK_STARTERS)


def style_line_names(text: str) -> list[tuple[int, str]]:
    """稿件里所有样式行 → [(行号, 解析后的 Word 样式名)]，供「样式是否在模板里」核对。"""
    found: list[tuple[int, str]] = []
    in_fence = False
    for i, line in enumerate((text or "").split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        split = split_style_line(line)
        if split is None:
            continue
        resolved = resolve_style_name(split[0])
        if resolved and resolved not in _HEADING_STYLES:
            found.append((i, resolved))
    return found
