"""`collapse="year-suffix-ranged"`：同作者同年后缀连续的多条并成 `2020a–c`。

`citeproc-py` 不实现 collapse，这一段由 citations.py 补；`collapse="year"` 的样式只并
年份、后缀仍逐条写，不能跟着折，数字制也不受影响。
"""

from __future__ import annotations

from pathlib import Path

from md_to_word.config import get_csl_dir
from md_to_word.transform.citations import CitationEngine

CSL_DIR = get_csl_dir()
SPRINGER = CSL_DIR / "springer-basic-author-date.csl"


def _bib(count: int) -> str:
    return "\n".join(
        f"@article{{g{i}, author={{Green, George}}, title={{T{i}}}, journal={{J}}, year={{2020}}}}"
        for i in range(count)
    )


def _engine(count: int, style: Path) -> CitationEngine:
    engine = CitationEngine(_bib(count), style, lang="en")
    engine.reserve([f"g{i}" for i in range(count)])
    return engine


def _text(engine: CitationEngine, keys: list[str]) -> str:
    return "".join(segment[0] for segment in engine.cite([(key, "", "", "page") for key in keys]))


def test_three_consecutive_suffixes_collapse_to_a_range() -> None:
    engine = _engine(3, SPRINGER)
    assert _text(engine, ["g0", "g1", "g2"]) == "(Green 2020a–c)"


def test_two_suffixes_are_not_collapsed() -> None:
    """参考实现（citeproc-js）两条不折，这里保持一致。"""
    engine = _engine(2, SPRINGER)
    assert _text(engine, ["g0", "g1"]) == "(Green 2020a, 2020b)"


def test_four_consecutive_suffixes_span_the_whole_run() -> None:
    engine = _engine(4, SPRINGER)
    assert _text(engine, ["g0", "g1", "g2", "g3"]) == "(Green 2020a–d)"


def test_a_gap_breaks_the_range() -> None:
    engine = _engine(4, SPRINGER)
    assert _text(engine, ["g0", "g1", "g3"]) == "(Green 2020a, 2020b, 2020d)"


def test_year_styles_keep_listing_suffixes() -> None:
    """`collapse="year"` 只并年份，后缀逐条写——不能跟着折成区间。"""
    engine = _engine(3, CSL_DIR / "elsevier-harvard.csl")
    assert _text(engine, ["g0", "g1", "g2"]) == "(Green, 2020a, 2020b, 2020c)"


def test_year_suffix_ranged_attribute_is_honored(tmp_path: Path) -> None:
    """内置样式没有 `year-suffix-ranged`，用改过属性的副本来覆盖这条分支。"""
    source = SPRINGER.read_text(encoding="utf-8")
    style = tmp_path / "ranged.csl"
    style.write_text(
        source.replace('collapse="year-suffix"', 'collapse="year-suffix-ranged"'),
        encoding="utf-8",
    )
    engine = _engine(3, style)
    assert _text(engine, ["g0", "g1", "g2"]) == "(Green 2020a–c)"


def test_numeric_styles_are_unchanged() -> None:
    engine = _engine(3, CSL_DIR / "chinese-gb7714-2015-numeric.csl")
    assert _text(engine, ["g0", "g1", "g2"]) == "[1–3]"
