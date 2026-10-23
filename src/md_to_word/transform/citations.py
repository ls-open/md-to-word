"""md_to_word.transform.citations — 文献引用的编译（CSL）。

用 citeproc-py（2 MB，只依赖 lxml）做 CSL 渲染。实测：把我们自己的 .bib 转成
CSL-JSON 之后，两套内置样式（nature、GB/T 7714）都能正常渲染；citeproc-py 自带的 BibTeX 读取器反而不产出 `issued`，直接用会抛
VariableError——所以转换这一步由我们做（见 transform/bibtex.py）。

已知限制：citeproc-py 不支持 `suppress-author`，叙述式引用（`@key` 作句子主语）无法按
CSL 的 author-in-text 形式渲染。这里对作者-年份制做一次保守改写把年份移进括号；
数字制下与括号式相同。这条限制写在文档里，不藏着。
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Iterable, Sequence

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter
from citeproc.source import Locator
from citeproc.source.json import CiteProcJSON

from md_to_word.transform.bibtex import parse_bibtex
from md_to_word.transform.disambiguation import (
    BASE, StyleCloner, Variant, citation_attrs, initials,
)
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
        self._style = style
        self._bibliography = CitationStylesBibliography(
            style, CiteProcJSON(self.entries), formatter.html
        )
        self._known = {entry["id"] for entry in self.entries}
        self._rendered: dict[tuple, str] = {}
        self._order: list[str] = []          # 首次引用顺序（数字制就用它）
        self._by_key = {entry["id"]: entry for entry in self.entries}
        self._sorted = _declares_sort(str(csl_path))
        style_text = Path(csl_path).read_text(encoding="utf-8")
        options = citation_attrs(style_text)
        self._year_suffix = options.get("disambiguate-add-year-suffix") == "true"
        self._add_names = options.get("disambiguate-add-names") == "true"
        # 只处理作者-年份制的 collapse="year"；数字制的编号合并另有 _collapse_numeric_runs
        self._collapse = options.get("collapse") in ("year", "year-suffix", "year-suffix-ranged")
        # 数字制的连续编号合并：方括号形态（GB/T、IEEE）与上标形态（Nature、AMA）
        self._numeric = options.get("collapse") == "citation-number"
        self._expand_pages = 'page-range-format="expanded"' in style_text
        self._add_givenname = options.get("disambiguate-add-givenname") == "true"
        # by-cite 只按引用消歧；其余四种规则连「名字」一起消歧（APA 用的就是后者）
        rule = options.get("givenname-disambiguation-rule", "by-cite")
        self._rule_names = rule != "by-cite"
        self._initials_all = rule.startswith("all-names")
        self._initials_only = rule.endswith("with-initials")
        self._cloner = StyleCloner(style_text, int(options.get("et-al-use-first", "1") or 1))
        citation_block = _citation_block(style_text)
        sort_block = re.search(r"<sort>(.*?)</sort>", citation_block, re.S)
        sort_vars = re.findall(r'variable="([^"]+)"', sort_block.group(1)) if sort_block else []
        self._citation_sort = (sort_vars[0] if sort_vars else "author") if sort_block else None
        layout = re.search(r"<layout\b([^>]*)>", citation_block)
        layout_attrs = dict(re.findall(r'([\w-]+)="([^"]*)"', layout.group(1))) if layout else {}
        self._layout = (
            layout_attrs.get("prefix", ""), layout_attrs.get("suffix", ""),
            layout_attrs.get("delimiter", "; "),
        )
        self._variants: dict[str, Variant] = {}
        self._variant_cache: dict[tuple, str] = {}

    def reserve(self, keys: Iterable[str]) -> None:
        """过一遍消歧，必须在第一次 cite 之前调用。

        CSL 的顺序是：补首字母 → 补名字 → 年份后缀。前两条落在引用的**名字形态**上
        （样式副本），第三条落在**条目数据**上（`year-suffix`）。

        首字母那条是名字级的，不是引用级的：同姓不同人即使年份不同也要补（APA 8.20），
        所以按「第一作者姓」分组判定，而不是比较整条引用。
        """
        cited = [key for key in dict.fromkeys(keys) if key in self._known]
        if not cited:
            return

        if self._add_givenname and self._rule_names:
            for key, variant in self._name_variants(cited).items():
                self._variants[key] = variant

        if self._add_names:
            for group in _groups({k: self._render_single(k, self._variant(k)) for k in cited}):
                best = 0
                for extra in range(1, _max_extra_names([self._by_key[k] for k in group]) + 1):
                    candidate = Variant(extra_names=extra, initials=self._variant(group[0]).initials)
                    shown = len({self._render_single(k, candidate) for k in group})
                    if shown == len(group):
                        best = extra
                        break
                if best:
                    for key in group:
                        base = self._variant(key)
                        self._variants[key] = Variant(extra_names=best, initials=base.initials)

        if self._year_suffix:
            final = {key: self._render_single(key, self._variant(key)) for key in cited}
            for group in _groups(final):
                group.sort(key=lambda k: _sort_key(self._by_key[k]))
                for index, key in enumerate(group):
                    self._by_key[key]["year-suffix"] = _suffix_label(index)
            # 条目数据变了，重建引用源：CiteProcJSON 的条目在构造时已抓走
            self._bibliography = CitationStylesBibliography(
                self._style, CiteProcJSON(self.entries), formatter.html
            )
            self._variant_cache.clear()

    def _with_names(self, key: str, full: bool = False) -> list:
        """这条引用的条目副本：按规则给首名（或全部名字）补首字母，或展开全名。"""
        decorated = []
        for entry in self.entries:
            if entry["id"] != key:
                decorated.append(entry)
                continue
            copy = dict(entry)
            people = [dict(person) for person in (entry.get("author") or [])]
            targets = people if self._initials_all else people[:1]
            for person in targets:
                given = person.get("given", "")
                family = person.get("family")
                if given and family:
                    person["family"] = (given + " " if full else initials(given)) + family
            copy["author"] = people
            decorated.append(copy)
        return decorated

    def _variant(self, key: str) -> Variant:
        return self._variants.get(key, BASE)

    def _name_variants(self, cited: list[str]) -> dict[str, Variant]:
        """第一作者同姓不同人的，补首字母；首字母也撞的（J. Smith 有两位），展开全名。"""
        buckets: dict[str, list[str]] = {}
        for key in cited:
            people = self._by_key[key].get("author") or []
            if people:
                buckets.setdefault(people[0].get("family") or people[0].get("literal", ""), []).append(key)

        out: dict[str, Variant] = {}
        for group in buckets.values():
            firsts = [(self._by_key[k].get("author") or [{}])[0] for k in group]
            givens = {person.get("given", "") for person in firsts}
            if len(givens) < 2:
                continue
            initials_seen = {initials(given).strip() for given in givens}
            # `…-with-initials` 规则只允许补到首字母，撞了就落到年份后缀（APA 8.20 那条例外
            # 「J. Smith [John]」CSL 表达不了，写在手册的能力边界里）
            collide = len(initials_seen) < len(givens)
            full = collide and not self._initials_only
            variant = Variant(full_names=True) if full else Variant(initials=True)
            for key in group:
                out[key] = variant
        return out

    def _render_group(self, pairs) -> str:
        """逐条渲染再按样式的布局合起来：这条路上消歧形态与 collapse 归我们自己管。

        CSL 的 `collapse="year"`：同一括号里作者部分相同的几条，年份并到一处
        （`(Kim & Park, 2019, 2020a)`）。citeproc-py 不实现 collapse，也不支持逐条换形态。
        """
        prefix, suffix, delimiter = self._layout
        ordered = self._sort_pairs(pairs)
        pieces = []
        for pair in ordered:
            locator = pair[1] if len(pair) > 1 else ""
            item_prefix = pair[2] if len(pair) > 2 else ""
            label = pair[3] if len(pair) > 3 else "page"
            text = self._render(pair[0], self._variant(pair[0]), locator, item_prefix, label)
            if prefix and text.startswith(prefix):
                text = text[len(prefix):]
            if suffix and text.endswith(suffix):
                text = text[: -len(suffix)]
            pieces.append((pair[0], text))

        if not self._collapse:
            return f"{prefix}{delimiter.join(text for _key, text in pieces)}{suffix}"

        groups: list[list] = []
        for key, text in pieces:
            names, date = self._split_author(key, text)
            if names is None:
                groups.append([None, [text]])
            elif groups and groups[-1][0] == names:
                groups[-1][1].append(date)
            else:
                groups.append([names, [date]])
        body = delimiter.join(
            names + ", ".join(dates) if names else dates[0] for names, dates in groups
        )
        return f"{prefix}{body}{suffix}"

    def _sort_pairs(self, pairs) -> list:
        """按样式声明的 `<sort>` 排；没声明就保持输入顺序（CSL 的规矩）。"""
        if not self._citation_sort:
            return list(pairs)
        if self._citation_sort in ("issued", "date"):
            return sorted(pairs, key=lambda pair: _sort_key(self._by_key.get(pair[0], {}))[1:])
        return sorted(pairs, key=lambda pair: _sort_key(self._by_key.get(pair[0], {})))

    def _split_author(self, key: str, text: str):
        """把一条渲染好的引用拆成「作者部分」与「年份部分」，供 collapse 归并。"""
        year = str((self._by_key.get(key, {}).get("issued") or {}).get("date-parts", [[None]])[0][0])
        if not year or year == "None":
            return None, text
        suffix = str(self._by_key.get(key, {}).get("year-suffix", ""))
        token = year + suffix
        index = text.rfind(token)
        if index <= 0:
            return None, text
        return text[:index], text[index:]

    def _render_single(self, key: str, variant: Variant = BASE) -> str:
        """单独渲染一条引用（不带定位符），用于判断两条会不会撞。"""
        cache_key = (key, variant)
        if cache_key in self._variant_cache:
            return self._variant_cache[cache_key]
        html = self._render(key, variant, "", "")
        self._variant_cache[cache_key] = html
        return html

    def _render(self, key: str, variant: Variant, locator: str = "", prefix: str = "", label: str = "page") -> str:
        """用指定的名字形态渲染一条引用，返回 html 标记串。

        补首字母走**条目数据**（只改这条引用用的副本，文献表用的原条目不动）：CSL 没有
        「只给第一个名字加首字母」的写法，`primary-name-with-initials` 只能这么做。
        补名字走**样式副本**：显示几个名字是样式属性，条目数据改不了。
        """
        entries = self.entries
        if variant.initials or variant.full_names:
            entries = self._with_names(key, full=variant.full_names)
        style = self._style
        if variant.extra_names:
            style = CitationStylesStyle(str(self._cloner.path(Variant(extra_names=variant.extra_names))), validate=False)
        bibliography = CitationStylesBibliography(
            style, CiteProcJSON(entries), formatter.html
        )
        args: dict = {}
        if locator:
            if label == "page" and self._expand_pages:
                locator = _expand_range(locator)
            args["locator"] = Locator(label, locator)
        if prefix:
            args["prefix"] = prefix.strip() + " "
        citation = Citation([CitationItem(key, **args)])
        bibliography.register(citation)
        return _with_year_suffix(str(bibliography.cite(citation, lambda item: item)), self._by_key.get(key, {}))

    def has(self, key: str) -> bool:
        return key in self._known

    def cite(self, keys: Sequence[tuple], narrative: bool = False) -> list[tuple[str, dict]]:
        """`keys` 是 (key, locator[, prefix]) 序列；同一组只注册一次，避免重复计入编号。

        locator 与 prefix 是作者写进引用的东西（页码、`见`），丢了就是丢内容，
        所以一律带到渲染里；页码按 CSL 的 page 标签走（终稿里成 `, p. 33`）。

        返回 (文本, 格式) 片段序列——上标/斜体这类格式由 CSL 决定，不能丢成纯文本。
        """
        pairs = tuple(tuple(pair) for pair in keys)
        cache_key = (pairs, narrative)
        if cache_key in self._rendered:
            return self._rendered[cache_key]

        for pair in pairs:
            if pair[0] not in self._known:
                raise CitationError(t("citations.key_missing", self.lang, key=pair[0]))
        for pair in pairs:
            if pair[0] not in self._order:
                self._order.append(pair[0])
        items = []
        for pair in pairs:
            args: dict = {}
            locator = pair[1] if len(pair) > 1 else ""
            prefix = pair[2] if len(pair) > 2 else ""
            label = pair[3] if len(pair) > 3 else "page"
            if locator:
                if label == "page" and self._expand_pages:
                    locator = _expand_range(locator)
                args["locator"] = Locator(label, locator)
            if prefix:
                # CSL 把 prefix 当原样文本，空格要自己带
                args["prefix"] = prefix.strip() + " "
            items.append(CitationItem(pair[0], **args))
        citation = Citation(items)
        # 先登记：文献表的成员与数字制编号都靠这一步，跟怎么渲染文内引用无关
        self._bibliography.register(citation)
        if self._collapse and len(pairs) > 1:
            html = self._render_group(pairs)
        elif any(not self._variant(pair[0]).plain for pair in pairs):
            html = self._render_group(pairs)
        else:
            html = str(self._bibliography.cite(citation, lambda item: item))
        if narrative:
            html = _as_narrative(html)
        html = _collapse_numeric_runs(html, bare=self._numeric)
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
        rendered = [
            _with_year_suffix(str(entry), self._by_key.get(key, {}))
            for key, entry in zip(self._order, self._bibliography.bibliography())
        ]
        if not self._sorted or len(rendered) != len(self._order):
            return rendered

        pairs = list(zip(self._order, rendered))
        pairs.sort(key=lambda pair: _sort_key(self._by_key.get(pair[0], {})))
        return [text for _key, text in pairs]


_NUMERIC_CITE_RE = re.compile(r"\[(\d+(?:\s*[,\-–]\s*\d+)+)\]")
# 上标/无括号的数字制（Nature、AMA、Cell 一类）：`1,2,3` 也要合并
_BARE_NUMERIC_RE = re.compile(r"(?<![\d.])(\d+(?:\s*,\s*\d+){2,})(?![\d.])")


def _collapse_numeric_runs(html: str, bare: bool = False) -> str:
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

    html = _NUMERIC_CITE_RE.sub(inside_brackets, html)
    html = re.sub(r"\[\d+\](?:\s*,\s*\[\d+\]){2,}", listed_separately, html)
    if bare:
        def bare_run(match: re.Match) -> str:
            numbers = [int(n) for n in re.findall(r"\d+", match.group(0))]
            if numbers != sorted(numbers) or len(set(numbers)) != len(numbers):
                return match.group(0)
            return merge(numbers)

        html = _BARE_NUMERIC_RE.sub(bare_run, html)
    return html


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


def _author_year(entry: dict) -> tuple:
    """「同作者 + 同年」的分组键：作者（姓）序列与年份。"""
    people = entry.get("author") or entry.get("editor") or []
    names = tuple(p.get("family") or p.get("literal", "") for p in people)
    issued = (entry.get("issued") or {}).get("date-parts", [[None]])
    return (names, issued[0][0] if issued and issued[0] else None)


def _suffix_label(index: int) -> str:
    """0 → a，25 → z，26 → aa（CSL 的年份后缀序列）。"""
    label = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        label = chr(ord("a") + rest) + label
    return label


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
    title = entry.get("title", "")
    # 没有作者的条目按题名排（CSL：用 substitute 后的内容排），排在最前是错的
    names = tuple(p.get("family") or p.get("literal", "") for p in people) or (title.casefold(),)
    issued = (entry.get("issued") or {}).get("date-parts", [[9999]])
    year = issued[0][0] if issued and issued[0] else 9999
    return (names, year, title)


def _as_narrative(text: str) -> str:
    """把 `(Smith, 2024)` 改成 `Smith (2024)`；数字制 `[1]` 原样返回。

    citeproc-py 不提供 CSL 的 author-in-text 形式，这是一次保守改写：只处理「整串被一对
    圆括号包住、且括号里只有一个分号前的条目」的情形，其余原样返回，不做猜测。
    """
    stripped = text.strip()
    if not (stripped.startswith("(") and stripped.endswith(")")):
        return text
    inner = stripped[1:-1]
    # 多篇文献用 `; ` 分隔；`&amp;` 这类实体里也有分号，先去掉实体再判
    if ";" in re.sub(r"&[a-zA-Z#0-9]+;", "", inner):
        return text
    match = re.match(
        r"^(?P<author>.+?),\s*(?P<rest>\d{4}[a-z]?(?:,\s*p{1,2}\.\s*[\d\-–]+)?)$",
        inner.strip(),
    )
    if not match:
        return text
    return f"{match.group('author')} ({match.group('rest')})"


def cited_keys(model) -> list[str]:
    """文档模型里引用到的文献 key，按出现顺序去重。

    年份后缀必须在第一次渲染之前定下来，而引擎是在模型读出来之前建的，
    所以由调用方读完模型再把 key 交回去（`CitationEngine.reserve`）。
    """
    from md_to_word.model.document import Citation as CitationNode  # 与 citeproc 的 Citation 同名，别混

    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, CitationNode):
            found.extend(item.key for item in node.items)
            return
        if node is None or isinstance(node, str):
            return
        if isinstance(node, (list, tuple)):
            for child in node:
                walk(child)
            return
        if dataclasses.is_dataclass(node) and not isinstance(node, type):
            for field in dataclasses.fields(node):
                walk(getattr(node, field.name))

    walk(model)
    return list(dict.fromkeys(found))


def _unique(pairs) -> list:
    """同一条引用里同一个 key 只算一次（CSL 要求消重），定位符不同的保留第一处。"""
    seen: set = set()
    unique = []
    for pair in pairs:
        if pair[0] in seen:
            continue
        seen.add(pair[0])
        unique.append(pair)
    return unique


def _expand_range(value: str) -> str:
    """`33-5` → `33-35`（CSL 的 `page-range-format="expanded"`）。"""
    def repl(m: re.Match) -> str:
        start, end = m.group(1), m.group(2)
        if len(end) < len(start):
            end = start[: len(start) - len(end)] + end
        return f"{start}\u2013{end}"

    return re.sub(r"(?<![\d.])(\d+)\s*[-\u2013]\s*(\d+)(?![\d.])", repl, value)


def _with_year_suffix(text: str, entry: dict) -> str:
    """样式没引用 `year-suffix` 变量时，按 CSL 默认位置把后缀补在年份后面。

    规范说后缀默认跟在「cite 与文献表里 cs:date 渲染出的第一个年份」后面，是否显式渲染
    由样式决定；citeproc-py 两样都不做，所以缺了这一步的样式（如 elsevier-harvard）
    后缀根本不出现，同一作者同年的文献就撞车。
    """
    suffix = entry.get("year-suffix")
    if not suffix:
        return text
    issued = (entry.get("issued") or {}).get("date-parts", [[None]])
    year = str(issued[0][0]) if issued and issued[0] else ""
    if not year or f"{year}{suffix}" in text:
        return text
    return text.replace(year, f"{year}{suffix}", 1)


def _citation_block(style_text: str) -> str:
    start = style_text.find("<citation")
    end = style_text.find("</citation>")
    return style_text[start : end + len("</citation>")] if start >= 0 and end >= 0 else ""


def _groups(texts: dict) -> list:
    """把渲染结果相同的条目归成一组；只返回撞车的那些组。"""
    buckets: dict = {}
    for key, text in texts.items():
        buckets.setdefault(text, []).append(key)
    return [group for group in buckets.values() if len(group) > 1]


def _max_extra_names(entries: list) -> int:
    """补名字最多补到把作者全列出来为止。"""
    return max((len(entry.get("author") or entry.get("editor") or []) for entry in entries), default=1) - 1
