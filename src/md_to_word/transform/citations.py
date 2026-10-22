"""md_to_word.transform.citations — 文献引用的编译（CSL）。

用 citeproc-py（2 MB，只依赖 lxml）做 CSL 渲染。实测：把我们自己的 .bib 转成
CSL-JSON 之后，两套内置样式（nature、GB/T 7714）都能正常渲染；citeproc-py 自带的 BibTeX 读取器反而不产出 `issued`，直接用会抛
VariableError——所以转换这一步由我们做（见 transform/bibtex.py）。

已知限制：citeproc-py 不支持 `suppress-author`，叙述式引用（`@key` 作句子主语）无法按
CSL 的 author-in-text 形式渲染。这里对作者-年份制做一次保守改写把年份移进括号；
数字制下与括号式相同。这条限制写在文档里，不藏着。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter
from citeproc.source.json import CiteProcJSON

from md_to_word.transform.bibtex import parse_bibtex
from md_to_word.i18n import t


class CitationError(RuntimeError):
    """文献库或 CSL 样式无法使用。"""


class CitationEngine:
    """一份文献库 + 一个 CSL 样式 = 一个渲染器。"""

    def __init__(self, bib_text: str, csl_path: Path | str, lang: str = "zh") -> None:
        self.lang = lang
        self.entries = parse_bibtex(bib_text)
        if not self.entries:
            raise CitationError(t("citations.empty_library", lang))
        try:
            style = CitationStylesStyle(str(csl_path), validate=False)
        except Exception as exc:  # 样式文件本身有问题
            raise CitationError(t("citations.style_unparsable", lang, path=csl_path, err=exc)) from exc
        # html 而不是 plain：CSL 里的斜体、上标（Nature 的引文编号就是上标）只有带标记
        # 才能还原。返回给我们自己解析，最终落成带格式的 run。
        self._bibliography = CitationStylesBibliography(
            style, CiteProcJSON(self.entries), formatter.html
        )
        self._known = {entry["id"] for entry in self.entries}
        self._rendered: dict[tuple, str] = {}
        self._order: list[str] = []          # 首次引用顺序（数字制就用它）
        self._by_key = {entry["id"]: entry for entry in self.entries}
        self._sorted = _declares_sort(str(csl_path))

    def has(self, key: str) -> bool:
        return key in self._known

    def cite(self, keys: Sequence[tuple[str, str]], narrative: bool = False) -> list[tuple[str, dict]]:
        """`keys` 是 (key, locator) 序列；同一组只注册一次，避免重复计入编号。

        返回 (文本, 格式) 片段序列——上标/斜体这类格式由 CSL 决定，不能丢成纯文本。
        """
        pairs = tuple(keys)
        cache_key = (pairs, narrative)
        if cache_key in self._rendered:
            return self._rendered[cache_key]

        for key, _locator in pairs:
            if key not in self._known:
                raise CitationError(t("citations.key_missing", self.lang, key=key))
        for key, _locator in pairs:
            if key not in self._order:
                self._order.append(key)
        items = [CitationItem(key) for key, _locator in pairs]
        citation = Citation(items)
        self._bibliography.register(citation)
        html = str(self._bibliography.cite(citation, lambda item: item))
        if narrative:
            html = _as_narrative(html)
        html = _collapse_numeric_runs(html)
        segments = html_to_segments(html)
        self._rendered[cache_key] = segments
        return segments

    def bibliography_entries(self):
        """(key, 片段序列)——写出器要用 key 建书签、用片段还原斜体。"""
        return self.bibliography_segments()

    def _ordered_keys(self) -> list[str]:
        keys = list(self._order)
        if self._sorted:
            keys.sort(key=lambda k: _sort_key(self._by_key.get(k, {})))
        return keys

    def bibliography_segments(self) -> list[tuple[str, list[tuple[str, dict]]]]:
        """(key, 片段序列)——写出器要用 key 建书签、用片段还原斜体。"""
        texts = self.bibliography()
        keys = self._ordered_keys()
        if len(keys) != len(texts):
            return [(f"item{i}", html_to_segments(t)) for i, t in enumerate(texts)]
        return list(zip(keys, [html_to_segments(t) for t in texts]))

    def bibliography(self) -> list[str]:
        """文末文献列表（仍是 html 标记串；要片段用 bibliography_segments）。

        顺序分两种：CSL 在 `<bibliography>` 里声明了 `<sort>` 的（作者-年份制）按作者与年份
        排；没声明的（数字顺序制，如 GB/T 7714、Nature）按首次引用顺序。

        `citeproc-py` 有 `style.sort_bibliography()`，但实测不生效（ape.csl 依旧按注册顺序
        返回），所以这里自己做。排序键用条目字段近似 CSL 的宏排序——够覆盖作者-年份制。
        """
        rendered = [str(entry) for entry in self._bibliography.bibliography()]
        if not self._sorted or len(rendered) != len(self._order):
            return rendered

        pairs = list(zip(self._order, rendered))
        pairs.sort(key=lambda pair: _sort_key(self._by_key.get(pair[0], {})))
        return [text for _key, text in pairs]


_NUMERIC_CITE_RE = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)+)\]")


def _collapse_numeric_runs(html: str) -> str:
    """数字制的连续编号合并成区间：`[4,5,6]` → `[4–6]`。

    这是 GB/T 7714 与 IEEE 这类数字制的硬要求，citeproc-py 只管把编号一个个列出来。
    三条以上的连续号才合并，`[4,5]` 保持原样。
    """

    def repl(match: re.Match) -> str:
        numbers = [int(n) for n in re.findall(r"\d+", match.group(1))]
        if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
            return match.group(0)
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
        return "[" + ",".join(parts) + "]"

    return _NUMERIC_CITE_RE.sub(repl, html)


_TAG_RE = re.compile(r"</?(?P<tag>i|b|sup|sub|sc|span)[^>]*>")
_TAG_FMT = {"i": "italic", "b": "bold", "sup": "superscript", "sub": "subscript"}


def html_to_segments(html: str) -> list[tuple[str, dict]]:
    """citeproc 的 html 输出 → (文本, 格式) 片段。只认 i/b/sup/sub，其余标签当分隔符丢掉。"""
    from html import unescape

    segments: list[tuple[str, dict]] = []
    stack: list[str] = []
    pos = 0
    for match in _TAG_RE.finditer(html or ""):
        if match.start() > pos:
            text = unescape(html[pos : match.start()])
            fmt = {_TAG_FMT[t]: True for t in stack if t in _TAG_FMT}
            if text:
                segments.append((text, fmt))
        tag = match.group("tag")
        if match.group(0).startswith("</"):
            if tag in stack:
                stack.reverse()
                stack.remove(tag)
                stack.reverse()
        else:
            stack.append(tag)
        pos = match.end()
    if pos < len(html or ""):
        text = unescape(html[pos:])
        fmt = {_TAG_FMT[t]: True for t in stack if t in _TAG_FMT}
        if text:
            segments.append((text, fmt))
    return segments or [(unescape(html or ""), {})]


def _declares_sort(csl_path: str) -> bool:
    try:
        import re as _re

        content = Path(csl_path).read_text(encoding="utf-8")
    except OSError:
        return False
    block = _re.search(r"<bibliography.*?</bibliography>", content, _re.S)
    return bool(block and "<sort>" in block.group(0))


def _sort_key(entry: dict) -> tuple:
    """作者（姓）→ 年份 → 题名。够近似 CSL 里 author/date/title 那几条 key。"""
    people = entry.get("author") or entry.get("editor") or []
    names = tuple(p.get("family") or p.get("literal", "") for p in people)
    issued = (entry.get("issued") or {}).get("date-parts", [[9999]])
    year = issued[0][0] if issued and issued[0] else 9999
    return (names, year, entry.get("title", ""))


def _as_narrative(text: str) -> str:
    """把 `(Smith, 2024)` 改成 `Smith (2024)`；数字制 `[1]` 原样返回。

    citeproc-py 不提供 CSL 的 author-in-text 形式，这是一次保守改写：只处理「整串被一对
    圆括号包住、且括号里只有一个分号前的条目」的情形，其余原样返回，不做猜测。
    """
    stripped = text.strip()
    if not (stripped.startswith("(") and stripped.endswith(")")):
        return text
    inner = stripped[1:-1]
    if ";" in inner:
        return text
    match = re.match(r"^(?P<author>.+?),\s*(?P<year>\d{4}[a-z]?)$", inner.strip())
    if not match:
        return text
    return f"{match.group('author')} ({match.group('year')})"
