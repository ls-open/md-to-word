"""CSL 的消歧阶段：citeproc-py 不实现，这里按规范补上。

CSL 规定了四种消歧手段，按顺序尝试（specification §"Disambiguation"）：

1. `disambiguate-add-givenname` —— 名字加到能区分（给首名补首字母）；
2. `disambiguate-add-names` —— 把 et al. 藏起来的名字一个个放出来；
3. `disambiguate` 条件 —— 样式里用 `<choose>` 写的专门分支（极少见，不支持）；
4. `disambiguate-add-year-suffix` —— 前三条都分不开时，同年加 a/b/c。

citeproc-py 一个都没做。它只能按一份样式渲染整条引用，没有「这个词条换个名字形态」的
入口，所以做法是**克隆样式**：把 `<citation>` 里的名字参数（`et-al-use-first`、`form`）
改成需要的形态，用副本重新渲染——CSL 处理器内部也是这么干的，不是改渲染结果。

条目数据层能做的只有第 4 条（`year-suffix` 是它认识的变量），前两条必须落在样式上。
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

    @property
    def plain(self) -> bool:
        return not self.extra_names and not self.initials


BASE = Variant()


def citation_attrs(style_text: str) -> dict[str, str]:
    """`<citation>` 元素上的属性（消歧选项、et-al 默认值都写在这里）。"""
    m = re.search(r"<citation\b([^>]*)>", style_text)
    if not m:
        return {}
    return dict(re.findall(r'([\w-]+)="([^"]*)"', m.group(1)))


def initialize_with(style_text: str) -> str:
    """样式里的 `initialize-with`（APA 系都是 ". "）。消歧补首字母时照它写。"""
    m = re.search(r'initialize-with="([^"]*)"', style_text)
    return m.group(1) if m else ". "


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


class StyleCloner:
    """按需生成样式副本，相同形态只写一次文件。"""

    def __init__(self, style_text: str, base_use_first: int) -> None:
        self._text = style_text
        self._base = base_use_first
        self._dir = tempfile.TemporaryDirectory(prefix="md-to-word-csl-")
        self._paths: dict[Variant, Path] = {}

    def path(self, variant: Variant) -> Path:
        if variant not in self._paths:
            target = Path(self._dir.name) / f"csl-{variant.extra_names}-{int(variant.initials)}.csl"
            target.write_text(clone(self._text, self._base, variant), encoding="utf-8")
            self._paths[variant] = target
        return self._paths[variant]

    def close(self) -> None:
        self._dir.cleanup()
