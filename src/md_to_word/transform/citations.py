"""md_to_word.transform.citations — 文献引用的编译（CSL）。

CSL 渲染由 `md_to_word.csl` 完成：它是 citeproc-py 0.12.2（BSD-2-Clause）的派生版，
源码就在仓库里，规范修正直接写在引擎方法中，不再靠运行期 monkey-patch。实测：把我们
自己的 .bib 转成 CSL-JSON 之后，两套内置样式（nature、GB/T 7714）都能正常渲染；
citeproc-py 自带的 BibTeX 读取器反而不产出 `issued`，直接用会抛 VariableError——所以
转换这一步由我们做（见 transform/bibtex.py）。

已知限制：citeproc-py 不支持 `suppress-author`，叙述式引用（`@key` 作句子主语）无法按
CSL 的 author-in-text 形式渲染。这里对作者-年份制做一次保守改写把年份移进括号；
数字制下与括号式相同。这条限制写在文档里，不藏着。

分阶段：`csl/` 负责求值与排序（`<sort>` 里的宏由引擎求值）；`citation_sort.py`
补 CSL 不表达的 GB/T 文种分组与年份后缀折叠；`disambiguation.py` 消歧；
`citation_postprocess.py` 输出修正（数字合并、标点、年份后缀等）；本文件只做编排与
公开 API。
"""

from __future__ import annotations

import dataclasses
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Sequence

from md_to_word.csl import (
    Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter,
)
from md_to_word.csl.formatter.segments import (
    join_segments, merge_segments, segments_text, slice_segments,
    strip_prefix, strip_suffix, to_segments,
)
from md_to_word.csl.features import CslFeatureError, check_style
from md_to_word.csl.source import Locator
from md_to_word.csl.source.json import CiteProcJSON

from md_to_word.transform.biblio import parse_bibliography
from md_to_word.transform.citation_postprocess import (
    _as_narrative_segments, _collapse_numeric_runs as _collapse_numeric_runs, _collapse_numeric_segments,
    _expand_range, _merge_period_segments, _with_year_suffix_segments,
    separate_first_field,
)
from md_to_word.transform.citation_sort import _join_dates, _language_group
from md_to_word.transform.disambiguation import (
    BASE, StyleCloner, Variant, _suffix_label, citation_attrs, groups,
    max_extra_names, name_variants, resolve_given_variants, with_names,
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
            check_style(csl_path)
        except CslFeatureError as exc:
            raise CitationError(t(
                "citations.style_unsupported", lang,
                feature="; ".join(exc.errors), path=csl_path,
            )) from exc
        self._style_locale = "en-US" if self.citation_lang == "en" else None
        try:
            style = CitationStylesStyle(str(csl_path), locale=self._style_locale)
        except Exception as exc:  # 样式文件本身有问题
            raise CitationError(t("citations.style_unparsable", lang, path=csl_path, err=exc)) from exc
        # segments 而不是 plain：CSL 里的斜体、上标（Nature 的引文编号就是上标）
        # 直接作为 run 属性返回，写出器不用再从标记串里还原。
        self._style = style
        # 条目数据只解析一次：CiteProcJSON 会把每条字符串拆成结构化 run，120 条就要
        # 几毫秒。原先每次试探渲染都重建一遍，reserve() 的耗时基本都是它。
        self._source = CiteProcJSON(self.entries)
        self._name_sources: dict[tuple, CiteProcJSON] = {}
        self._cloned_styles: dict[int, CitationStylesStyle] = {}
        self._bibliography = CitationStylesBibliography(
            style, self._source, formatter.segments
        )
        self._known = {entry["id"] for entry in self.entries}
        self._rendered: dict[tuple, str] = {}
        self._order: list[str] = []          # 首次引用顺序（数字制就用它）
        self._by_key = {entry["id"]: entry for entry in self.entries}
        style_text = Path(csl_path).read_text(encoding="utf-8")
        self._number_prefix, self._number_suffix, has_citation_number = _number_affixes(style_text)
        tag = re.search(r"<bibliography\b[^>]*>", style_text)
        self._first_field_column = has_citation_number or bool(tag and 'second-field-align' in tag.group(0))
        # 排序交给引擎：`<key>` 指向的是宏，按名字猜类别会漏掉 `issued-year`、
        # `responsability` 这类宏名。引擎的 `Sort` 会真的渲染宏，并按
        # `names-min` / `sort="descending"` 求值。
        bibliography = self._style.root.bibliography
        citation = self._style.root.citation
        self._bib_sort = bibliography.sort if bibliography is not None else None
        self._bib_layout = bibliography.default_layout() if bibliography is not None else None
        self._cite_sort = citation.sort if citation is not None else None
        self._cite_layout = citation.default_layout() if citation is not None else None
        self._renders_citation_number = (
            has_citation_number or "citation-number" in _citation_block(style_text)
        )
        self._numbers: dict[str, int] | None = None
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
        # 数字制样式（29 份里 19 份）没有任何消歧设置：reserve() 的逐条探针渲染
        # 只为消歧服务，样式不用就可以整段跳过。
        self._needs_disambiguation = bool(
            self._add_givenname or self._add_names or self._year_suffix
            or "disambiguate" in style_text
        )
        self._cloner = StyleCloner(style_text, int(options.get("et-al-use-first", "1") or 1))
        citation_block = _citation_block(style_text)
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
        keys = list(keys)
        self._assign_numbers(keys)
        if not self._needs_disambiguation:
            return
        cited = [key for key in dict.fromkeys(keys) if key in self._known]
        if not cited:
            return

        self._disambiguate_keys = set()
        if self._add_givenname:
            if self._rule_names:
                for key, variant in name_variants(cited, self._by_key, initials_only=self._initials_only).items():
                    self._variants[key] = variant
            else:
                for group in groups({k: segments_text(self._render_single(k, self._variant(k))) for k in cited}):
                    for key, variant in resolve_given_variants(group, self._by_key, initials_only=self._initials_only).items():
                        self._variants[key] = variant

        if self._add_names:
            for group in groups({k: segments_text(self._render_single(k, self._variant(k))) for k in cited}):
                best = 0
                for extra in range(1, max_extra_names([self._by_key[k] for k in group]) + 1):
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

        remaining = groups({k: segments_text(self._render_single(k, self._variant(k))) for k in cited})
        if remaining:
            self._disambiguate_keys = {k for group in remaining for k in group}
            self._variant_cache.clear()

        if self._year_suffix:
            final = {key: segments_text(self._render_single(key, self._variant(key))) for key in cited}
            for group in groups(final):
                group = self._sorted_keys(group)
                for index, key in enumerate(group):
                    self._by_key[key]["year-suffix"] = _suffix_label(index)
            # 条目数据变了，重建引用源：CiteProcJSON 的条目在构造时已抓走
            self._source = CiteProcJSON(self.entries)
            if self._numbers is not None:
                self._source._numbers = self._numbers
            self._name_sources.clear()
            self._bibliography = CitationStylesBibliography(
                self._style, self._source, formatter.segments
            )
            self._variant_cache.clear()

    def _assign_numbers(self, keys: list[str]) -> None:
        """数字制样式按文献表顺序编号。

        CSL 的 `citation-number` 跟着文献表走。文献表按作者排的样式（如 ACM）里，
        第三条被引的文献可以印成 `[1]`，文内引用与文献表必须一致。引擎默认按首次
        引用顺序编号，所以这里在第一次渲染之前先排一遍，把结果挂到共享文献源上。
        文献表没声明 `<sort>`、或样式不印编号时不用动。
        """
        if not self._renders_citation_number or self._bib_sort is None:
            return
        items = [CitationItem(key) for key in dict.fromkeys(keys) if key in self._known]
        if not items:
            return
        # 排序键可能是 `citation-number`，先给一组按引用顺序的临时编号让它能求值
        scratch = CitationStylesBibliography(self._style, self._source, formatter.segments)
        scratch.register(Citation(items))
        ordered = self._bib_sort.sort(items, self._bib_layout)
        self._numbers = {
            item.key: number for number, item in enumerate(ordered, start=1)
        }
        self._source._numbers = self._numbers

    def _variant(self, key: str) -> Variant:
        return self._variants.get(key, BASE)

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
        """按样式声明的 `<sort>` 排；没声明就保持输入顺序（CSL 的规矩）。

        `_render_group` 是逐条渲染的，引擎的 `render_citation` 那套排序用不上，
        所以把这一组的条目交给引擎的 `Sort` 排一次，再按条目对象换回原来的参数元组。
        """
        if self._cite_sort is None:
            return list(pairs)
        items = [self._citation_item(pair) for pair in pairs]
        citation = Citation(items)
        citation.bibliography = self._bibliography   # 只供 item.reference 用，不登记
        ordered = self._cite_sort.sort(items, self._cite_layout)
        by_item = {id(item): pair for item, pair in zip(items, pairs)}
        return [by_item[id(item)] for item in ordered]

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
        style = self._style
        if variant.extra_names:
            style = self._cloned_style(variant.extra_names)
        bibliography = CitationStylesBibliography(
            style, self._source_for(key, variant), formatter.segments
        )
        citation = Citation([self._citation_item((key, locator, prefix, label))])
        bibliography.register(citation)
        with self._disambiguation_context():
            rendered = to_segments(bibliography.cite(citation, lambda item: item))
        return _with_year_suffix_segments(rendered, self._by_key.get(key, {}))

    def _source_for(self, key: str, variant: Variant):
        """这条引用用的条目源；补首字母/展开全名的条目副本各建一次。"""
        if not (variant.initials or variant.full_names):
            return self._source
        cache_key = (key, self._initials_all, variant.full_names)
        source = self._name_sources.get(cache_key)
        if source is None:
            entries = with_names(
                self.entries, key, initials_all=self._initials_all, full=variant.full_names,
            )
            source = self._name_sources[cache_key] = CiteProcJSON(entries)
        return source

    def _cloned_style(self, extra_names: int):
        """`et-al-use-first` 改过的样式副本；同一形态只解析一次。"""
        style = self._cloned_styles.get(extra_names)
        if style is None:
            style = CitationStylesStyle(
                str(self._cloner.path(Variant(extra_names=extra_names))),
                locale=self._style_locale,
            )
            self._cloned_styles[extra_names] = style
        return style

    @contextmanager
    def _disambiguation_context(self):
        token = _DISAMBIGUATE_KEYS.set(frozenset(self._disambiguate_keys))
        try:
            yield
        finally:
            _DISAMBIGUATE_KEYS.reset(token)

    def _citation_item(self, pair) -> CitationItem:
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
        return CitationItem(pair[0], **args)

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
        items = [self._citation_item(pair) for pair in pairs]
        citation = Citation(items)
        # 先登记：文献表的成员与数字制编号都靠这一步，跟怎么渲染文内引用无关
        self._bibliography.register(citation)
        with self._disambiguation_context():
            if self._collapse and len(pairs) > 1:
                segments = self._render_group(pairs)
            elif any(not self._variant(pair[0]).plain for pair in pairs):
                segments = self._render_group(pairs)
            else:
                segments = to_segments(
                    self._bibliography.cite(citation, lambda item: item))
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
        """用样式声明的 `<sort>` 排一组 key（年份后缀分配要用同一套次序）。"""
        if self._bib_sort is None:
            return list(keys)
        items = []
        by_item = {}
        for key in keys:
            item = CitationItem(key)
            items.append(item)
            by_item[id(item)] = key
        citation = Citation(items)
        citation.bibliography = self._bibliography
        return [by_item[id(item)] for item in self._bib_sort.sort(items, self._bib_layout)]

    def _ordered_items(self) -> list[tuple[str, CitationItem]]:
        """(原始 key, 条目)：先按样式 `<sort>`，再按 GB/T 的文种分组。"""
        items = list(self._bibliography.items)
        # CitationItem.key 是小写化的；原始拼写只在上面的 `_order` 里，用身份对齐。
        by_item = {id(item): key for item, key in zip(items, self._order)}
        if self._bib_sort is not None:
            items = self._bib_sort.sort(items, self._bib_layout)
        if self._gbt_language_groups:
            # GB/T 7714-2015 §9.2：著者-年制先按文种集中，再按作者/年份。
            # 稳定排序保留组内已有的 `<sort>` 次序。
            items.sort(
                key=lambda item: _language_group(
                    self._by_key.get(by_item[id(item)], {}))
            )
        return [(by_item[id(item)], item) for item in items]

    def bibliography_segments(self) -> list[tuple[str, list[tuple[str, dict]]]]:
        """(key, 片段序列)——写出器要用 key 建书签、用片段还原斜体。"""
        ordered = self._ordered_items()
        rendered = self._style.render_bibliography([item for _key, item in ordered])
        if len(rendered) != len(ordered):
            return [(f"item{i}", segs) for i, segs in enumerate(rendered)]
        return [
            (
                key,
                _merge_period_segments(
                    _with_year_suffix_segments(
                        self._separate_first_field(entry, item.number),
                        self._by_key.get(key, {}),
                    )
                ),
            )
            for (key, item), entry in zip(ordered, rendered)
        ]

    def bibliography(self) -> list[str]:
        """文末文献列表（纯文本；要片段用 bibliography_segments）。

        顺序分两种：`<bibliography>` 里声明了 `<sort>` 的按声明的键序与方向排（宏由引擎
        求值，`names-min`、`sort="descending"` 都在其中）；没声明的（数字顺序制，如
        GB/T 7714、Nature）按首次引用顺序。GB/T 7714 著者-年制再按文种分组。
        """
        return [segments_text(segs) for _key, segs in self.bibliography_segments()]

    def _separate_first_field(self, entry, number: int) -> list[tuple[str, dict]]:
        return separate_first_field(
            entry, number,
            number_prefix=self._number_prefix,
            number_suffix=self._number_suffix,
            first_field_column=self._first_field_column,
        )


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



def _citation_block(style_text: str) -> str:
    start = style_text.find("<citation")
    end = style_text.find("</citation>")
    return style_text[start : end + len("</citation>")] if start >= 0 and end >= 0 else ""
