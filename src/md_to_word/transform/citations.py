"""md_to_word.transform.citations — 文献引用的编译（CSL）。

用 citeproc-py（2 MB，只依赖 lxml）做 CSL 渲染，而不是为了引文装一个近 1 GB 的
Quarto。实测：把我们自己的 .bib 转成 CSL-JSON 之后，两套内置样式（nature、GB/T 7714）
都能正常渲染；citeproc-py 自带的 BibTeX 读取器反而不产出 `issued`，直接用会抛
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


class CitationError(RuntimeError):
    """文献库或 CSL 样式无法使用。"""


class CitationEngine:
    """一份文献库 + 一个 CSL 样式 = 一个渲染器。"""

    def __init__(self, bib_text: str, csl_path: Path | str) -> None:
        self.entries = parse_bibtex(bib_text)
        if not self.entries:
            raise CitationError("文献库里没有可用条目")
        try:
            style = CitationStylesStyle(str(csl_path), validate=False)
        except Exception as exc:  # 样式文件本身有问题
            raise CitationError(f"CSL 样式无法解析：{csl_path}（{exc}）") from exc
        self._bibliography = CitationStylesBibliography(
            style, CiteProcJSON(self.entries), formatter.plain
        )
        self._known = {entry["id"] for entry in self.entries}
        self._rendered: dict[tuple, str] = {}
        self._order: list[str] = []          # 首次引用顺序（数字制就用它）
        self._by_key = {entry["id"]: entry for entry in self.entries}
        self._sorted = _declares_sort(str(csl_path))

    def has(self, key: str) -> bool:
        return key in self._known

    def cite(self, keys: Sequence[tuple[str, str]], narrative: bool = False) -> str:
        """`keys` 是 (key, locator) 序列；同一组只注册一次，避免重复计入编号。"""
        pairs = tuple(keys)
        cache_key = (pairs, narrative)
        if cache_key in self._rendered:
            return self._rendered[cache_key]

        for key, _locator in pairs:
            if key not in self._known:
                raise CitationError(f"文献库里没有条目：{key}")
        for key, _locator in pairs:
            if key not in self._order:
                self._order.append(key)
        items = [CitationItem(key) for key, _locator in pairs]
        citation = Citation(items)
        self._bibliography.register(citation)
        text = str(self._bibliography.cite(citation, lambda item: item))
        if narrative:
            text = _as_narrative(text)
        self._rendered[cache_key] = text
        return text

    def bibliography_entries(self) -> list[tuple[str, str]]:
        """(key, 渲染文本) 列表，顺序与 bibliography() 一致——写出器要用 key 建书签。"""
        texts = self.bibliography()
        keys = self._ordered_keys()
        if len(keys) != len(texts):
            return [(f"item{i}", text) for i, text in enumerate(texts)]
        return list(zip(keys, texts))

    def _ordered_keys(self) -> list[str]:
        keys = list(self._order)
        if self._sorted:
            keys.sort(key=lambda k: _sort_key(self._by_key.get(k, {})))
        return keys

    def bibliography(self) -> list[str]:
        """文末文献列表。

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
