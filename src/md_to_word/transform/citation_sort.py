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


def _join_dates(dates: list[str], ranged: bool) -> str:
    """同一作者下的年份串；ranged 时把同年后缀连续的 ≥3 条折成 `2020a–c`。

    CSL 只在 year-suffix 系样式里折后缀，两条不折（citeproc-js 也不折）。
    """
    if not ranged:
        return ", ".join(dates)
    parts: list[str] = []
    index = 0
    while index < len(dates):
        match = _SUFFIX_DATE_RE.match(dates[index])
        if match:
            year, suffix = match.group(1), match.group(2)
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
                parts.append(f"{year}{suffix}–{label}")
                index = end + 1
                continue
        parts.append(dates[index])
        index += 1
    return ", ".join(parts)


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
