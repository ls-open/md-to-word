"""引文里的页码、前缀、同年后缀：作者写进去的东西必须原样出现在成品里。

这几项以前被静默丢掉——`[@a, p. 33]` 渲染成 `(Adams, 2019)`，`[见 @a]` 的「见」也没了。
丢了看不出来，属于最该拦的一类，所以逐条锁住。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from md_to_word.config import get_csl_dir
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.transform.citations import CitationEngine

CSL = get_csl_dir()
BIB = """
@article{adams2019, author={Adams, Bo and Cole, Di}, title={A study}, journal={J}, year={2019}}
@article{wang2020, author={Wang, Ming}, title={B}, journal={J}, year={2020}}
"""


def _apa() -> CitationEngine:
    return CitationEngine(BIB, CSL / "apa.csl", lang="en")


def _text(engine: CitationEngine, *pairs: tuple) -> str:
    return "".join(segment[0] for segment in engine.cite(list(pairs)))


def test_locator_survives() -> None:
    assert _text(_apa(), ("adams2019", "33")) == "(Adams & Cole, 2019, p. 33)"


def test_page_range_becomes_plural() -> None:
    assert _text(_apa(), ("adams2019", "33-35")) == "(Adams & Cole, 2019, pp. 33–35)"


def test_prefix_survives() -> None:
    assert _text(_apa(), ("adams2019", "", "see")) == "(see Adams & Cole, 2019)"


def test_numeric_styles_ignore_locators() -> None:
    engine = CitationEngine(BIB, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    assert _text(engine, ("wang2020", "33")) == "[1]"


def test_the_docx_keeps_the_page_number(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n# 一\n\n引用 [@adams2019, 33]。\n",
        encoding="utf-8",
    )
    out = tmp_path / "m.docx"
    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=out))
    assert result.returncode == 0, result.errors

    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    assert "p. 33" in text, text


def test_bare_page_number_is_a_locator(tmp_path: Path) -> None:
    """`[@a, 33]` 与 `[@a, p. 33]` 等价；不带 `p.` 的写法以前会静默丢掉。"""
    from md_to_word.model.reader import read_markdown

    for body, expect in (("见 [@a, 33]。", "33"), ("见 [@a, p. 33]。", "33"), ("见 [@a, pp. 33-35]。", "33-35")):
        model = read_markdown("# 一\n\n" + body + "\n", citation_keys={"a"})
        item = next(
            i for b in model.blocks for n in getattr(b, "inlines", [])
            if type(n).__name__ == "Citation" for i in n.items
        )
        assert item.locator == expect, body


def test_narrative_locator_is_attached() -> None:
    """手册里写的 `正如 @a [p. 33] 指出` 以前把 `[p. 33]` 留成正文。"""
    from md_to_word.model.reader import read_markdown

    model = read_markdown("# 一\n\n正如 @a [p. 33] 指出。\n", citation_keys={"a"})
    citation = next(
        n for b in model.blocks for n in getattr(b, "inlines", []) if type(n).__name__ == "Citation"
    )
    assert citation.items[0].locator == "33"


def test_year_only_citation_is_blocked(tmp_path: Path) -> None:
    """`[-@a]` 引擎不实现：静默渲染成完整引用等于改写了作者的话，所以拦下。"""
    from md_to_word.validator.check import validate_manuscript

    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\n---\n\n# 一\n\n见 [-@adams2019]。\n", encoding="utf-8"
    )
    report = validate_manuscript(tmp_path / "m.md")
    assert not report.valid
    assert any("[-@" in error for error in report.errors)


def test_group_authors_and_name_particles_survive() -> None:
    """`{{World Health Organization}}` 是团体作者，`Ludwig van Beethoven` 的 van 是姓氏前缀，
    `Smith, Jr., John` 的 Jr. 是后缀——三种以前都会被拆错，而且不报错。"""
    from md_to_word.transform.bibtex import parse_bibtex

    assert parse_bibtex("@book{a, author={{World Health Organization}}, title={R}}")[0]["author"] == [
        {"literal": "World Health Organization"}
    ]
    person = parse_bibtex("@book{b, author={Ludwig van Beethoven}, title={S}}")[0]["author"][0]
    assert person["family"] == "Beethoven" and person["non-dropping-particle"] == "van"
    person = parse_bibtex("@book{c, author={Smith, Jr., John}, title={T}}")[0]["author"][0]
    assert person["suffix"] == "Jr." and person["given"] == "John"


def test_month_and_thesis_genre_reach_the_output() -> None:
    from md_to_word.transform.bibtex import parse_bibtex

    entry = parse_bibtex("@article{a, author={Month, Only}, title={M}, year={2020}, month={mar}}")[0]
    assert entry["issued"]["date-parts"][0] == [2020, 3]
    thesis = parse_bibtex("@phdthesis{b, author={Doe, Jane}, title={T}, school={MIT}, year={2018}}")[0]
    assert thesis["genre"] == "Doctoral dissertation"


def test_locator_labels_are_kept() -> None:
    """`para.` 以前被当成页码前缀剥成 `ara.`；标签要换成 CSL 的变量名传下去。"""
    from md_to_word.model.reader import read_markdown

    model = read_markdown("# H\n\n见 [@a, para. 4]。\n", citation_keys={"a"})
    item = next(
        i for b in model.blocks for n in getattr(b, "inlines", [])
        if type(n).__name__ == "Citation" for i in n.items
    )
    assert (item.label, item.locator) == ("paragraph", "4")


def test_duplicate_keys_collapse() -> None:
    engine = _apa()
    assert _text(engine, ("adams2019", ""), ("adams2019", "")) == "(Adams & Cole, 2019)"
