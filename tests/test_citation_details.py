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


def test_numeric_entries_put_the_number_in_its_own_column() -> None:
    """`[1]` 与条目正文之间要有分隔，且是制表符：样式声明了 `second-field-align`。

    GB/T 7714 的 `<layout>` 里序号后面故意不写空格，上游靠这个属性让排版器把序号
    排成独立一栏。段落格式归要求文件管，所以这一栏由引擎按 CSL 自己的声明补。
    """
    engine = CitationEngine(BIB, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    engine.cite([("adams2019", "")])
    assert engine.bibliography()[0].startswith("[1]\tADAMS"), engine.bibliography()


def test_author_date_entries_get_no_tab() -> None:
    """作者-年份制没有序号列，不能凭空补一个制表符。"""
    engine = _apa()
    engine.cite([("adams2019", "")])
    assert "\t" not in engine.bibliography()[0], engine.bibliography()


def test_the_number_column_is_cut_at_the_style_declared_marker() -> None:
    """序号那一栏的边界只认 CSL 声明的前后缀，不认 citeproc 的分片。

    citeproc-py 的分片是按文本节点切的：IEEE 给出的是 `'[1]J. Doe and J. Roe, '`，
    序号和作者在同一个分片里。按分片切会把制表符插到作者后面（3.4.2 的回归）。
    """
    engine = CitationEngine(BIB, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    engine._first_field_column = True
    engine._number_prefix, engine._number_suffix = "[", "]"
    assert engine._separate_first_field(["[1]J. Doe and J. Roe, ", "“T”"], 1) == (
        "[1]\tJ. Doe and J. Roe, “T”")


def test_no_separator_when_the_number_is_not_where_the_style_says() -> None:
    engine = CitationEngine(BIB, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    engine._first_field_column = True
    engine._number_prefix, engine._number_suffix = "[", "]"
    assert engine._separate_first_field(["Doe, J. A study."], 3) == "Doe, J. A study."


def test_edited_book_does_not_repeat_editors_and_capitalizes_label() -> None:
    """编者书缺 author 时 editor 升到作者位，后续附注位不能再重复印一遍编者；

    同时 APA 要求的 `(Eds.)` / `(Ed.)`（`text-case="title"`）要按默认英文区域生效。
    """
    bib = """
@book{edbook, editor={Stensaker, Bjorn and Harvey, Lee}, year={2023},
  title={Accountability in higher education}, edition={2}, publisher={Routledge}}
@incollection{chap, author={Stake, R.}, editor={Guba, E.}, year={2000},
  title={Chapter title}, booktitle={Handbook}, pages={10-20}, publisher={Press}}
"""
    apa = CitationEngine(bib, CSL / "apa.csl", lang="en")
    apa.cite([("edbook", "")])
    apa.cite([("chap", "")])
    entries = {k: "".join(s[0] for s in segs) for k, segs in apa.bibliography_entries()}
    assert entries["edbook"] == (
        "Stensaker, B., & Harvey, L. (Eds.). (2023). Accountability in higher education (2nd ed.). Routledge."
    )
    assert "(Ed.)" in entries["chap"], entries["chap"]

    for style in ("harvard-cite-them-right.csl", "modern-language-association.csl", "american-medical-association.csl"):
        eng = CitationEngine(bib, CSL / style, lang="en")
        eng.cite([("edbook", "")])
        rendered = eng.bibliography()[0]
        assert rendered.count("Stensaker") == 1, f"{style}: {rendered}"


def test_english_narrative_citation_uses_and_not_ampersand() -> None:
    """英文作者-年份叙述式引用正文用 `and`，括号内仍用 `&`（APA §8.17），

    含 `&` 的单机构作者名不拆，中文稿也不乱插英文 `and`。
    """
    bib = """
@article{vd2021, author={Venkatesh, V. and Davis, F.}, title={TAM}, journal={MS}, year={2021}}
@book{pg2024, author={{Procter & Gamble}}, title={Annual Report}, publisher={P&G}, year={2024}}
"""
    apa_en = CitationEngine(bib, CSL / "apa.csl", lang="en")
    assert "".join(s[0] for s in apa_en.cite([("vd2021", "")], narrative=True)) == "Venkatesh and Davis (2021)"
    assert "".join(s[0] for s in apa_en.cite([("vd2021", "")], narrative=False)) == "(Venkatesh & Davis, 2021)"
    assert "".join(s[0] for s in apa_en.cite([("pg2024", "")], narrative=True)) == "Procter & Gamble (2024)"

    apa_zh = CitationEngine(bib, CSL / "apa.csl", lang="zh")
    assert "".join(s[0] for s in apa_zh.cite([("vd2021", "")], narrative=True)) == "Venkatesh & Davis (2021)"



_SYNTH_STYLE = """<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text"
       default-locale="en-US">
  <info><title>probe</title><id>probe</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout><text variable="title"/></layout></citation>
  <bibliography><layout>{body}</layout></bibliography>
</style>"""


def _synthetic(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "synth.csl"
    path.write_text(_SYNTH_STYLE.format(body=body), encoding="utf-8")
    return path


def test_number_range_is_plural_but_identifiers_are_not(tmp_path: Path) -> None:
    """`number = {3-5}` 是区间，标签要用复数；`TR-2023-04` / `3.5.0--rc1` 是编号，不是区间。

    上游 0.12 的 `\\d+[^\\d.]+\\d+` 把 `3.5.0--rc1` 也判成复数；我们旧的补丁反过来
    完全不认 `-`，于是真区间输出 `(number 3-5)`。
    """
    csl = _synthetic(tmp_path, '<label variable="number"/><text variable="number" prefix=" "/>')

    def render(number: str) -> str:
        bib = f"@techreport{{r, author = {{A, B}}, title = {{T}}, number = {{{number}}}, year = {{2020}}}}\n"
        engine = CitationEngine(bib, csl, lang="en")
        engine.reserve(["r"])
        engine.cite([("r", "")])
        return "".join(t for t, _ in dict(engine.bibliography_entries())["r"])

    assert render("3-5") == "numbers 3-5"
    assert render("TR-2023-04") == "number TR-2023-04"
    assert render("3.5.0--rc1") == "number 3.5.0--rc1"


def test_substituted_names_are_not_substituted_twice(tmp_path: Path) -> None:
    """同名 `<names>` 第二次出现时，若变量已被前一个 `<substitute>` 用掉，
    这里就该什么都不出——不能把本元素自己的 `<substitute>` 再渲染一遍
    （实测得到 `Ann Ed / Solo Title`，本该是 `Ann Ed /`）。"""
    csl = _synthetic(
        tmp_path,
        '<names variable="author"><substitute><names variable="editor"/></substitute></names>'
        '<text value=" / "/>'
        '<names variable="editor"><substitute><text variable="title"/></substitute></names>',
    )
    bib = "@book{edited, editor = {Smith, Ann}, title = {Solo Title}, year = {2020}}\n"
    engine = CitationEngine(bib, csl, lang="en")
    engine.reserve(["edited"])
    engine.cite([("edited", "")])
    rendered = "".join(t for t, _ in dict(engine.bibliography_entries())["edited"])
    assert rendered == "Ann Smith / ", rendered


def test_unsupported_citeproc_version_is_reported_not_silently_degraded(
    monkeypatch, caplog
) -> None:
    """装了范围外的 citeproc-py：九处 CSL 补丁会整体不生效，但不会报错。

    文献表照样能生成，只是悄悄退回上游的已知缺陷。既然结果是「看着正常、其实是旧的
    bug」，那就必须吵一句——所以这里锁两条：版本不对要说，同一个进程只说一次。
    """
    import importlib.metadata

    import md_to_word.transform.citations as citations

    monkeypatch.setattr(citations, "_citeproc_version_checked", False)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "0.11.1")

    with caplog.at_level("WARNING", logger="md_to_word.transform.citations"):
        _apa()
    assert "citeproc-py" in caplog.text and "0.11.1" in caplog.text

    caplog.clear()
    with caplog.at_level("WARNING", logger="md_to_word.transform.citations"):
        _apa()
    assert not caplog.text, "同一个进程不该反复念同一句"


def test_supported_citeproc_version_stays_quiet(monkeypatch, caplog) -> None:
    """范围内（0.12.x）不出声——否则这句提醒会因为太常见而被忽略。"""
    import importlib.metadata

    import md_to_word.transform.citations as citations

    monkeypatch.setattr(citations, "_citeproc_version_checked", False)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "0.12.2")

    with caplog.at_level("WARNING", logger="md_to_word.transform.citations"):
        _apa()
    assert not caplog.text
