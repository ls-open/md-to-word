"""CSL sorting helpers that stay outside the engine.

`<sort>` evaluation itself now lives in the engine (`csl/model.py`, `Sort`/`Key`):
it renders the referenced macros, applies `names-min`/`names-use-first` and honours
`sort="descending"`. What remains here is the part CSL does not express:

- GB/T 7714-2015 §9.2 language grouping for author-date bibliographies;
- collapsing of consecutive year suffixes (`2020a–c`) for `collapse` styles.

Pure functions only.
"""

from __future__ import annotations

import re

from md_to_word.transform.disambiguation import (
    _suffix_index, _suffix_label,
)


_SUFFIX_DATE_RE = re.compile(r"^(\d{4})([a-z]+)$")


def _join_dates(dates: list[str], mode: str = "", delimiter: str = ", ") -> str:
    """同一作者下的年份串。

    `collapse="year-suffix"` 省略后一条的重复年份（`2020a, b, c`）；年份不同或没有
    后缀时印全年份。`year-suffix-ranged` 在此基础上把同年后缀连续的 ≥3 条折成
    `2020a–c`，两条不折（与 citeproc-js 一致）。`year` 或普通样式逐条印全年份。
    """
    if mode not in ("year-suffix", "year-suffix-ranged"):
        return delimiter.join(dates)

    parts: list[str] = []
    shown_year: str | None = None
    index = 0
    while index < len(dates):
        match = _SUFFIX_DATE_RE.match(dates[index])
        if not match:
            # 带定位符等尾巴的日期不参与省略，原样印出来并重置年份
            parts.append(dates[index])
            shown_year = None
            index += 1
            continue

        year, suffix = match.group(1), match.group(2)
        if mode == "year-suffix-ranged":
            start = _suffix_index(suffix)
            end = index
            while end + 1 < len(dates):
                following = _SUFFIX_DATE_RE.match(dates[end + 1])
                if (
                    not following
                    or following.group(1) != year
                    or _suffix_index(following.group(2)) != start + (end + 1 - index)
                ):
                    break
                end += 1
            if end - index + 1 >= 3:
                label = _suffix_label(start + end - index)
                head = year if year != shown_year else ""
                parts.append(f"{head}{suffix}–{label}")
                shown_year = year
                index = end + 1
                continue

        if year == shown_year:
            parts.append(suffix)
        else:
            parts.append(dates[index])
            shown_year = year
        index += 1
    return delimiter.join(parts)


_WESTERN_LANGUAGES = {
    "en", "de", "fr", "es", "it", "pt", "nl", "sv", "da", "no", "fi", "is",
    "pl", "cs", "sk", "hu", "ro", "hr", "sl", "bg", "el", "la", "et", "lv",
    "lt", "tr", "id", "ms", "vi",
}


def _language_group(entry: dict) -> int:
    """GB/T 7714 著者-年制文献表的文种序号：中文、日文、西文、俄文、其他。

    有 `language` 就按它；没有就按文字本身判——很多 BibTeX 条目不写语言，但题名和
    作者已经说明了文种。显式的 `ko` / `ar` 这类不在五组里的语言落到「其他」，不能
    因为文字不是拉丁字母就猜成西文。
    """
    language = str(entry.get("language") or "").strip().lower()
    base = re.split(r"[-_]", language)[0] if language else ""

    if base == "zh":
        return 0
    if base == "ja":
        return 1
    if base == "ru":
        return 3

    text = " ".join(
        str(part)
        for part in (
            entry.get("title"),
            entry.get("container-title"),
            *(person.get("family", "") for person in entry.get("author") or []),
        )
        if part
    )
    if re.search(r"[぀-ヿ]", text):
        return 1
    if re.search(r"[Ѐ-ӿ]", text):
        return 3
    if re.search(r"[一-鿿]", text):
        return 0
    if base in _WESTERN_LANGUAGES or re.search(r"[A-Za-zÀ-ɏ]", text):
        return 2
    return 4
