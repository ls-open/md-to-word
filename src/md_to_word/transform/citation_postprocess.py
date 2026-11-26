"""Post-processing of structured CSL runs.

These are the project's output-stage fixes: numeric-run collapsing, terminal
punctuation, punctuation-in-quote, narrative citations, year suffixes,
page-range expansion, and the number-column tab. They operate on
`(text, format)` runs; they do not parse markup or touch the CSL evaluator.
"""

from __future__ import annotations

import re

from md_to_word.csl.formatter.segments import (
    merge_segments, replace_first, segments_text, slice_segments, style_at,
    to_segments,
)


_NUMERIC_CITE_RE = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)+)\]")
# 上标/无括号的数字制（Nature、AMA、Cell 一类）：`1,2,3` 也要合并
_BARE_NUMERIC_RE = re.compile(r"(?<![\d.])(\d+(?:\s*,\s*\d+){2,})(?![\d.])")


def _collapse_numeric_runs(text: str, bare: bool = False) -> str:
    """数字制的连续编号合并成区间：`[4,5,6]` → `[4–6]`。

    GB/T 7714、IEEE 这类用方括号，Nature、AMA 这类直接写上标数字；citeproc-py 两种都
    一个个列出来。三条以上连续才合并，`[4,5]` 保持原样。
    """

    def merge(numbers: list[int]) -> str:
        parts: list[str] = []
        start = prev = numbers[0]
        for n in numbers[1:] + [None]:
            if n is not None and n == prev + 1:
                prev = n
                continue
            parts.append(f"{start}–{prev}" if prev - start >= 2 else
                         ",".join(str(x) for x in range(start, prev + 1)))
            if n is not None:
                start = prev = n
        return ",".join(parts)

    def inside_brackets(match: re.Match) -> str:
        if re.search(r"[–\-]", match.group(1)):   # 已经是区间，别再拆
            return match.group(0)
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
            return match.group(0)
        return "[" + merge(numbers) + "]"

    def listed_separately(match: re.Match) -> str:
        """`[1], [2], [3]` 逐条列出的也并成 `[1]–[3]`。"""
        numbers = [int(n) for n in re.findall(r"\[(\d+)\]", match.group(0))]
        if numbers != list(range(numbers[0], numbers[0] + len(numbers))):
            return match.group(0)
        return f"[{numbers[0]}]–[{numbers[-1]}]"

    text = _NUMERIC_CITE_RE.sub(inside_brackets, text)
    text = re.sub(r"\[\d+\](?:\s*,\s*\[\d+\]){2,}", listed_separately, text)
    if bare:
        def bare_run(match: re.Match) -> str:
            numbers = [int(n) for n in re.findall(r"\d+", match.group(0))]
            if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
                return match.group(0)
            return merge(numbers)

        text = _BARE_NUMERIC_RE.sub(bare_run, text)
    return text


def _collapse_numeric_segments(segments: list[tuple[str, dict]],
                               bare: bool = False) -> list[tuple[str, dict]]:
    """Apply numeric-run collapsing to structured runs.

    Numeric citations are uniform (all plain brackets or all superscript). Merge
    same-format runs first so the regex can see the whole cluster; if a style
    splits the pattern across formats, leave it alone rather than guess.
    """
    merged = merge_segments(segments)
    if not merged:
        return []
    formats = {tuple(sorted(fmt.items())) for _text, fmt in merged}
    if len(formats) == 1:
        text = segments_text(merged)
        collapsed = _collapse_numeric_runs(text, bare=bare)
        return [(collapsed, merged[0][1])] if collapsed != text else merged
    return merge_segments([
        (_collapse_numeric_runs(text, bare=bare), fmt) for text, fmt in merged
    ])


_TERMINAL_PUNCT = ".!?:"
_CLOSING_QUOTES = "”’\"'"
# 半角句点跟在终止标点后面、且后面是空白或结尾——CSL 追加的 `suffix="."` 就是这种。
# 引号包住的也算：`“What?”` 后面同样不再补句点。
_SUFFIX_PERIOD_RE = re.compile(r"([.!?:][" + _CLOSING_QUOTES + r"]*)\.(?=\s|$)")


def _merge_period_segments(segments: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    """终止标点后面不再补句点：`Automated?.` → `Automated?`、`“Automated?”.` → `“Automated?”`。

    只看可见文本，格式边界不打断判断：APA 的书名是斜体，句点可能落在斜体 run 之后。
    """
    output: list[tuple[str, dict]] = []
    tail = ""
    for text, fmt in segments:
        while text.startswith(".") and _absorbs_period(tail):
            text = text[1:]
        text = _SUFFIX_PERIOD_RE.sub(r"\1", text)
        if text:
            output.append((text, fmt))
            visible = text.rstrip()
            if visible:
                tail = (tail + visible)[-4:]
    return merge_segments(output)


def _absorbs_period(tail: str) -> bool:
    """句点前面是不是「已经收过句号」的终止标点；右引号不算隔断（`“What?”.` 一样不补）。"""
    unquoted = tail.rstrip(_CLOSING_QUOTES)
    return bool(unquoted) and unquoted[-1] in _TERMINAL_PUNCT


_QUOTE_PUNCT_RE = re.compile(r"[”’\"][.,]")


def _punctuation_in_quote_segments(
    segments: list[tuple[str, dict]],
) -> list[tuple[str, dict]]:
    """`“An Article”.` → `“An Article.”`（en-US 的 `punctuation-in-quote`）。

    句点/逗号紧跟右引号时移进引号内。citation 与 bibliography 都在最终 run 上做一次：
    标点可能来自 group 分隔符，也可能来自 affix，单看某一层接不上。
    """
    text = segments_text(segments)
    for index in reversed([match.start() for match in _QUOTE_PUNCT_RE.finditer(text)]):
        quote_format = style_at(segments, index)
        punct_format = style_at(segments, index + 1)
        segments = merge_segments(
            slice_segments(segments, 0, index)
            + [(text[index + 1], punct_format), (text[index], quote_format)]
            + slice_segments(segments, index + 2, len(text))
        )
    return segments


def _as_narrative(text: str, *, and_word: str | None = None) -> str:
    """把 `(Smith, 2024)` 改成 `Smith (2024)`；数字制 `[1]` 原样返回。

    citeproc-py 不提供 CSL 的 author-in-text 形式，这是一次保守改写：只处理「整串被一对
    圆括号包住、且括号里只有一个分号前的条目」的情形，其余原样返回，不做猜测。
    英文多作者叙述式在正文里写 `and` 而不写 `&`（APA §8.17），由 `and_word` 替换最末连接符。
    """
    stripped = text.strip()
    if not (stripped.startswith("(") and stripped.endswith(")")):
        return text
    inner = stripped[1:-1]
    # 多篇文献用 `; ` 分隔；`&amp;` 这类实体里也有分号，先去掉实体再判
    if ";" in re.sub(r"&[a-zA-Z#0-9]+;", "", inner):
        return text
    match = re.match(
        r"^(?P<author>.+?)(?:,\s*|\s+)(?P<rest>(?:\d{4}[a-z]?|n\.d\.|no date|in press|forthcoming)(?:,\s*(?:p{1,2}\.|para\.|sec\.|chap\.)?\s*[\d\-–]+)?)$",
        inner.strip(),
    )
    if not match:
        return text
    author = match.group("author")
    if and_word:
        for separator in (" &amp; ", " & "):
            if separator in author:
                head, tail = author.rsplit(separator, 1)
                author = f"{head} {and_word} {tail}"
                break
    return f"{author} ({match.group('rest')})"


def _as_narrative_segments(segments: list[tuple[str, dict]],
                           *, and_word: str | None = None) -> list[tuple[str, dict]]:
    text = segments_text(segments)
    rewritten = _as_narrative(text, and_word=and_word)
    return segments if rewritten == text else [(rewritten, {})]


def _expand_range(value: str) -> str:
    """`33-5` → `33-35`（CSL 的 `page-range-format="expanded"`）。"""
    def repl(m: re.Match) -> str:
        start, end = m.group(1), m.group(2)
        if len(end) < len(start):
            end = start[: len(start) - len(end)] + end
        return f"{start}–{end}"

    return re.sub(r"(?<![\d.])(\d+)\s*[-–]\s*(\d+)(?![\d.])", repl, value)


def _with_year_suffix_segments(segments: list[tuple[str, dict]],
                               entry: dict) -> list[tuple[str, dict]]:
    """样式没引用 `year-suffix` 变量时，按 CSL 默认位置把后缀补在年份后面。

    规范说后缀默认跟在「cite 与文献表里 cs:date 渲染出的第一个年份」后面，是否显式渲染
    由样式决定；citeproc-py 两样都不做，所以缺了这一步的样式（如 elsevier-harvard）
    后缀根本不出现，同一作者同年的文献就撞车。
    """
    suffix = entry.get("year-suffix")
    if not suffix:
        return segments
    issued = (entry.get("issued") or {}).get("date-parts", [[None]])
    year = str(issued[0][0]) if issued and issued[0] else ""
    text = segments_text(segments)
    if not year or f"{year}{suffix}" in text:
        return segments
    return replace_first(segments, year, f"{year}{suffix}")


def separate_first_field(entry, number: int, *, number_prefix: str,
                         number_suffix: str, first_field_column: bool):
    """序号列：在样式声明的 citation-number 标记后补制表符。

    边界只认 CSL 自己写的序号前后缀，不认引擎的文本分片：IEEE 会把序号和作者放在
    同一个分片里。`first_field_column` 为假时原样返回。
    """
    segments = to_segments(entry)
    text = segments_text(segments)
    marker = f"{number_prefix}{number}{number_suffix}"
    if not first_field_column or not text.startswith(marker):
        return segments
    marker_clean = marker.rstrip()
    tail = text[len(marker):]
    leading = len(tail) - len(tail.lstrip())
    rest = slice_segments(segments, len(marker) + leading, len(text))
    return merge_segments([(marker_clean + "\t", {})] + rest)
