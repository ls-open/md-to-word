"""引文渲染的复用：条目只解析一次，重复渲染不会互相污染。

`CiteProcJSON` 会把每条字符串拆成结构化 run。原先每渲染一条引用就重建整个文献源，
120 条文献的一次 `reserve()` 要花 3.5 秒，其中 2 秒在重复解析同一条目。这里盯住
「解析次数不随引用次数增长」，以及共享文献源之后输出仍然稳定。
"""

from __future__ import annotations

import pytest

from md_to_word.config import get_csl_dir
from md_to_word.transform import citations
from md_to_word.transform.citations import CitationEngine

CSL_DIR = get_csl_dir()

BIB = """
@article{one, author={Kim, Jae and Park, Min}, title={Alpha}, journal={J}, year={2020}}
@article{two, author={Lee, Ann}, title={Beta}, journal={J}, year={2021}}
@article{three, author={Bai, Xue and Sun, Yao}, title={Gamma}, journal={J}, year={2022}}
"""


def _count_sources(monkeypatch) -> list[int]:
    """记录 `CiteProcJSON` 被构造了几次。"""
    calls: list[int] = []
    real = citations.CiteProcJSON

    def counting(entries):
        calls.append(1)
        return real(entries)

    monkeypatch.setattr(citations, "CiteProcJSON", counting)
    return calls


def test_entries_are_parsed_once_for_a_numeric_style(monkeypatch) -> None:
    """数字制样式没有消歧设置，`reserve()` 整段跳过，条目源只该建一次。"""
    calls = _count_sources(monkeypatch)
    engine = CitationEngine(BIB, CSL_DIR / "nature.csl")
    engine.reserve(["one", "two", "three"])
    for _ in range(5):
        for key in ("one", "two", "three"):
            engine.cite([(key, "")])
    engine.bibliography()
    assert len(calls) == 1


def test_disambiguation_does_not_reparse_per_citation(monkeypatch) -> None:
    """APA 要补名字/年份后缀，条目源仍按需要建，而不是每渲染一条重建全库。"""
    calls = _count_sources(monkeypatch)
    engine = CitationEngine(BIB, CSL_DIR / "apa.csl", lang="en")
    engine.reserve(["one", "two", "three"])
    for key in ("one", "two", "three"):
        engine.cite([(key, "")])
    engine.bibliography()
    assert len(calls) <= 1 + len(engine.entries)


def test_repeated_renders_leave_the_source_untouched() -> None:
    """共享文献源的前提是渲染只读；读两遍必须一模一样。"""
    engine = CitationEngine(BIB, CSL_DIR / "nature.csl")
    for key in ("one", "two", "three"):
        engine.cite([(key, "")])
    first = engine.bibliography()
    for key in ("one", "two", "three"):
        engine.cite([(key, "")])
    assert engine.bibliography() == first


@pytest.mark.parametrize("style", ["apa.csl", "chicago-author-date.csl"])
def test_year_suffix_rebuild_still_reaches_every_entry(style: str) -> None:
    """年份后缀要写进条目数据；重建文献源后，缓存过的条目副本也必须失效。"""
    bib = """
@article{a, author={Kim, Jae}, title={Alpha}, journal={J}, year={2020}}
@article{b, author={Kim, Jae}, title={Beta}, journal={J}, year={2020}}
"""
    engine = CitationEngine(bib, CSL_DIR / style, lang="en")
    engine.reserve(["a", "b"])
    assert "2020a" in "".join(fragment for fragment, _ in engine.cite([("a", "")]))
    assert "2020b" in "".join(fragment for fragment, _ in engine.cite([("b", "")]))
