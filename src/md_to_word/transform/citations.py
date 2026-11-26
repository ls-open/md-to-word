"""md_to_word.transform.citations — 文献引用的编译（CSL）。

CSL 渲染由 `md_to_word.csl` 完成：它是 citeproc-py 0.12.2（BSD-2-Clause）的派生版，
源码就在仓库里，规范修正直接写在引擎方法中，不再靠运行期 monkey-patch。实测：把我们
自己的 .bib 转成 CSL-JSON 之后，两套内置样式（nature、GB/T 7714）都能正常渲染；
citeproc-py 自带的 BibTeX 读取器反而不产出 `issued`，直接用会抛 VariableError——所以
转换这一步由我们做（见 transform/bibtex.py）。

已知限制：citeproc-py 不支持 `suppress-author`，叙述式引用（`@key` 作句子主语）无法按
CSL 的 author-in-text 形式渲染。这里对作者-年份制做一次保守改写把年份移进括号；
数字制下与括号式相同。这条限制写在文档里，不藏着。
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Iterable, Sequence

from md_to_word.csl import (
    Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter,
)
from md_to_word.csl.formatter.segments import (
    join_segments, merge_segments, replace_first, segments_text, slice_segments,
    strip_prefix, strip_suffix, to_segments,
)
from md_to_word.csl.source import Locator
from md_to_word.csl.source.json import CiteProcJSON

from md_to_word.transform.biblio import parse_bibliography
from md_to_word.transform.disambiguation import (
    BASE, StyleCloner, Variant, citation_attrs, initials,
)
from md_to_word.i18n import t

from md_to_word.csl.model import (
    DISAMBIGUATE_KEYS as _DISAMBIGUATE_KEYS,
)


class CitationError(RuntimeError):
    """文献库或 CSL 样式无法使用。"""


class CitationEngine:
    """一份文献库 + 一个 CSL 样式 = 一个渲染器。"""

    def __init__(
        self, bib_text: str, csl_path: Path | str, lang: str = "zh",
        citation_lang: str | None = None,
    ) -> None:
        self.lang = lang
        # 消息语言与引文语言是两件事：`--lang en` 只该改提示语，不该把中文稿的
        # CSL term 换成英文（反之亦然）。流水线把文档语言单独传进来。
        self.citation_lang = citation_lang or lang
        # BibTeX / BibLaTeX 与 CSL-JSON 走同一个入口（按内容判断，不看扩展名）。
        self.entries = parse_bibliography(bib_text, lang)
        if not self.entries:
            raise CitationError(t("citations.empty_library", lang))
        try:
            style = CitationStylesStyle(
                str(csl_path),
                locale="en-US" if self.citation_lang == "en" else None,
            )
        except Exception as exc:  # 样式文件本身有问题
            raise CitationError(t("citations.style_unparsable", lang, path=csl_path, err=exc)) from exc
        # segments 而不是 plain：CSL 里的斜体、上标（Nature 的引文编号就是上标）
        # 直接作为 run 属性返回，写出器不用再从标记串里还原。
        self._style = style
        self._bibliography = CitationStylesBibliography(
            style, CiteProcJSON(self.entries), formatter.segments
        )
        self._known = {entry["id"] for entry in self.entries}
        self._rendered: dict[tuple, str] = {}
        self._order: list[str] = []          # 首次引用顺序（数字制就用它）
        self._by_key = {entry["id"]: entry for entry in self.entries}
        style_text = Path(csl_path).read_text(encoding="utf-8")
        self._number_prefix, self._number_suffix, has_citation_number = _number_affixes(style_text)
        tag = re.search(r"<bibliography\b[^>]*>", style_text)
        self._first_field_column = has_citation_number or bool(tag and 'second-field-align' in tag.group(0))
        self._sort_by_initials = _sort_names_initialized(style_text)
        self._sort_order = _declared_sort_keys(style_text)
        self._sorted = bool(self._sort_order)
        # 只有 GB/T 7714 的著者-年制要求按文种分组；数字制仍按引用顺序。
        self._gbt_language_groups = (
            "author-date" in style_text.lower() and "GB/T 7714" in style_text
        )
        options = citation_attrs(style_text)
        self._year_suffix = options.get("disambiguate-add-year-suffix") == "true"
        self._add_names = options.get("disambiguate-add-names") == "true"
        mode = options.get("collapse", "")
        self._collapse = mode in ("year", "year-suffix", "year-suffix-ranged")
        # 后缀区间只有 year-suffix 系样式才折（CSL 的 year-suffix-ranged）；
        # collapse="year" 与数字制该逐条列出，不能折
        self._collapse_ranged = mode in ("year-suffix", "year-suffix-ranged")
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
        self._disambiguate_keys: set[str] = set()

    def reserve(self, keys: Iterable[str]) -> None:
        """过一遍消歧，必须在第一次 cite 之前调用。

        CSL 的顺序是：补首字母 → 补名字 → `<if disambiguate="true">` → 年份后缀。
        前两条落在引用的**名字形态**上（样式副本/临时名），第三条通过上下文激活样式的
        `disambiguate="true"` 条件分支，第四条落在**条目数据**上（`year-suffix`）。

        首字母在 `primary-name*` 规则下是名字级的：同姓不同人即使年份不同也要补（APA 8.20），
        所以按「第一作者姓」分组判定；在 `by-cite` 规则（如 MLA、Harvard）下仅对撞车的引用组补。
        """
        cited = [key for key in dict.fromkeys(keys) if key in self._known]
        if not cited:
            return

        self._disambiguate_keys = set()
        if self._add_givenname:
            if self._rule_names:
                for key, variant in self._name_variants(cited).items():
                    self._variants[key] = variant
            else:
                for group in _groups({k: segments_text(self._render_single(k, self._variant(k))) for k in cited}):
                    for key, variant in self._resolve_given_variants(group).items():
                        self._variants[key] = variant

        if self._add_names:
            for group in _groups({k: segments_text(self._render_single(k, self._variant(k))) for k in cited}):
                best = 0
                for extra in range(1, _max_extra_names([self._by_key[k] for k in group]) + 1):
                    shown = len({
                        segments_text(self._render_single(
                            k,
                            Variant(
                                extra_names=extra,
                                initials=self._variant(k).initials,
                                full_names=self._variant(k).full_names,
                            ),
                        ))
                        for k in group
                    })
                    if shown == len(group):
                        best = extra
                        break
                if best:
                    for key in group:
                        base = self._variant(key)
                        self._variants[key] = Variant(
                            extra_names=best, initials=base.initials, full_names=base.full_names
                        )

        remaining = _groups({k: segments_text(self._render_single(k, self._variant(k))) for k in cited})
        if remaining:
            self._disambiguate_keys = {k for group in remaining for k in group}
            self._variant_cache.clear()

        if self._year_suffix:
            final = {key: segments_text(self._render_single(key, self._variant(key))) for key in cited}
            for group in _groups(final):
                group = self._sorted_keys(group)
                for index, key in enumerate(group):
                    self._by_key[key]["year-suffix"] = _suffix_label(index)
            # 条目数据变了，重建引用源：CiteProcJSON 的条目在构造时已抓走
            self._bibliography = CitationStylesBibliography(
                self._style, CiteProcJSON(self.entries), formatter.segments
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
            role = "author" if entry.get("author") else ("editor" if entry.get("editor") else None)
            if role:
                people = [dict(person) for person in entry[role]]
                targets = people if self._initials_all else people[:1]
                for person in targets:
                    given = person.get("given", "")
                    family = person.get("family")
                    if given and family:
                        person["family"] = (given + " " if full else initials(given)) + family
                copy[role] = people
            decorated.append(copy)
        return decorated

    def _variant(self, key: str) -> Variant:
        return self._variants.get(key, BASE)

    def _resolve_given_variants(self, group: list[str]) -> dict[str, Variant]:
        """同一同姓组（或同撞车引用组）里，按首字母子组决定补首字母还是展开全名。"""
        firsts = [((self._by_key[k].get("author") or self._by_key[k].get("editor") or [{}])[0]) for k in group]
        givens = {person.get("given", "") for person in firsts}
        if len(givens) < 2:
            return {}
        if self._initials_only:
            variant = Variant(initials=True)
            return {key: variant for key in group}
        by_init: dict[str, list[tuple[str, str]]] = {}
        for key, person in zip(group, firsts):
            given = person.get("given", "")
            by_init.setdefault(initials(given).strip(), []).append((key, given))
        out: dict[str, Variant] = {}
        for items in by_init.values():
            distinct = {given for _k, given in items}
            variant = Variant(full_names=True) if len(distinct) >= 2 else Variant(initials=True)
            for key, _given in items:
                out[key] = variant
        return out

    def _name_variants(self, cited: list[str]) -> dict[str, Variant]:
        """第一作者同姓不同人的，补首字母；首字母也撞的（J. Smith 有两位），按子组展开全名。"""
        buckets: dict[str, list[str]] = {}
        for key in cited:
            people = self._by_key[key].get("author") or self._by_key[key].get("editor") or []
            if people:
                buckets.setdefault(people[0].get("family") or people[0].get("literal", ""), []).append(key)

        out: dict[str, Variant] = {}
        for group in buckets.values():
            out.update(self._resolve_given_variants(group))
        return out

    def _render_group(self, pairs) -> list[tuple[str, dict]]:
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
            text = strip_prefix(text, prefix)
            text = strip_suffix(text, suffix)
            pieces.append((pair[0], text))

        if not self._collapse:
            body = join_segments([text for _key, text in pieces], delimiter)
            return merge_segments([(prefix, {})] + body + [(suffix, {})])

        groups: list[dict] = []
        for key, text in pieces:
            names, date = self._split_author(key, text)
            if names is None:
                groups.append({"names": None, "segments": text, "dates": [text]})
                continue
            names_text = segments_text(names)
            if groups and groups[-1]["names"] == names_text:
                groups[-1]["dates"].append(date)
            else:
                groups.append({"names": names_text, "segments": names, "dates": [date]})

        body_pieces = []
        for group in groups:
            if group["names"] is None:
                body_pieces.append(group["segments"])
            else:
                body_pieces.append(
                    group["segments"]
                    + [(_join_dates(group["dates"], self._collapse_ranged), {})]
                )
        body = join_segments(body_pieces, delimiter)
        return merge_segments([(prefix, {})] + body + [(suffix, {})])

    def _sort_pairs(self, pairs) -> list:
        """按样式声明的 `<sort>` 排；没声明就保持输入顺序（CSL 的规矩）。"""
        if not self._citation_sort:
            return list(pairs)
        kind = "year" if self._citation_sort in ("issued", "date") else "names"
        return sorted(
            pairs,
            key=lambda pair: _sort_value(kind, self._by_key.get(pair[0], {}), self._sort_by_initials),
        )

    def _split_author(self, key: str, segments: list[tuple[str, dict]]):
        """把一条渲染好的引用拆成「作者部分」与「年份部分」，供 collapse 归并。"""
        year = str((self._by_key.get(key, {}).get("issued") or {}).get("date-parts", [[None]])[0][0])
        if not year or year == "None":
            return None, ""
        suffix = str(self._by_key.get(key, {}).get("year-suffix", ""))
        token = year + suffix
        text = segments_text(segments)
        index = text.rfind(token)
        if index <= 0:
            return None, ""
        return slice_segments(segments, 0, index), text[index:]

    def _render_single(self, key: str, variant: Variant = BASE) -> list[tuple[str, dict]]:
        """单独渲染一条引用（不带定位符），用于判断两条会不会撞。"""
        cache_key = (key, variant)
        if cache_key in self._variant_cache:
            return self._variant_cache[cache_key]
        rendered = self._render(key, variant, "", "")
        self._variant_cache[cache_key] = rendered
        return rendered

    def _render(self, key: str, variant: Variant, locator: str = "",
                prefix: str = "", label: str = "page") -> list[tuple[str, dict]]:
        """用指定的名字形态渲染一条引用，返回结构化片段。

        补首字母走**条目数据**（只改这条引用用的副本，文献表用的原条目不动）：CSL 没有
        「只给第一个名字加首字母」的写法，`primary-name-with-initials` 只能这么做。
        补名字走**样式副本**：显示几个名字是样式属性，条目数据改不了。
        """
        entries = self.entries
        if variant.initials or variant.full_names:
            entries = self._with_names(key, full=variant.full_names)
        style = self._style
        if variant.extra_names:
            style = CitationStylesStyle(str(self._cloner.path(Variant(extra_names=variant.extra_names))))
        bibliography = CitationStylesBibliography(
            style, CiteProcJSON(entries), formatter.segments
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
        token = _DISAMBIGUATE_KEYS.set(frozenset(self._disambiguate_keys))
        try:
            rendered = to_segments(bibliography.cite(citation, lambda item: item))
        finally:
            _DISAMBIGUATE_KEYS.reset(token)
        return _with_year_suffix_segments(rendered, self._by_key.get(key, {}))

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
        token = _DISAMBIGUATE_KEYS.set(frozenset(self._disambiguate_keys))
        try:
            if self._collapse and len(pairs) > 1:
                segments = self._render_group(pairs)
            elif any(not self._variant(pair[0]).plain for pair in pairs):
                segments = self._render_group(pairs)
            else:
                segments = to_segments(
                    self._bibliography.cite(citation, lambda item: item))
        finally:
            _DISAMBIGUATE_KEYS.reset(token)
        if narrative:
            entry = self._by_key.get(pairs[0][0], {}) if len(pairs) == 1 else {}
            creators = entry.get("author") or entry.get("editor") or []
            and_word = "and" if self.citation_lang == "en" and len(creators) >= 2 else None
            segments = _as_narrative_segments(segments, and_word=and_word)
        segments = _merge_period_segments(
            _collapse_numeric_segments(segments, bare=self._numeric))
        self._rendered[cache_key] = segments
        return segments

    def bibliography_entries(self):
        """(key, 片段序列)——写出器要用 key 建书签、用片段还原斜体。"""
        return self.bibliography_segments()

    def _sorted_keys(self, keys) -> list[str]:
        """按 `<sort>` 声明的键序与方向排。

        多字段混搭（作者升序、年份降序）靠稳定排序从最后一条键往前做，一趟一条键；
        把几条键塞进一个元组是做不到的——元组里没法让某一项逆序。
        """
        result = list(keys)
        for kind, descending in reversed(self._sort_order):
            result.sort(
                key=lambda key: _sort_value(kind, self._by_key.get(key, {}), self._sort_by_initials),
                reverse=descending,
            )
        return result

    def _ordered_keys(self) -> list[str]:
        keys = self._sorted_keys(self._order) if self._sorted else list(self._order)
        if self._gbt_language_groups:
            # GB/T 7714-2015 §9.2：著者-年制先按文种集中，再按作者/年份。
            # 稳定排序保留组内已有的 `<sort>` 次序。
            keys.sort(key=lambda key: _language_group(self._by_key.get(key, {})))
        return keys

    def bibliography_segments(self) -> list[tuple[str, list[tuple[str, dict]]]]:
        """(key, 片段序列)——写出器要用 key 建书签、用片段还原斜体。"""
        segments = self._bibliography_segments()
        keys = self._ordered_keys()
        if len(keys) != len(segments):
            return [(f"item{i}", segs) for i, segs in enumerate(segments)]
        return list(zip(keys, segments))

    def _bibliography_segments(self) -> list[list[tuple[str, dict]]]:
        rendered = [
            _merge_period_segments(
                _with_year_suffix_segments(
                    self._separate_first_field(entry, number),
                    self._by_key.get(key, {}),
                )
            )
            for number, (key, entry)
            in enumerate(zip(self._order, self._bibliography.bibliography()), start=1)
        ]
        if not self._sorted or len(rendered) != len(self._order):
            return rendered
        by_key = dict(zip(self._order, rendered))
        return [by_key[key] for key in self._ordered_keys()]

    def bibliography(self) -> list[str]:
        """文末文献列表（纯文本；要片段用 bibliography_segments）。

        顺序分两种：CSL 在 `<bibliography>` 里声明了 `<sort>` 的（作者-年份制）按声明的键序
        与方向排；没声明的（数字顺序制，如 GB/T 7714、Nature）按首次引用顺序。

        `citeproc-py` 有 `style.sort_bibliography()`，但实测不生效（apa.csl 依旧按注册顺序
        返回），所以这里自己做：键序、升降序、名的形态都取自样式本身，见
        `_declared_sort_keys` 与 `_sort_names_initialized`。
        """
        return [segments_text(segs) for segs in self._bibliography_segments()]

    def _separate_first_field(self, entry, number: int) -> list[tuple[str, dict]]:
        """顺序数字制或 `second-field-align` 声明了「首个字段自成一栏」：在序号后面补一个制表符。

        `citeproc-py` 从不落实这个属性，序号会直接贴住条目正文（例如 `[1]Smith`、`1.Smith`）。
        而它的分片**不是**按字段切的（IEEE 给出的是 `'[1]J. Doe and J. Roe, '`，序号和作者在
        同一个分片里），所以边界只能从 CSL 自己写的序号前后缀来：样式里那只 `citation-number`
        长什么样，产物里序号就长什么样。

        用制表符而非空格——`参考文献` 带悬挂缩进时，制表位正落在缩进处，首行文字与折行文字对齐成列。
        """
        segments = to_segments(entry)
        text = segments_text(segments)
        marker = f"{self._number_prefix}{number}{self._number_suffix}"
        if not self._first_field_column or not text.startswith(marker):
            return segments
        marker_clean = marker.rstrip()
        tail = text[len(marker):]
        leading = len(tail) - len(tail.lstrip())
        rest = slice_segments(segments, len(marker) + leading, len(text))
        return merge_segments([(marker_clean + "\t", {})] + rest)


def _number_affixes(style_text: str) -> tuple[str, str, bool]:
    """`<bibliography>` 里 `citation-number` 的前后缀：序号那一栏实际印成什么样。

    返回 (prefix, suffix, has_citation_number)。
    """
    block = re.search(r"<bibliography\b.*?</bibliography>", style_text, re.DOTALL)
    tag = block and re.search(r'<text\b[^>]*variable="citation-number"[^>]*>', block.group(0))
    if not tag:
        return "", "", False

    def attr(name: str) -> str:
        found = re.search(rf'{name}="([^"]*)"', tag.group(0))
        return found.group(1) if found else ""

    return attr("prefix"), attr("suffix"), True


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


def _suffix_label(index: int) -> str:
    """0 → a，25 → z，26 → aa（CSL 的年份后缀序列）。"""
    label = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        label = chr(ord("a") + rest) + label
    return label


def _suffix_index(label: str) -> int:
    """`_suffix_label` 的逆：a → 0，aa → 26。"""
    index = 0
    for char in label:
        index = index * 26 + ord(char) - ord("a") + 1
    return index - 1


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


def _expand_range(value: str) -> str:
    """`33-5` → `33-35`（CSL 的 `page-range-format="expanded"`）。"""
    def repl(m: re.Match) -> str:
        start, end = m.group(1), m.group(2)
        if len(end) < len(start):
            end = start[: len(start) - len(end)] + end
        return f"{start}\u2013{end}"

    return re.sub(r"(?<![\d.])(\d+)\s*[-\u2013]\s*(\d+)(?![\d.])", repl, value)


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
