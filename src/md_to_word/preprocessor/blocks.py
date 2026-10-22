"""md_to_word.preprocessor.blocks — 段落样式行。

写法：`%% <样式名> <正文>`

与 `# 标题` 同一条排布规则——符号在最前，内容跟在同行。区别在于标题的层级能用符号
编码（`#`/`##`…），段落样式有二十多种编码不了，所以名字写在符号后面。

单位是**段落**，不是区域：一行即一段，空行结束。没有闭合符号，也就没有"忘记闭合"。
读取器按这一行直接造段落节点，套对应样式；这里只做**认名字**与**挑毛病**两件事。
"""

from __future__ import annotations

import re

from md_to_word.spec.constants import STYLE_MAP

# `%%` 后必须有一个空格，再接样式名与正文
_STYLE_LINE_RE = re.compile(r"^(?P<indent>[ \t]*)%%[ \t]+(?P<rest>\S.*)$")

# 标题类由 `#` 的个数决定，不接受第二套入口
_HEADING_STYLES = {"Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5", "Heading 6"}

# 参考文献列表由 .bib + csl 生成，不接受手写清单（否则会与生成结果并存、样式打架）
GENERATED_STYLES = {"Bibliography"}

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


def style_line_issues(text: str) -> list[tuple[int, str]]:
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
            issues.append(
                (i, f"不认识样式名「{name}」；请写词表里的名字（如 摘要 / 关键词 / 表题 / 表注 / 参考文献标题）")
            )
        elif resolved in _HEADING_STYLES:
            issues.append(
                (i, f"「{name}」是标题类样式，章节层级请用 Markdown 的 # 写法（## 为二级，依此类推）")
            )
        elif resolved in GENERATED_STYLES:
            issues.append(
                (
                    i,
                    "手写文献列表已不支持：在 YAML 里写 `bibliography: refs.bib` 与 `csl:`，"
                    "文献列表由引擎生成（样式仍由要求文件的「参考文献」行控制）",
                )
            )
        elif not content:
            issues.append((i, f"「{name}」后面没有正文；这一行要写成「%% {name} 内容」"))
        elif _looks_like_continuation(lines, i - 1):
            issues.append(
                (
                    i,
                    f"「{name}」的下一行紧接正文，疑似软换行；本技能的段落样式以这一行为界，"
                    f"续行不会被并进来。请把整段合并到这一行",
                )
            )
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
