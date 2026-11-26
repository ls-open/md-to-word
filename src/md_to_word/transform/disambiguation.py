"""CSL 的消歧阶段：citeproc-py 不实现，这里按规范补上。

CSL 规定了四种消歧手段，按顺序尝试（specification §"Disambiguation"）：

1. `disambiguate-add-givenname` —— 名字加到能区分（给首名补首字母）；
2. `disambiguate-add-names` —— 把 et al. 藏起来的名字一个个放出来；
3. `disambiguate` 条件 —— 样式里用 `<choose>` 写的专门分支；由 `citations.py` 的
   `_if_render` 按本次引用组求值，不是恒真；
4. `disambiguate-add-year-suffix` —— 前三条都分不开时，同年加 a/b/c。

citeproc-py 一个都没做。它只能按一份样式渲染整条引用，没有「这个词条换个名字形态」的
入口，所以做法是**克隆样式**：把 `<citation>` 里的名字参数（`et-al-use-first`、`form`）
改成需要的形态，用副本重新渲染——CSL 处理器内部也是这么干的，不是改渲染结果。

第 1、4 条同时用到**条目数据**：`CitationEngine._with_names()` 给首名补首字母或展开全名，
`year-suffix` 直接写进条目副本；第 2 条靠样式副本的 `et-al-use-first`。`StyleCloner`
当前只改 `et-al-use-first`，文档里说的 `form` 改写并未实现——改这段前先看 `clone()`。
"""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Variant:
    """一条引用的名字形态。`extra_names=0` + `initials=False` 就是样式本来的样子。"""

    extra_names: int = 0
    initials: bool = False
    full_names: bool = False   # 首字母也分不开时展开全名（primary-name 规则的最后一步）

    @property
    def plain(self) -> bool:
        return not self.extra_names and not self.initials and not self.full_names


BASE = Variant()


def citation_attrs(style_text: str) -> dict[str, str]:
    """`<citation>` 元素上的属性（消歧选项、et-al 默认值都写在这里）。"""
    m = re.search(r"<citation\b([^>]*)>", style_text)
    if not m:
        return {}
    return dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))


def clone(style_text: str, base_use_first: int, variant: Variant) -> str:
    """返回把名字参数改成 `variant` 的样式副本文本。"""
    start = style_text.find("<citation")
    end = style_text.find("</citation>")
    if start < 0 or end < 0:
        return style_text
    block = style_text[start : end + len("</citation>")]

    if variant.extra_names:
        shown = base_use_first + variant.extra_names
        block = _set_attr(block, "et-al-use-first", str(shown), tag="citation")
        block = re.sub(
            r'(<name\b[^>]*\bet-al-use-first=")(\d+)(")',
            lambda m: f"{m.group(1)}{int(m.group(2)) + variant.extra_names}{m.group(3)}",
            block,
        )

    return style_text[:start] + block + style_text[end + len("</citation>") :]


def _set_attr(block: str, name: str, value: str, tag: str) -> str:
    """给 `<tag …>` 开标签上的属性赋值，没有就补上。"""
    pattern = re.compile(rf"<{tag}\b([^>]*)>")

    def repl(m: re.Match) -> str:
        attrs = m.group(1)
        if re.search(rf'\b{name}="[^"]*"', attrs):
            attrs = re.sub(rf'\b{name}="[^"]*"', f'{name}="{value}"', attrs)
        else:
            attrs = f'{attrs} {name}="{value}"'
        return f"<{tag}{attrs}>"

    return pattern.sub(repl, block, count=1)


def initials(given: str, separator: str = ". ") -> str:
    """`Mary Jane` → `M. J. `（CSL 的 `initialize-with`）。"""
    parts = [word[0].upper() for word in re.split(r"[\s-]+", given.strip()) if word]
    return "".join(part + separator for part in parts)



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



def with_names(entries, key: str, *, initials_all: bool, full: bool = False) -> list:
    """这条引用的条目副本：按规则给首名（或全部名字）补首字母，或展开全名。"""
    decorated = []
    for entry in entries:
        if entry["id"] != key:
            decorated.append(entry)
            continue
        copy = dict(entry)
        role = "author" if entry.get("author") else ("editor" if entry.get("editor") else None)
        if role:
            people = [dict(person) for person in entry[role]]
            targets = people if initials_all else people[:1]
            for person in targets:
                given = person.get("given", "")
                family = person.get("family")
                if given and family:
                    person["family"] = (given + " " if full else initials(given)) + family
            copy[role] = people
        decorated.append(copy)
    return decorated


def resolve_given_variants(group: list[str], by_key: dict,
                           *, initials_only: bool) -> dict[str, Variant]:
    """同一同姓组（或同撞车引用组）里，按首字母子组决定补首字母还是展开全名。"""
    firsts = [((by_key[k].get("author") or by_key[k].get("editor") or [{}])[0]) for k in group]
    givens = {person.get("given", "") for person in firsts}
    if len(givens) < 2:
        return {}
    if initials_only:
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


def name_variants(cited: list[str], by_key: dict,
                  *, initials_only: bool) -> dict[str, Variant]:
    """第一作者同姓不同人的，补首字母；首字母也撞的，按子组展开全名。"""
    buckets: dict[str, list[str]] = {}
    for key in cited:
        people = by_key[key].get("author") or by_key[key].get("editor") or []
        if people:
            buckets.setdefault(people[0].get("family") or people[0].get("literal", ""), []).append(key)

    out: dict[str, Variant] = {}
    for group in buckets.values():
        out.update(resolve_given_variants(group, by_key, initials_only=initials_only))
    return out


def groups(texts: dict) -> list:
    """把渲染结果相同的条目归成一组；只返回撞车的那些组。"""
    buckets: dict = {}
    for key, text in texts.items():
        buckets.setdefault(text, []).append(key)
    return [group for group in buckets.values() if len(group) > 1]


def max_extra_names(entries: list) -> int:
    """补名字最多补到把作者全列出来为止。"""
    return max((len(entry.get("author") or entry.get("editor") or []) for entry in entries), default=1) - 1


class StyleCloner:
    """按需生成样式副本，相同形态只写一次文件。"""

    def __init__(self, style_text: str, base_use_first: int) -> None:
        self._text = style_text
        self._base = base_use_first
        self._dir = tempfile.TemporaryDirectory(prefix="md-to-word-csl-")
        self._paths: dict[Variant, Path] = {}

    def path(self, variant: Variant) -> Path:
        if variant not in self._paths:
            target = Path(self._dir.name) / f"csl-{variant.extra_names}.csl"
            target.write_text(clone(self._text, self._base, variant), encoding="utf-8")
            self._paths[variant] = target
        return self._paths[variant]

    def close(self) -> None:
        self._dir.cleanup()
