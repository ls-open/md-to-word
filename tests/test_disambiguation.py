"""APA 一类作者-年份制的消歧：同作者同年的文献必须带 a/b/c。

`citeproc-py` 不实现 CSL 的消歧阶段（`disambiguate-add-year-suffix` 等选项它只读进默认值，
全库没有一处使用），所以三条不同的文献会被渲染成一模一样的 `(Kim & Park, 2020)`——
读者分不清谁是谁，作者自己更看不出来。这一层把年份后缀补上：写进条目数据的
`year-suffix`，文内引用与文献表两处都会带。

另外两条消歧（同姓补首字母、同首作者补合作者）还没做，见文末的已知边界。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from md_to_word.config import get_csl_dir
from md_to_word.transform.citations import CitationEngine

CSL_DIR = get_csl_dir()

BIB = """
@article{kim2020a, author={Kim, Jae and Park, Min}, title={Alpha}, journal={J}, year={2020}}
@article{kim2020b, author={Kim, Jae and Park, Min}, title={Beta}, journal={J}, year={2020}}
@article{kim2021, author={Kim, Jae and Park, Min}, title={Gamma}, journal={J}, year={2021}}
@article{lee2020, author={Lee, Ann and Park, Min}, title={Delta}, journal={J}, year={2020}}
@article{bai2024sun, author={Bai, Xue and Sun, Yao and Li, Meng}, title={Eps}, journal={J}, year={2024}}
@article{bai2024yu, author={Bai, Xue and Yu, Lan and Zhao, Qi}, title={Zeta}, journal={J}, year={2024}}
"""


def _text(engine: CitationEngine, keys: list[str]) -> str:
    return "".join(segment[0] for segment in engine.cite([(key, "") for key in keys]))


def _apa() -> CitationEngine:
    engine = CitationEngine(BIB, CSL_DIR / "apa.csl", lang="en")
    engine.reserve(["kim2020a", "kim2020b", "kim2021", "lee2020", "bai2024sun", "bai2024yu"])
    return engine


def test_same_authors_same_year_get_suffixes() -> None:
    engine = _apa()
    assert _text(engine, ["kim2020a"]) == "(Kim & Park, 2020a)"
    assert _text(engine, ["kim2020b"]) == "(Kim & Park, 2020b)"


def test_the_suffix_reaches_the_bibliography_too() -> None:
    """CSL 要求文内与文献表一致；只改一处比不改更糟。"""
    engine = _apa()
    _text(engine, ["kim2020a"])
    _text(engine, ["kim2020b"])
    _text(engine, ["kim2021"])
    entries = dict(engine.bibliography_segments())
    assert "(2020a)" in "".join(frag for frag, _ in entries["kim2020a"])
    assert "(2020b)" in "".join(frag for frag, _ in entries["kim2020b"])
    assert "(2021)" in "".join(frag for frag, _ in entries["kim2021"])


def test_a_lone_work_keeps_its_plain_year() -> None:
    engine = _apa()
    assert _text(engine, ["kim2021"]) == "(Kim & Park, 2021)"
    assert _text(engine, ["lee2020"]) == "(Lee & Park, 2020)"


def test_different_co_authors_are_not_suffixed() -> None:
    """同姓不同合作者要靠「补作者」区分，不是加年份后缀；加错了反而更乱。"""
    engine = _apa()
    assert _text(engine, ["bai2024sun"]) == "(Bai et al., 2024)"
    assert _text(engine, ["bai2024yu"]) == "(Bai et al., 2024)"


def test_a_combined_citation_lists_every_suffix() -> None:
    engine = _apa()
    assert _text(engine, ["kim2020a", "kim2020b"]) == "(Kim & Park, 2020a; Kim & Park, 2020b)"


def test_numeric_styles_are_untouched() -> None:
    """GB/T 7714 与 IEEE 是顺序编码制，条目没有年份后缀这回事。"""
    engine = CitationEngine(BIB, CSL_DIR / "chinese-gb7714-2015-numeric.csl")
    engine.reserve(["kim2020a", "kim2020b"])
    assert _text(engine, ["kim2020a"]) == "[1]"
    assert _text(engine, ["kim2020b"]) == "[2]"


def test_suffix_alphabet_rolls_over() -> None:
    from md_to_word.transform.citations import _suffix_label

    assert [_suffix_label(i) for i in (0, 1, 25, 26, 27)] == ["a", "b", "z", "aa", "ab"]


@pytest.mark.parametrize("csl", ["apa.csl", "chicago-author-date.csl"])
def test_styles_that_declare_the_option_opt_in(csl: str) -> None:
    engine = CitationEngine(BIB, CSL_DIR / csl, lang="en")
    assert engine._year_suffix, f"{csl} 声明了 disambiguate-add-year-suffix，应被识别"


def test_the_exported_docx_carries_the_suffix(tmp_path: Path) -> None:
    """走完整条流水线：预检 → 模型 → 写出，后缀要真的落在产物里。"""
    import re
    import zipfile

    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    (tmp_path / "refs.bib").write_text(
        "@article{a, author={Kim, Jae and Park, Min}, title={Alpha}, journal={J}, year={2020}}\n"
        "@article{b, author={Kim, Jae and Park, Min}, title={Beta}, journal={J}, year={2020}}\n",
        encoding="utf-8",
    )
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n"
        "# 一\n\n见 [@a] 与 [@b]。\n",
        encoding="utf-8",
    )
    out = tmp_path / "m.docx"
    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=out))
    assert result.returncode == 0, result.errors

    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    assert "2020a" in text and "2020b" in text, text
