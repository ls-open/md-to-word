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
        items = [CitationItem(key) for key, _locator in pairs]
        citation = Citation(items)
        self._bibliography.register(citation)
        text = str(self._bibliography.cite(citation, lambda item: item))
        if narrative:
            text = _as_narrative(text)
        self._rendered[cache_key] = text
        return text

    def bibliography(self) -> list[str]:
        """文末文献列表（按引用顺序）。"""
        return [str(entry) for entry in self._bibliography.bibliography()]


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
