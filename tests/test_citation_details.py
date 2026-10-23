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


def test_terminal_punctuation_does_not_take_a_second_period() -> None:
    """标题以 `?`／`!`／`.`／`:` 结尾时，样式补的那个句点不再追加。

    句点是 CSL 写在 `<group suffix=".">` 上的，citeproc-js 有一张合并表把它吃掉，
    citeproc-py 没有——`What Aspects Are Automated?` 于是成了 `Automated?.`。
    书名走斜体时句点落在 `</i>` 后面、Chicago 这类加引号的落在右引号后面，
    合并都要看得穿。
    """
    bib = """
@article{q, author={Smith, Jane}, title={What Aspects Are Automated?}, journal={J}, year={2021}}
@article{e, author={Doe, Jane}, title={Is it done!}, journal={J}, year={2020}}
@article{d, author={Roe, Jane}, title={A study.}, journal={J}, year={2019}}
@book{b, author={Poe, Jane}, title={What Now?}, publisher={MIT Press}, year={2018}}
"""
    engine = CitationEngine(bib, CSL / "apa.csl", lang="en")
    keys = ["q", "e", "d", "b"]
    engine.reserve(keys)
    for key in keys:
        engine.cite([(key, "")])
    texts = {
        key: "".join(text for text, _ in segments)
        for key, segments in engine.bibliography_entries()
    }
    assert texts["q"].startswith("Smith, J. (2021). What Aspects Are Automated? J")
    assert texts["e"].startswith("Doe, J. (2020). Is it done! J")
    assert texts["d"].startswith("Roe, J. (2019). A study. J")
    assert texts["b"].startswith("Poe, J. (2018). What Now? MIT Press")

    chicago = CitationEngine(bib, CSL / "chicago-author-date.csl", lang="en")
    chicago.reserve(keys)
    for key in keys:
        chicago.cite([(key, "")])
    quoted = dict(chicago.bibliography_entries())["q"]
    assert "“What Aspects Are Automated?” J" in "".join(text for text, _ in quoted)


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


def test_duplicate_keys_are_rendered_as_written() -> None:
    """CSL 不在一条引用里消重（官方用例 `collapse_NumericDuplicate` 就是这么期望的）：
    重复的 key 原样渲染，作者能一眼看出自己写重了，而不是被悄悄合并。"""
    engine = _apa()
    assert _text(engine, ("adams2019", ""), ("adams2019", "")) == "(Adams & Cole, 2019, 2019)"


def test_superscript_numeric_runs_collapse() -> None:
    """Nature/AMA 这类上标数字制没有方括号，连续编号同样要并成区间。"""
    bib = "\n".join(
        f"@article{{n{i}, author={{A{i}, X}}, title={{P{i}}}, journal={{J}}, year={{200{i}}}}}"
        for i in range(1, 4)
    )
    engine = CitationEngine(bib, CSL / "nature.csl", lang="en")
    text = "".join(segment[0] for segment in engine.cite([("n1", ""), ("n2", ""), ("n3", "")]))
    assert "–" in text and "1" in text and "3" in text, text
    assert "1,2,3" not in text


SAME_SURNAME_BIB = """
@article{liming, author={Li, Ming}, title={Gamma}, journal={J}, year={2021}}
@article{lichaoyang, author={Li, Chaoyang}, title={Delta}, journal={J}, year={2023}}
@article{gaoj, author={Gao, Juliet}, title={Alpha}, journal={J}, year={2024}}
@article{gaoq, author={Gao, Quebec}, title={Beta}, journal={J}, year={2024}}
@article{lichen, author={Li, Chen}, title={Epsilon}, journal={J}, year={2019}}
@article{lichaoyang2, author={Li, Chaoyang}, title={Zeta}, journal={J}, year={2018}}
"""
SAME_SURNAME_KEYS = ["liming", "lichaoyang", "gaoj", "gaoq", "lichen", "lichaoyang2"]


def _bibliography_titles(style: str) -> list[str]:
    """文献表的顺序，用题名（每条不重复）表示——各样式把年份、题名套在不同标点里。"""
    titles = ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta")
    engine = CitationEngine(SAME_SURNAME_BIB, CSL / f"{style}.csl", lang="en")
    engine.reserve(SAME_SURNAME_KEYS)
    for key in SAME_SURNAME_KEYS:
        engine.cite([(key, "")])
    entries = ["".join(text for text, _ in segments) for _key, segments in engine.bibliography_entries()]
    return [next(title for title in titles if title in entry) for entry in entries]


def test_same_surname_authors_sort_by_given_name() -> None:
    """同姓不同人按名排，不是按姓撞成一个键就掉到年份上。

    只比姓的话 `Li, C.` 与 `Li, M.` 完全同键，顺序由年份定：`Li, M. (2021)` 会排到
    `Li, C. (2023)` 前面。改后与 citeproc-js 对同一组条目的输出逐条对齐。
    """
    assert _bibliography_titles("apa") == ["Alpha", "Beta", "Zeta", "Epsilon", "Delta", "Gamma"]


def test_the_given_name_form_follows_the_style() -> None:
    """名的形态跟着样式走，不是我们自己挑一种。

    APA 在样式根上写了 `initialize-with`，名收成首字母：`Chaoyang` 与 `Chen` 都是 `C.`，
    分不开，于是落到年份——`Zeta (2018)`、`Epsilon (2019)`、`Delta (2023)`。
    Chicago 与 MLA 在 `<name>` 上写了 `initialize="false"`，比全名：`Chaoyang` 排在
    `Chen` 前面。MLA 的排序键里根本没有日期，同作者按**题名**排（`Delta` → `Zeta`），
    按年份排就错了。三档都以 citeproc-js 为准。
    """
    assert _bibliography_titles("chicago-author-date") == [
        "Alpha", "Beta", "Zeta", "Delta", "Epsilon", "Gamma",
    ]
    assert _bibliography_titles("modern-language-association") == [
        "Alpha", "Beta", "Delta", "Zeta", "Epsilon", "Gamma",
    ]


def test_a_descending_sort_key_is_honoured() -> None:
    """Elsevier Harvard 的 `<key variable="issued" sort="descending"/>`：同作者年份倒序。"""
    assert _bibliography_titles("elsevier-harvard") == [
        "Alpha", "Beta", "Delta", "Epsilon", "Zeta", "Gamma",
    ]


def test_translator_series_and_note_are_mapped() -> None:
    """`.bib` 里这些字段以前直接丢掉：译者在文献表里整段不见、丛书名与注释也消失。"""
    from md_to_word.transform.bibtex import parse_bibtex

    entry = parse_bibtex(
        "@book{b, author={A, B}, title={T}, series={LNCS}, translator={C, D}, "
        "note={注}, numpages={123}, year={2020}}"
    )[0]
    assert entry["collection-title"] == "LNCS"
    assert entry["translator"] == [{"family": "C", "given": "D"}]
    assert entry["note"] == "注"
    assert entry["number-of-pages"] == "123"
