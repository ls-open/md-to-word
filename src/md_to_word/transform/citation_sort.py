"""CSL sorting and bibliography grouping for the citation adapter.

The engine's own `<sort>` support is not enough for per-item name variants and
GB/T 115 language grouping, so the adapter evaluates the four sort-key kinds it
understands and orders entries itself. Pure functions only.
"""

from __future__ import annotations

import re

from md_to_word.transform.disambiguation import (
    _suffix_index, _suffix_label, initials,
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


def _declared_sort_keys(style_text: str) -> tuple[tuple[str, bool], ...]:
    """`<bibliography><sort>` 里声明了哪几条排序键、各自升序还是降序。

    CSL 把排序写成一串 `<key>`，每条指向一个宏或变量，还能带 `sort="descending"`。
    完整求值宏是不必的——我们只认得出「作者 / 年份 / 题名 / 状态」四类，其余（卷号、
    来源、事件日期这类）直接跳过：跳过的键只在前面几条全打平时才起作用。
    """
    bibliography = re.search(r"<bibliography\b.*?</bibliography>", style_text, re.S)
    sort = re.search(r"<sort>(.*?)</sort>", bibliography.group(0), re.S) if bibliography else None
    if sort is None:
        return ()

    keys: list[tuple[str, bool]] = []
    for attrs in re.findall(r"<key\b([^>]*)>", sort.group(1)):
        target = re.search(r'(?:macro|variable)="([^"]+)"', attrs)
        kind = _sort_kind(target.group(1)) if target else ""
        # 连着几条同类的键（APA 的 date-sort-group + date-sort）合成一条
        if not kind or (keys and keys[-1][0] == kind):
            continue
        keys.append((kind, 'sort="descending"' in attrs))
    return tuple(keys)


def _sort_kind(name: str) -> str:
    """一条 `<key>` 指向宏名或变量名，归到我们排序时认的四类之一；认不出返回空串。"""
    lowered = name.lower()
    if lowered.startswith(("author", "editor", "contributor", "composer")):
        return "names"
    if lowered in ("issued", "year") or lowered.startswith(("date", "year")):
        return "year"
    if lowered.startswith("title"):
        return "title"
    return "status" if lowered == "status" else ""


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


def _sort_value(kind: str, entry: dict, by_initials: bool = True):
    """条目在某一类排序键上的取值。

    作者按 `(姓, 名)` 逐位比较，名**不能省**：只比姓的话同姓不同人撞成一个键，顺序掉到
    年份上——`Li, C. (2023)` 会排到 `Li, M. (2021)` 后面。名的形态由样式决定
    （见 `_sort_names_initialized`）。
    """
    if kind == "names":
        people = entry.get("author") or entry.get("editor") or []
        title = entry.get("title", "")
        # 没有作者的条目按题名排（CSL：用 substitute 后的内容排），排在最前是错的
        return tuple(
            (
                (p.get("family") or p.get("literal") or "").casefold(),
                (
                    initials(p.get("given") or "", "")
                    if by_initials
                    else " ".join((p.get("given") or "").split())
                ).casefold(),
            )
            for p in people
        ) or ((title.casefold(), ""),)
    if kind == "year":
        issued = (entry.get("issued") or {}).get("date-parts", [[9999]])
        return issued[0][0] if issued and issued[0] else 9999
    if kind == "title":
        return entry.get("title", "").casefold()
    return entry.get("status", "") or ""


def _sort_names_initialized(style_text: str) -> bool:
    """排序键里的名是按首字母还是按全名比：看排序宏里那个 `name-as-sort-order` 的 `<name>`。

    APA 的 `author-sort` 一路指到 `<name name-as-sort-order="all"/>`，样式根上又写了
    `initialize-with=". "`，于是名收成首字母；Chicago 与 MLA 在同一处写了
    `initialize="false"`，比的是全名。两档结果不同：APA 里 `C. 2019` 排在 `C. 2023` 前
    （首字母分不开，落到年份），Chicago 里 `Chaoyang` 排在 `Chen` 前（全名分得开）。
    两边都以 citeproc-js 的输出为准。
    """
    macros = dict(re.findall(r'<macro name="([^"]+)">(.*?)</macro>', style_text, re.S))
    bibliography = re.search(r"<bibliography\b.*?</bibliography>", style_text, re.S)
    sort = re.search(r"<sort>.*?</sort>", bibliography.group(0), re.S) if bibliography else None
    keys = re.findall(r'<key macro="([^"]+)"', sort.group(0)) if sort else []
    if not keys:
        return True

    # 只跟第一条 key（作者）；后面的日期、题名 key 与名字形态无关，跟进去只会撞上
    # 标题宏里那些编辑者名字
    pending, seen, name_els = [keys[0]], set(), []
    while pending:
        macro = pending.pop()
        if macro in seen or macro not in macros:
            continue
        seen.add(macro)
        body = macros[macro]
        name_els += [
            element
            for element in re.findall(r"<name\b[^>]*>", body)
            if "name-as-sort-order" in element
        ]
        pending += re.findall(r'macro="([^"]+)"', body)

    if any('initialize="false"' in element for element in name_els):
        return False
    # `initialize-with` 可能写在 `<name>` 上（Harvard），也可能写在样式根上（APA）
    if any("initialize-with" in element for element in name_els):
        return True
    return bool(re.search(r'<style\b[^>]*initialize-with=', style_text))
