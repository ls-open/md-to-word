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
from contextvars import ContextVar
from pathlib import Path
from typing import Iterable, Sequence

from citeproc import Citation, CitationItem, CitationStylesBibliography, CitationStylesStyle, formatter
import citeproc.model as _citeproc_model
from citeproc.source import Locator
from citeproc.source.json import CiteProcJSON

from md_to_word.transform.bibtex import parse_bibtex
from md_to_word.transform.disambiguation import (
    BASE, StyleCloner, Variant, citation_attrs, initials,
)
from md_to_word.i18n import t

_DISAMBIGUATE_KEYS: ContextVar[frozenset[str]] = ContextVar(
    "md2word_disambiguate_keys", default=frozenset()
)


def _install_citeproc_shims() -> None:
    """修补 citeproc-py 几处 CSL 1.0 规范遗漏：

    1. `<substitute>` 触发后，`Names.process` / `Text._variable` 等未跳过已写入 `layout.repressed`
       的变量，且嵌套在 `<choose>`/`<macro>` 内的 `<names>` 未继承父 `<names>` 的格式与抑制状态；
    2. `Group.process` / `Macro.render` 用静态 `calls_variable()` 扫描 `<choose>` 全部未命中分支，
       导致如 APA 学位论文无报告号却印出 `(Publication)`；按 CSL 1.0 规范改为运行期实际变量追踪，
       同时保持非空 `<macro>` 在外层 `<group>` 里视同已成功渲染的变量（如 Chicago software 的 `released`）；
    3. 独立 `<label variable="..."/>` 在变量缺失时未抑制，导致如 GB/T 7714-2025 无版本号却印出 `V.`；
    4. `<if disambiguate="true">` 在 citeproc-py 里是未实现的 TODO（恒为真），导致 MLA 每条文内引用都强行附带题名；
    5. `Label.markup` 未向 `TextCased.case` 传递条目语言，导致英文 `(Eds.)`/`(Ed.)` 退化为小写；
    6. `Label._is_plural` 把 `3.5.0--rc1` / `TR-2023-04` 里的 `-` 误判为复数范围，输出 `(Versions ...)`；
    7. `Name.initialize` 忽略 `<name initialize="false"/>`，导致 Chicago/MLA 文献表人名被错误缩写成首字母；
    8. `FormatNumber._format_last_page` 在 `minimal-two`/`minimal` 遇到 `1–40`/`11–112` 等不等位页码时截断错误（输出 `1–0`/`11–2`）；
    9. `to_ordinal` 遇到中文区域显式空 `<term name="ordinal"/>` 时误回退到 `en-US`（输出 `3rd 版`）。
    """
    if getattr(_citeproc_model.Names.process, "_md2word_shimmed", False):
        return

    group_frames: list[list[bool]] = []  # [var_called, var_rendered]
    sub_frames: list[tuple[object, dict[str, set[str]]]] = []  # (parent_names_elem, staging_repressed)

    orig_substitute_render = _citeproc_model.Substitute.render
    orig_macro_render = _citeproc_model.Macro.render
    orig_names_process = _citeproc_model.Names.process
    orig_name_initialize = _citeproc_model.Name.initialize
    orig_text_variable = _citeproc_model.Text._variable
    orig_date_process = _citeproc_model.Date.process
    orig_number_process = _citeproc_model.Number.process
    orig_label_process = _citeproc_model.Label.process
    orig_label_is_plural = _citeproc_model.Label._is_plural
    orig_if_render = _citeproc_model.If.render
    orig_format_last_page = _citeproc_model.FormatNumber._format_last_page

    def _is_repressed(elem, var: str | None, context) -> bool:
        if not var:
            return False
        ctx = context if context is not None else elem
        try:
            repressed = getattr(ctx.get_layout(), "repressed", {})
        except Exception:
            return False
        for item_var in repressed.get(elem.tag, ()):
            if item_var and var in item_var.split():
                return True
        return False

    def _substitute_render(self, item, context=None, **kwargs):
        ctx = context if context is not None else self
        try:
            parent_names = self.xpath_search("./parent::cs:names[1]")[0]
        except Exception:
            parent_names = None
        for child in self.getchildren():
            staging: dict[str, set[str]] = {}
            sub_group_frame = [False, False]
            sub_frames.append((parent_names, staging))
            group_frames.append(sub_group_frame)
            text = None
            try:
                if isinstance(child, _citeproc_model.Names) and child.name is None and parent_names is not None:
                    text = child.render(item, names_context=parent_names, context=ctx, **kwargs)
                else:
                    text = child.render(item, context=ctx, **kwargs)
            except _citeproc_model.VariableError:
                continue
            finally:
                sub_frames.pop()
                group_frames.pop()
            if text:
                if group_frames and sub_group_frame[1]:
                    group_frames[-1][0] = True
                    group_frames[-1][1] = True
                try:
                    layout = ctx.get_layout()
                except Exception:
                    return text
                for rtag, rvars in staging.items():
                    bucket = layout.repressed.setdefault(rtag, [])
                    for rvar in rvars:
                        if rvar not in bucket:
                            bucket.append(rvar)
                direct_var = child.get("variable")
                if direct_var:
                    bucket = layout.repressed.setdefault(child.tag, [])
                    for rvar in direct_var.split():
                        if rvar not in bucket:
                            bucket.append(rvar)
                return text
        if group_frames:
            group_frames[-1][0] = True
        return None

    def _names_process(self, item, names_context=None, context=None, **kwargs):
        ctx = context if context is not None else self
        if names_context is None and self.name is None and sub_frames:
            parent_names = sub_frames[-1][0]
            if parent_names is not None and parent_names is not self:
                names_context = parent_names

        try:
            layout = ctx.get_layout()
            repressed_list = getattr(layout, "repressed", {}).get(self.tag, [])
        except Exception:
            repressed_list = []
        repressed_vars: set[str] = set()
        for var in repressed_list:
            if var:
                repressed_vars.update(var.split())

        orig_var = self.get("variable") or ""
        roles = orig_var.split()
        filtered = [role for role in roles if role not in repressed_vars]
        if group_frames:
            group_frames[-1][0] = True
        present = [r for r in filtered if r in item.reference and item.reference[r]]

        def _invoke():
            return orig_names_process(
                self, item, names_context=names_context, context=context, **kwargs
            )

        if len(filtered) != len(roles):
            self.attrib["variable"] = " ".join(filtered)
            try:
                out = _invoke()
            finally:
                self.attrib["variable"] = orig_var
        else:
            out = _invoke()

        if out:
            if group_frames:
                group_frames[-1][1] = True
            if present and sub_frames:
                sub_frames[-1][1].setdefault(self.tag, set()).update(present)
        return out

    def _text_variable(self, item, context):
        var = self.get("variable")
        is_generated = var in self.generated_variables
        if group_frames and not is_generated:
            group_frames[-1][0] = True
        if _is_repressed(self, var, context):
            return None
        val = orig_text_variable(self, item, context)
        if val is not None and str(val) != "":
            if group_frames and not is_generated:
                group_frames[-1][1] = True
            if sub_frames and var and not is_generated:
                sub_frames[-1][1].setdefault(self.tag, set()).add(var)
        return val

    def _date_process(self, item, variable=None, show_parts=None, context=None, **kwargs):
        var = variable or self.get("variable")
        ctx = context if context is not None else self
        track_var = not self.is_locale_date()
        if track_var and group_frames:
            group_frames[-1][0] = True
        if _is_repressed(self, var, ctx):
            return None
        val = orig_date_process(
            self, item, variable=variable, show_parts=show_parts, context=context, **kwargs
        )
        if val is not None and str(val) != "" and track_var:
            if group_frames:
                group_frames[-1][1] = True
            if sub_frames and var:
                sub_frames[-1][1].setdefault(self.tag, set()).add(var)
        return val

    def _number_process(self, item, context=None, **kwargs):
        var = self.get("variable")
        ctx = context if context is not None else self
        if group_frames:
            group_frames[-1][0] = True
        if _is_repressed(self, var, ctx):
            return None
        val = orig_number_process(self, item, context=context, **kwargs)
        if val is not None and str(val) != "":
            if group_frames:
                group_frames[-1][1] = True
            if sub_frames and var:
                sub_frames[-1][1].setdefault(self.tag, set()).add(var)
        return val

    def _label_process(self, item, variable=None, plural=None, context=None, **kwargs):
        var = variable or self.get("variable")
        standalone = variable is None
        if var == "locator":
            if group_frames:
                group_frames[-1][0] = True
            if not getattr(item, "has_locator", False):
                return None
        elif var and standalone:
            # 独立 `<label variable="X"/>`（非 `<names>` 内部转发）：变量缺失或为空时不渲染（CSL 1.0）
            if group_frames:
                group_frames[-1][0] = True
            try:
                ref_val = item.reference[var.replace("-", "_")]
            except _citeproc_model.VariableError:
                return None
            if ref_val is None or str(ref_val).strip() == "":
                return None
        val = orig_label_process(self, item, variable=variable, plural=plural, context=context, **kwargs)
        if val is not None and str(val) != "" and (var == "locator" or (var and standalone)) and group_frames:
            group_frames[-1][1] = True
        return val

    def _macro_render(self, item, context=None, sort_options=None):
        frame = [False, False]
        group_frames.append(frame)
        failed = False
        try:
            out = orig_macro_render(self, item, context=context, sort_options=sort_options)
        except _citeproc_model.VariableError:
            failed = True
            out = None
        finally:
            group_frames.pop()
        if failed or (frame[0] and not frame[1]):
            if group_frames and frame[0]:
                group_frames[-1][0] = True
            return None
        if out and group_frames:
            # CSL 1.0：非空 macro 自身未因变量全空失败时，在外层 `<group>` 中视同非空变量输出
            group_frames[-1][0] = True
            group_frames[-1][1] = True
        return out

    def _group_process(self, item, context=None, **kwargs):
        frame = [False, False]
        group_frames.append(frame)
        try:
            output = []
            delimiter = self.get("delimiter", "")
            for child in self.iterchildren():
                try:
                    if isinstance(child, _citeproc_model.Choose):
                        child_text = child.render(item, context=context, delimiter=delimiter, **kwargs)
                    else:
                        child_text = child.render(item, context=context, **kwargs)
                    if child_text is not None:
                        output.append(child_text)
                except _citeproc_model.VariableError:
                    pass
            output = [part for part in output if part is not None]
            success = (not frame[0]) or frame[1]
            if output and success:
                return self.join(output)
            raise _citeproc_model.VariableError
        finally:
            group_frames.pop()
            if group_frames:
                group_frames[-1][0] = group_frames[-1][0] or frame[0]
                group_frames[-1][1] = group_frames[-1][1] or frame[1]

    def _if_render(self, item, context=None, delimiter="", **kwargs):
        if "disambiguate" not in self.attrib:
            return orig_if_render(self, item, context=context, delimiter=delimiter, **kwargs)
        disambig_want = str(self.get("disambiguate")).lower() == "true"
        cond_ok = (item.key in _DISAMBIGUATE_KEYS.get()) == disambig_want
        results: list[bool] = [cond_ok]
        if "type" in self.attrib:
            results += self._type(item)
        if "variable" in self.attrib:
            results += self._variable(item)
        if "is-numeric" in self.attrib:
            results += self._is_numeric(item)
        if "is-uncertain-date" in self.attrib:
            results += self._is_uncertain_date(item)
        if "locator" in self.attrib:
            results += self._locator(item)
        if "position" in self.attrib:
            results += self._position(item, context)
        match_mode = self.get("match")
        if match_mode == "any":
            result = any(results)
        elif match_mode == "none":
            result = not any(results)
        else:
            result = all(results)
        if not result:
            raise _citeproc_model.ConditionFailed
        return self.render_children(item, context=context, delimiter=delimiter, **kwargs)

    def _label_is_plural(self, item):
        var = self.get("variable")
        if var in ("version", "number", "collection-number"):
            try:
                value = item.reference[var.replace("-", "_")]
            except _citeproc_model.VariableError:
                return False
            return bool(re.search(r"(?:\d\s*(?:,|&|\band\b)\s*\d)", str(value)))
        return orig_label_is_plural(self, item)

    def _label_render(self, *args, **kwargs):
        text = self.process(*args, **kwargs)
        if not text:
            return None
        item = kwargs.get("item") if "item" in kwargs else (args[0] if args else None)
        lang = None
        if item is not None:
            try:
                lang = str(item.reference.language)[:2].lower()
            except Exception:
                lang = None
        if not lang:
            root = self.get_root()
            default_locale = root.get("default-locale", "en") if root is not None else "en"
            lang = str(default_locale)[:2].lower()
        return self.wrap(self.format(self.case(self.strip_periods(text), lang)))

    def _name_initialize(self, given, mark, context=None):
        init_opt = self.get("initialize")
        if init_opt is None:
            ctx = context if context is not None else self
            try:
                parent = ctx.xpath_search("./ancestor::*[self::cs:citation or self::cs:bibliography][1]")[0]
                init_opt = parent.get("initialize")
            except Exception:
                init_opt = None
            if init_opt is None:
                try:
                    init_opt = self.get_root().get("initialize")
                except Exception:
                    init_opt = None
        if init_opt is not None and str(init_opt).lower() == "false":
            return given
        return orig_name_initialize(self, given, mark, context)

    def _format_last_page(self, first, last):
        range_format = self.get_root().get_option("page-range-format")
        if not range_format or range_format == "expanded":
            return orig_format_last_page(self, first, last)
        if len(first) != len(last):
            return last
        if range_format in ("minimal", "minimal-two"):
            common = 0
            for idx, (fch, lch) in enumerate(zip(first, last)):
                if fch != lch:
                    common = idx
                    break
            else:
                return last
            if range_format == "minimal":
                index = common
            else:
                index = max(0, min(common, len(first) - 2))
            return last[index:]
        return orig_format_last_page(self, first, last)

    def _to_ordinal(number, context):
        lg_key = "{http://www.w3.org/XML/1998/namespace}lang"

        def _find(fallback_locale: bool):
            locales = context.get_root().locales
            if not fallback_locale and locales:
                main_lg = (locales[0].get(lg_key) or "").split("-")[0]
                if main_lg:
                    candidates = [
                        loc for loc in locales
                        if (loc.get(lg_key) or main_lg).split("-")[0] == main_lg
                    ]
                else:
                    candidates = list(locales[:1])
            else:
                candidates = list(locales)

            keys = [
                (f"ordinal-{number:02}" if len(str(number)) == 1 else f"ordinal-{number}", False),
                (f"ordinal-{int(str(number)[-1]):02}", True),
                ("ordinal", False),
            ]
            for term_name, zp in keys:
                for loc in candidates:
                    try:
                        t_el = loc.get_term(term_name, zero_padded=zp)
                    except IndexError:
                        continue
                    if t_el is not None:
                        return True, str(t_el.single)
            return False, ""

        found, suffix = _find(fallback_locale=False)
        if not found:
            _f2, suffix = _find(fallback_locale=True)
        return str(number) + suffix

    _substitute_render._md2word_shimmed = True
    _macro_render._md2word_shimmed = True
    _names_process._md2word_shimmed = True
    _name_initialize._md2word_shimmed = True
    _text_variable._md2word_shimmed = True
    _date_process._md2word_shimmed = True
    _number_process._md2word_shimmed = True
    _label_process._md2word_shimmed = True
    _group_process._md2word_shimmed = True
    _if_render._md2word_shimmed = True
    _label_is_plural._md2word_shimmed = True
    _label_render._md2word_shimmed = True
    _format_last_page._md2word_shimmed = True
    _to_ordinal._md2word_shimmed = True

    _citeproc_model.Substitute.render = _substitute_render
    _citeproc_model.Macro.render = _macro_render
    _citeproc_model.Names.process = _names_process
    _citeproc_model.Name.initialize = _name_initialize
    _citeproc_model.Text._variable = _text_variable
    _citeproc_model.Date.process = _date_process
    _citeproc_model.Number.process = _number_process
    _citeproc_model.Label.process = _label_process
    _citeproc_model.Group.process = _group_process
    _citeproc_model.If.render = _if_render
    _citeproc_model.Label._is_plural = _label_is_plural
    _citeproc_model.Label.render = _label_render
    _citeproc_model.FormatNumber._format_last_page = _format_last_page
    _citeproc_model.to_ordinal = _to_ordinal


_install_citeproc_shims()


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
        style_text = Path(csl_path).read_text(encoding="utf-8")
        self._number_prefix, self._number_suffix, has_citation_number = _number_affixes(style_text)
        tag = re.search(r"<bibliography\b[^>]*>", style_text)
        self._first_field_column = has_citation_number or bool(tag and 'second-field-align' in tag.group(0))
        self._sort_by_initials = _sort_names_initialized(style_text)
        self._sort_order = _declared_sort_keys(style_text)
        self._sorted = bool(self._sort_order)
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
                for group in _groups({k: self._render_single(k, self._variant(k)) for k in cited}):
                    for key, variant in self._resolve_given_variants(group).items():
                        self._variants[key] = variant

        if self._add_names:
            for group in _groups({k: self._render_single(k, self._variant(k)) for k in cited}):
                best = 0
                for extra in range(1, _max_extra_names([self._by_key[k] for k in group]) + 1):
                    shown = len({
                        self._render_single(
                            k,
                            Variant(
                                extra_names=extra,
                                initials=self._variant(k).initials,
                                full_names=self._variant(k).full_names,
                            ),
                        )
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

        remaining = _groups({k: self._render_single(k, self._variant(k)) for k in cited})
        if remaining:
            self._disambiguate_keys = {k for group in remaining for k in group}
            self._variant_cache.clear()

        if self._year_suffix:
            final = {key: self._render_single(key, self._variant(key)) for key in cited}
            for group in _groups(final):
                group = self._sorted_keys(group)
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
            names + _join_dates(dates, self._collapse_ranged) if names else dates[0]
            for names, dates in groups
        )
        return f"{prefix}{body}{suffix}"

    def _sort_pairs(self, pairs) -> list:
        """按样式声明的 `<sort>` 排；没声明就保持输入顺序（CSL 的规矩）。"""
        if not self._citation_sort:
            return list(pairs)
        kind = "year" if self._citation_sort in ("issued", "date") else "names"
        return sorted(
            pairs,
            key=lambda pair: _sort_value(kind, self._by_key.get(pair[0], {}), self._sort_by_initials),
        )

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
        token = _DISAMBIGUATE_KEYS.set(frozenset(self._disambiguate_keys))
        try:
            rendered = str(bibliography.cite(citation, lambda item: item))
        finally:
            _DISAMBIGUATE_KEYS.reset(token)
        return _with_year_suffix(rendered, self._by_key.get(key, {}))

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
                html = self._render_group(pairs)
            elif any(not self._variant(pair[0]).plain for pair in pairs):
                html = self._render_group(pairs)
            else:
                html = str(self._bibliography.cite(citation, lambda item: item))
        finally:
            _DISAMBIGUATE_KEYS.reset(token)
        if narrative:
            entry = self._by_key.get(pairs[0][0], {}) if len(pairs) == 1 else {}
            creators = entry.get("author") or entry.get("editor") or []
            and_word = "and" if self.lang == "en" and len(creators) >= 2 else None
            html = _as_narrative(html, and_word=and_word)
        html = _merge_duplicate_period(_collapse_numeric_runs(html, bare=self._numeric))
        segments = html_to_segments(html)
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
        return self._sorted_keys(self._order) if self._sorted else list(self._order)

    def bibliography_segments(self) -> list[tuple[str, list[tuple[str, dict]]]]:
        """(key, 片段序列)——写出器要用 key 建书签、用片段还原斜体。"""
        texts = self.bibliography()
        keys = self._ordered_keys()
        if len(keys) != len(texts):
            return [(f"item{i}", html_to_segments(t)) for i, t in enumerate(texts)]
        return list(zip(keys, [html_to_segments(t) for t in texts]))

    def bibliography(self) -> list[str]:
        """文末文献列表（仍是 html 标记串；要片段用 bibliography_segments）。

        顺序分两种：CSL 在 `<bibliography>` 里声明了 `<sort>` 的（作者-年份制）按声明的键序
        与方向排；没声明的（数字顺序制，如 GB/T 7714、Nature）按首次引用顺序。

        `citeproc-py` 有 `style.sort_bibliography()`，但实测不生效（apa.csl 依旧按注册顺序
        返回），所以这里自己做：键序、升降序、名的形态都取自样式本身，见
        `_declared_sort_keys` 与 `_sort_names_initialized`。
        """
        rendered = [
            _merge_duplicate_period(
                _with_year_suffix(self._separate_first_field(entry, number),
                                  self._by_key.get(key, {}))
            )
            for number, (key, entry)
            in enumerate(zip(self._order, self._bibliography.bibliography()), start=1)
        ]
        if not self._sorted or len(rendered) != len(self._order):
            return rendered

        text_by_key = dict(zip(self._order, rendered))
        return [text_by_key[key] for key in self._sorted_keys(self._order)]

    def _separate_first_field(self, entry, number: int) -> str:
        """顺序数字制或 `second-field-align` 声明了「首个字段自成一栏」：在序号后面补一个制表符。

        `citeproc-py` 从不落实这个属性，序号会直接贴住条目正文（例如 `[1]Smith`、`1.Smith`）。
        而它的分片**不是**按字段切的（IEEE 给出的是 `'[1]J. Doe and J. Roe, '`，序号和作者在
        同一个分片里），所以边界只能从 CSL 自己写的序号前后缀来：样式里那只 `citation-number`
        长什么样，产物里序号就长什么样。

        用制表符而非空格——`参考文献` 带悬挂缩进时，制表位正落在缩进处，首行文字与折行文字对齐成列。
        """
        text = "".join(str(chunk) for chunk in entry)
        marker = f"{self._number_prefix}{number}{self._number_suffix}"
        if not self._first_field_column or not text.startswith(marker):
            return text
        marker_clean = marker.rstrip()
        rest = text[len(marker):].lstrip()
        return marker_clean + "\t" + rest


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


_TERMINAL_PUNCT = ".!?:"
_CLOSING_QUOTES = "”’\"'"
# 半角句点跟在终止标点后面、且后面是空白或结尾——CSL 追加的 `suffix="."` 就是这种。
# 引号包住的也算：`“What?”` 后面同样不再补句点。
_SUFFIX_PERIOD_RE = re.compile(r"([.!?:][" + _CLOSING_QUOTES + r"]*)\.(?=\s|$)")


def _merge_duplicate_period(html: str) -> str:
    """终止标点后面不再补句点：`Automated?.` → `Automated?`、`“Automated?”.` → `“Automated?”`。

    citeproc-js 有一张合并表（`?` + `.` → `?`、`!` + `.` → `!`、`:` + `.` → `:`），
    用来吃掉样式在标题后补的那个 `suffix="."`；citeproc-py 没有，标题以问号结尾时
    文献表就写成 `Automated?.`。只看文本、跳过标签：APA 的书名是斜体，句点落在 `</i>` 后面。
    """
    parts: list[str] = []
    tail = ""
    pos = 0
    for match in _TAG_RE.finditer(html or ""):
        text, tail = _merge_text(html[pos : match.start()], tail)
        parts.append(text)
        parts.append(match.group(0))
        pos = match.end()
    text, tail = _merge_text((html or "")[pos:], tail)
    parts.append(text)
    return "".join(parts)


def _merge_text(text: str, tail: str) -> tuple[str, str]:
    """(合并后的文本, 这段最后几个非空白字符)——跨标签时上一段的结果要传过来。"""
    if not text:
        return text, tail
    while text.startswith(".") and _absorbs_period(tail):
        text = text[1:]
    text = _SUFFIX_PERIOD_RE.sub(r"\1", text)
    visible = text.rstrip()
    return text, ((tail + visible)[-4:] if visible else tail)


def _absorbs_period(tail: str) -> bool:
    """句点前面是不是「已经收过句号」的终止标点；右引号不算隔断（`“What?”.` 一样不补）。"""
    unquoted = tail.rstrip(_CLOSING_QUOTES)
    return bool(unquoted) and unquoted[-1] in _TERMINAL_PUNCT


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
    if and_word and " &amp; " in author:
        head, tail = author.rsplit(" &amp; ", 1)
        author = f"{head} {and_word} {tail}"
    return f"{author} ({match.group('rest')})"


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
