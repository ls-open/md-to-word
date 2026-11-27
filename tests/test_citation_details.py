"""引文里的页码、前缀、同年后缀：作者写进去的东西必须原样出现在成品里。

这几项以前被静默丢掉——`[@a, p. 33]` 渲染成 `(Adams, 2019)`，`[见 @a]` 的「见」也没了。
丢了看不出来，属于最该拦的一类，所以逐条锁住。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

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


def test_year_only_reaches_the_docx(tmp_path: Path) -> None:
    """写出器要带上 suppress 标记：成品里是 `(2019)`，不是完整引用。"""
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n# 一\n\n见 [-@adams2019]。\n",
        encoding="utf-8",
    )
    out = tmp_path / "m.docx"
    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=out))
    assert result.returncode == 0, result.errors

    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    assert "见(2019)" in text, text
    assert "(Adams & Cole, 2019)" not in text, text


def test_year_only_marker_is_parsed_before_the_key() -> None:
    """`-` 不是前缀：`[see -@a]` 的前缀是 `see`，作者抑制标记单独带走。"""
    from md_to_word.model.reader import read_markdown

    for body, prefix in (("见 [-@a]。", ""), ("见 [see -@a]。", "see")):
        model = read_markdown("# 一\n\n" + body + "\n", citation_keys={"a"})
        item = next(
            i for b in model.blocks for n in getattr(b, "inlines", [])
            if type(n).__name__ == "Citation" for i in n.items
        )
        assert item.suppress_author and item.prefix == prefix, body


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


def test_year_only_citation_drops_the_author() -> None:
    """`[-@a]` 是 Pandoc 的「只出年份」：APA 下是 `(2019)`，页码与混合组照常工作。"""
    engine = _apa()
    engine.reserve(["adams2019", "wang2020"])
    assert _text(engine, ("adams2019", "", "", "page", True)) == "(2019)"
    assert _text(engine, ("adams2019", "33", "", "page", True)) == "(2019, p. 33)"
    assert _text(
        engine,
        ("adams2019", "", "", "page", False),
        ("wang2020", "", "", "page", True),
    ) == "(Adams & Cole, 2019; 2020)"
    # 前缀保留，减号不吃进正文
    assert _text(engine, ("adams2019", "", "see", "page", True)) == "(see 2019)"


def test_year_only_citation_is_a_no_op_for_numeric_styles() -> None:
    """数字制本来就不印作者：`[-@a]` 与 `[@a]` 相同，编号不能被打乱。"""
    engine = CitationEngine(BIB, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    engine.reserve(["adams2019", "wang2020"])
    assert _text(engine, ("wang2020", "", "", "page")) == "[1]"
    assert _text(engine, ("adams2019", "", "", "page", True)) == "[2]"


def test_year_only_citation_passes_preflight(tmp_path: Path) -> None:
    from md_to_word.validator.check import validate_manuscript

    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\n---\n\n# 一\n\n见 [-@adams2019] 与 [see -@wang2020]。\n",
        encoding="utf-8",
    )
    report = validate_manuscript(tmp_path / "m.md")
    assert report.valid, report.errors


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


def test_double_period_at_a_seam_is_collapsed() -> None:
    """标题宏与字段后缀各自带 `. `：`Things. . London` 要并成一个句点。

    ISO 690 的标题宏写完 `. `，外层又给同字段补 `. `；citeproc 在拼接处吃掉重复标点，
    以前只在两个标点紧邻时判断，隔着空格就漏了。
    """
    bib = (
        "@book{b, author={Smith, John}, title={A Book About Things}, "
        "publisher={Acme Press}, address={London}, year={2020}}"
    )
    engine = CitationEngine(bib, CSL / "iso690-numeric-en.csl", lang="en")
    engine.cite([("b", "")])
    text = engine.bibliography()[0]
    assert ". ." not in text, text
    assert "Things. London" in text, text


def test_a_period_after_a_semicolon_is_suppressed() -> None:
    """字段以 `;` 收尾、布局再补 `.`：`2020;.` 应为 `2020;`。"""
    bib = (
        "@book{b, author={Smith, John}, title={A Book About Things}, "
        "publisher={Acme Press}, address={London}, year={2020}}"
    )
    engine = CitationEngine(
        bib, CSL / "multidisciplinary-digital-publishing-institute.csl", lang="en")
    engine.cite([("b", "")])
    text = engine.bibliography()[0]
    assert "2020;." not in text, text
    assert "2020;" in text, text


ARTICLE_BIB = """
@article{art, author={Doe, Jane and Roe, Richard}, title={An Article},
  journal={Journal of Stuff}, volume={3}, number={2}, pages={10--20}, year={2021}}
"""


def test_punctuation_moves_inside_quotes_for_en_us() -> None:
    """en-US 的 locale 声明 `punctuation-in-quote="true"`：`“An Article”.` → `“An Article.”`。

    Chicago 与 MLA 的逗号/句点来自 group 分隔符，不一定挂在 affix 上；所以判断在最终
    run 上做，格式边界不打断。
    """
    for style in ("chicago-author-date", "modern-language-association"):
        engine = CitationEngine(ARTICLE_BIB, CSL / f"{style}.csl", lang="en")
        engine.cite([("art", "")])
        text = engine.bibliography()[0]
        assert "“An Article.”" in text, (style, text)
        assert "“An Article”." not in text, (style, text)


def test_a_style_can_turn_punctuation_in_quote_off() -> None:
    """样式自己的 locale 选项优先：Emerald Harvard 声明 false，逗号留在引号外。"""
    engine = CitationEngine(ARTICLE_BIB, CSL / "emerald-harvard.csl", lang="en")
    engine.cite([("art", "")])
    text = engine.bibliography()[0]
    assert "“An Article”," in text, text


def test_sort_keys_named_by_a_macro_are_evaluated() -> None:
    """排序键指向的宏叫什么都得求值，不能按名字猜类别。

    GB/T 7714 作者-年制的年份键叫 `issued-year`、ISO 690 的作者键叫 `responsability`，
    前缀都认不出来；以前这两条被跳过，文献表退回引用顺序。
    """
    zh = """
@article{later, author={Zhang, San}, title={Later}, journal={J}, year={2022}}
@article{earlier, author={Zhang, San}, title={Earlier}, journal={J}, year={2020}}
"""
    engine = CitationEngine(zh, CSL / "chinese-gb7714-2015-author-date.csl", lang="zh")
    engine.reserve(["later", "earlier"])
    for key in ("later", "earlier"):
        engine.cite([(key, "")])
    assert [key for key, _ in engine.bibliography_segments()] == ["earlier", "later"]

    en = """
@book{smith, author={Smith, John}, title={A Book}, publisher={P}, year={2020}}
@book{doe, author={Doe, Jane}, title={B Book}, publisher={P}, year={2021}}
"""
    engine = CitationEngine(en, CSL / "iso690-author-date-en.csl", lang="en")
    engine.reserve(["smith", "doe"])
    for key in ("smith", "doe"):
        engine.cite([(key, "")])
    assert [key for key, _ in engine.bibliography_segments()] == ["doe", "smith"]


def test_repeated_author_is_replaced_in_mla_bibliography() -> None:
    """MLA 的 `subsequent-author-substitute`：相邻同作者的第二条换成 `———`。

    替换按**渲染出来的**姓名比较，样式把名缩写、用编者顶替作者时都跟着变。
    """
    bib = """
@book{s1, author={Smith, John}, title={Alpha}, publisher={P}, year={2020}}
@book{s2, author={Smith, John}, title={Beta}, publisher={P}, year={2022}}
@book{d1, author={Doe, Jane}, title={Gamma}, publisher={P}, year={2021}}
"""
    engine = CitationEngine(bib, CSL / "modern-language-association.csl", lang="en")
    engine.reserve(["s1", "s2", "d1"])
    for key in ("s1", "s2", "d1"):
        engine.cite([(key, "")])
    rendered = [
        "".join(text for text, _ in segments)
        for _key, segments in engine.bibliography_segments()
    ]
    assert rendered[0].startswith("Doe, Jane."), rendered
    assert rendered[1].startswith("Smith, John."), rendered
    assert rendered[2].startswith("———."), rendered


BLOCK_STYLE = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>probe</title><id>probe</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout><text variable="title"/></layout></citation>
  <bibliography><layout suffix=".">
    <group display="block"><text variable="title"/></group>
    <group display="{display}"><text variable="publisher"/></group>
    <group delimiter=", "><text variable="publisher-place"/>
      <date variable="issued"><date-part name="year"/></date></group>
  </layout></bibliography>
</style>'''


def test_block_display_starts_a_new_line(tmp_path: Path) -> None:
    """`display="block"` 让文献条目内部换行，而不是挤成一段。

    `display="indent"` 不在这里：它要求缩进量，而引擎只换行会静默丢掉缩进，所以
    `check_style` 直接拒绝（见 test_csl_feature_gate.py）。
    """
    from md_to_word.csl.string import LINE_BREAK

    style = tmp_path / "block.csl"
    style.write_text(BLOCK_STYLE.replace("{display}", "block"), encoding="utf-8")
    engine = CitationEngine(
        "@book{b, author={Smith, John}, title={A Book}, publisher={Acme Press}, "
        "address={London}, year={2020}}",
        style, lang="en",
    )
    engine.reserve(["b"])
    engine.cite([("b", "")])
    assert engine.bibliography()[0] == "A Book\nAcme Press\nLondon, 2020."

    segments = engine.bibliography_segments()[0][1]
    assert LINE_BREAK in "".join(text for text, _ in segments)


def test_block_join_keeps_the_seam_normalization() -> None:
    """`display` 的组装路径不能绕过 `join()` 的边界归一化，否则会多一个空格。"""
    from md_to_word.csl.model import _join_blocks
    from md_to_word.csl.string import String

    parts = [String("Things. "), String("London")]
    assert str(_join_blocks(parts, ". ")) == "Things. London"


def test_block_display_becomes_a_word_line_break(tmp_path: Path) -> None:
    """OOXML 里段内换行是 `<w:br/>`，不能写进 `<w:t>` 当普通字符。"""
    (tmp_path / "block.csl").write_text(
        BLOCK_STYLE.replace("{display}", "block"), encoding="utf-8")
    (tmp_path / "refs.bib").write_text(
        "@book{b, author={Smith, John}, title={A Book}, publisher={Acme Press}, "
        "address={London}, year={2020}}\n", encoding="utf-8")
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\ncsl: block.csl\n---\n\n# 一\n\n引用 [@b]。\n\n"
        "%% 参考文献标题 参考文献\n", encoding="utf-8")
    out = tmp_path / "m.docx"
    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=out))
    assert result.returncode == 0, result.errors

    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert "A Book</w:t><w:br/><w:t" in xml, xml[xml.find("A Book")-80:xml.find("A Book")+300]


def test_date_range_uses_the_declared_range_delimiter(tmp_path: Path) -> None:
    """日期区间的分隔符写在 `<date-part range-delimiter>` 上，默认才是短横线。"""
    style = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>probe</title><id>probe</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout><text variable="title"/></layout></citation>
  <bibliography><layout>
    <date variable="issued">{part}</date>
  </layout></bibliography>
</style>'''
    bib = ('[{"id": "a", "type": "book", "title": "T", '
           '"issued": {"date-parts": [[2020], [2022]]}}]')

    declared = tmp_path / "declared.csl"
    declared.write_text(style.format(part='<date-part name="year" range-delimiter="—"/>'),
                        encoding="utf-8")
    engine = CitationEngine(bib, declared, lang="en")
    engine.cite([("a", "")])
    assert engine.bibliography()[0] == "2020—2022"

    default = tmp_path / "default.csl"
    default.write_text(style.format(part='<date-part name="year"/>'), encoding="utf-8")
    engine = CitationEngine(bib, default, lang="en")
    engine.cite([("a", "")])
    assert engine.bibliography()[0] == "2020–2022"


def test_citation_number_follows_the_sorted_bibliography() -> None:
    """文献表按作者排的数字制样式（ACM），编号也按文献表走。

    第三条被引的文献可以印成 `[1]`：文内编号与文献表必须一致，不然读者找不到。
    """
    bib = """
@book{smith1, author={Smith, John}, title={A Book}, publisher={P}, year={2020}}
@book{smith2, author={Smith, John}, title={Another Book}, publisher={P}, year={2022}}
@article{doe, author={Doe, Jane and Roe, Richard}, title={An Article}, journal={J}, year={2021}}
"""
    engine = CitationEngine(bib, CSL / "acm-sig-proceedings.csl", lang="en")
    engine.reserve(["smith1", "smith2", "doe"])
    cited = {
        key: "".join(text for text, _ in engine.cite([(key, "")]))
        for key in ("smith1", "smith2", "doe")
    }
    assert cited == {"smith1": "[2]", "smith2": "[3]", "doe": "[1]"}
    assert [key for key, _ in engine.bibliography_segments()] == ["doe", "smith1", "smith2"]
    assert engine.bibliography()[0].startswith("[1]\tDoe"), engine.bibliography()


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
    separated = engine._separate_first_field(["[1]J. Doe and J. Roe, ", "“T”"], 1)
    assert "".join(text for text, _ in separated) == "[1]\tJ. Doe and J. Roe, “T”"


def test_no_separator_when_the_number_is_not_where_the_style_says() -> None:
    engine = CitationEngine(BIB, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    engine._first_field_column = True
    engine._number_prefix, engine._number_suffix = "[", "]"
    separated = engine._separate_first_field(["Doe, J. A study."], 3)
    assert "".join(text for text, _ in separated) == "Doe, J. A study."


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


def test_engine_comes_from_the_csl_package() -> None:
    """引擎在仓库里，不是外部依赖：否则修正与引擎版本会再次各走各的。"""
    import md_to_word.transform.citations as citations

    assert citations.CitationStylesStyle.__module__.startswith(
        "md_to_word.csl"
    )


def test_each_gbt_entry_uses_its_own_language_for_et_al() -> None:
    """GB/T 8.1.2：中文条目印「等」，西文条目印「et al.」——同一份文献表里各按各的。

    消息语言与文档语言是两件事，逐条语言又不随文档语言变；这里把两种组合都锁住。
    """
    bib = """
@article{zh, author={张三 and 李四 and 王五 and 赵六 and 钱七},
  title={中文文献}, journal={中国科学}, year={2020}}
@article{en, author={Alpha, Ann and Beta, Bob and Gamma, Gail and Delta, Dan and Epsilon, Eve},
  title={An English Work}, journal={J}, year={2020}}
"""
    csl = CSL / "chinese-gb7714-2015-numeric.csl"
    for lang, citation_lang in (("zh", "zh"), ("en", "zh"), ("zh", "en")):
        engine = CitationEngine(bib, csl, lang=lang, citation_lang=citation_lang)
        engine.cite([("zh", ""), ("en", "")])
        entries = dict(engine.bibliography_entries())
        zh_text = "".join(text for text, _ in entries["zh"])
        en_text = "".join(text for text, _ in entries["en"])
        assert "等" in zh_text, (lang, citation_lang, zh_text)
        assert "et al." in en_text, (lang, citation_lang, en_text)
        assert "等" not in en_text, (lang, citation_lang, en_text)


def test_multilayout_style_picks_layout_by_item_language(tmp_path: Path) -> None:
    """CSL-M 的多 layout：英文条目走 `locale="en"` 那一支，中文条目走默认那一支。

    2015 版 GB/T 的两份样式原本把英文 layout 注释掉了，就是因为引擎只认第一个
    layout；现在按条目语言选，注释已经恢复。
    """
    csl = tmp_path / "multi.csl"
    csl.write_text("""<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>multi</title><id>multi</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation>
    <layout locale="en" delimiter="; "><text value="EN:"/><text variable="title"/></layout>
    <layout delimiter="; "><text value="ZH:"/><text variable="title"/></layout>
  </citation>
  <bibliography>
    <layout locale="en" suffix="."><text value="EN:"/><text variable="title"/></layout>
    <layout suffix="."><text value="ZH:"/><text variable="title"/></layout>
  </bibliography>
</style>""", encoding="utf-8")
    bib = """
@book{en, author={Alpha, Ann}, title={English}, year={2020}}
@book{zh, author={张三}, title={中文}, year={2020}}
"""
    engine = CitationEngine(bib, csl, lang="zh")
    assert _text(engine, ("en", ""), ("zh", "")) == "EN:English; ZH:中文"
    entries = dict(engine.bibliography_entries())
    assert "".join(t for t, _ in entries["en"]) == "EN:English."
    assert "".join(t for t, _ in entries["zh"]) == "ZH:中文."


def test_gbt_author_date_groups_bibliography_by_language() -> None:
    """GB/T 7714-2015 §9.2：著者-年制按中文、日文、西文、俄文、其他集中。"""
    bib = """
@article{zh, author={张三}, title={中文文献}, journal={中国科学}, year={2020}}
@article{en, author={Smith, Ann}, title={An English Work}, journal={J}, year={2021}}
@article{ru, author={Иванов, Иван}, title={Русская статья}, journal={Журнал}, year={2019}}
@article{ja, author={山田, 太郎}, title={日本語の論文}, journal={雑誌}, year={2022}}
"""
    order = [("zh", ""), ("en", ""), ("ru", ""), ("ja", "")]

    author_date = CitationEngine(
        bib, CSL / "chinese-gb7714-2015-author-date.csl", lang="zh")
    author_date.cite(order)
    assert [key for key, _ in author_date.bibliography_entries()] == ["zh", "ja", "en", "ru"]

    numeric = CitationEngine(
        bib, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    numeric.cite(order)
    assert [key for key, _ in numeric.bibliography_entries()] == ["zh", "en", "ru", "ja"]


def test_style_level_locale_override_wins_for_page_ranges() -> None:
    """GB/T 样式在通用 `<locale>` 里把页码分隔符定为 `-`；不能因为条目是中文，
    就让系统 zh-CN 的 `～` 反盖样式自己的声明。"""
    bib = "@article{zh, author={张三}, title={中文}, journal={中国科学}, year={2025}, pages={101--110}}"
    engine = CitationEngine(bib, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    engine.cite([("zh", "")])
    rendered = engine.bibliography()[0]
    assert "101-110" in rendered
    assert "～" not in rendered


def test_structured_segments_keep_italics_and_carry_no_html() -> None:
    """引擎直接给 (文本, 格式)：斜体是 run 属性，不再靠 `<i>` 标签 + 正则解析。"""
    bib = (
        "@article{a, author={Adams, Bo}, title={A study}, "
        "journal={Journal of Tests}, volume={3}, year={2019}}"
    )
    engine = CitationEngine(bib, CSL / "apa.csl", lang="en")
    engine.cite([("a", "")])
    segments = dict(engine.bibliography_entries())["a"]
    text = "".join(part for part, _ in segments)
    assert "Journal of Tests" in text
    assert {"italic": True} in [fmt for _, fmt in segments]
    assert "<i>" not in text and "</i>" not in text


def test_superscript_numeric_runs_keep_their_format() -> None:
    """Nature 的上标是 run 属性；合并连续编号时不能退回普通文本。"""
    bib = "\n".join(
        f"@article{{n{i}, author={{A{i}, X}}, title={{P{i}}}, journal={{J}}, year={{200{i}}}}}"
        for i in range(1, 4)
    )
    engine = CitationEngine(bib, CSL / "nature.csl", lang="en")
    segments = engine.cite([("n1", ""), ("n2", ""), ("n3", "")])
    text = "".join(part for part, _ in segments)
    assert "1–3" in text
    assert all(fmt.get("superscript") for part, fmt in segments if part.strip())

def test_the_docx_keeps_bibliography_italics(tmp_path: Path) -> None:
    """引文里的斜体要一路落到 Word run，不能只活在内存片段里。"""
    (tmp_path / "refs.bib").write_text(
        "@article{a, author={Adams, Bo}, title={A study}, "
        "journal={Journal of Tests}, volume={3}, year={2019}}\n",
        encoding="utf-8",
    )
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n# 一\n\n引用 [@a]。\n",
        encoding="utf-8",
    )
    out = tmp_path / "m.docx"
    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=out))
    assert result.returncode == 0, result.errors

    root = etree.fromstring(zipfile.ZipFile(out).read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    for run in root.findall(".//w:r", ns):
        text = "".join(node.text or "" for node in run.findall("w:t", ns))
        if "Journal of Tests" in text:
            assert run.find("w:rPr/w:i", ns) is not None, text
            break
    else:
        raise AssertionError("bibliography journal title not found in document.xml")


def test_sort_only_particle_is_demoted_in_sort_keys_only() -> None:
    """`demote-non-dropping-particle="sort-only"`：排序按 Berg，正文仍印 van der Berg。"""
    bib = (
        "@article{berg, author={van der Berg, Johannes}, title={Networks}, "
        "journal={J}, year={2019}}\n"
        "@article{bearman, author={Bearman, Mark}, title={Discourses}, "
        "journal={J}, year={2023}}\n"
        "@article{chen, author={Chen, Wei}, title={Parsing}, journal={J}, year={2021}}\n"
    )
    engine = CitationEngine(bib, CSL / "acm-sig-proceedings.csl", lang="en")
    keys = ["berg", "bearman", "chen"]
    engine.reserve(keys)
    for key in keys:
        engine.cite([(key, "")])
    entries = ["".join(t for t, _ in segs) for _k, segs in engine.bibliography_entries()]
    assert "van der Berg" in entries[1] and "[2]" in entries[1], entries[1]
    assert "[3]" in entries[2], entries[2]


def test_empty_given_does_not_leave_a_dangling_period() -> None:
    """中文作者常写成 `given: ""`；没有可缩写的词，就不能印 `王伟伟, .`。"""
    bib = (
        '[{"id": "zh", "type": "article-journal", '
        '"author": [{"family": "王伟伟", "given": ""}, {"family": "顾炎辉", "given": ""}, '
        '{"family": "余隋怀", "given": ""}], "title": "研究", '
        '"container-title": "学报", "issued": {"date-parts": [[2024]]}}]'
    )
    engine = CitationEngine(bib, CSL / "apa.csl", lang="en")
    engine.reserve(["zh"])
    engine.cite([("zh", "")])
    text = "".join(t for t, _ in engine.bibliography_entries()[0][1])
    assert ", ." not in text and "., &" not in text, text
    assert "王伟伟, 顾炎辉, & 余隋怀" in text, text


def test_single_citation_keeps_the_year_suffix() -> None:
    """同一作者同年的两条分开引用时，正文也要带 a/b，否则和文献表对不上。"""
    bib = (
        "@article{x1, author={Smith, John}, title={Alpha}, journal={J}, year={2020}}\n"
        "@article{x2, author={Smith, John}, title={Beta}, journal={J}, year={2020}}\n"
    )
    for style in ("emerald-harvard.csl", "frontiers.csl", "springer-basic-author-date.csl"):
        engine = CitationEngine(bib, CSL / style, lang="en")
        engine.reserve(["x1", "x2"])
        first = _text(engine, ("x1", ""))
        second = _text(engine, ("x2", ""))
        assert "2020a" in first and "2020b" in second, (style, first, second)


def test_date_range_affixes_wrap_the_range_once() -> None:
    """`(2020)–(2021)` 是两头各套一次前后缀；区间应只套一次：`(2020–2021)`。"""
    bib = (
        '[{"id": "r", "type": "article-journal", "author": [{"family": "Garcia", "given": "L"}], '
        '"title": "R", "container-title": "J", "volume": "7", "page": "11-29", '
        '"issued": {"date-parts": [[2020], [2021]]}}]'
    )
    engine = CitationEngine(
        bib, CSL / "springer-lecture-notes-in-computer-science.csl", lang="en")
    engine.reserve(["r"])
    engine.cite([("r", "")])
    text = "".join(t for t, _ in engine.bibliography_entries()[0][1])
    assert "(2020–2021)" in text and "(2020)–(2021)" not in text, text


def test_replaced_edition_label_is_not_printed_again() -> None:
    """题名替掉作者时 edition 已随替身渲染过；后面的 `<label>` 不能再印 `(ed.)`。"""
    bib = (
        '[{"id": "cmos", "type": "book", "title": "The Chicago Manual of Style", '
        '"edition": "17", "publisher": "University of Chicago Press", '
        '"issued": {"date-parts": [[2017]]}}]'
    )
    engine = CitationEngine(bib, CSL / "apa.csl", lang="en")
    engine.reserve(["cmos"])
    engine.cite([("cmos", "")])
    text = "".join(t for t, _ in engine.bibliography_entries()[0][1])
    assert "(17th ed.)" in text and "(ed.)." not in text, text


def test_numeric_collapse_does_not_touch_prefixes_or_locators() -> None:
    """前缀里的数字不是引用编号，不能并成区间。"""
    bib = (
        "@article{a, author={A, Ann}, title={A}, journal={J}, year={2020}}\n"
        "@article{b, author={B, Bob}, title={B}, journal={J}, year={2021}}\n"
        "@article{c, author={C, Cat}, title={C}, journal={J}, year={2022}}\n"
    )
    engine = CitationEngine(
        bib, CSL / "chinese-gb7714-2015-numeric.csl", lang="zh")
    engine.reserve(["a", "b", "c"])
    text = _text(engine, ("a", "", "see [1, 2, 3]"))
    assert "1–3" not in text, text


def test_possessive_apostrophe_is_not_a_closing_quote() -> None:
    from md_to_word.transform.citation_postprocess import _punctuation_in_quote_segments

    segments = [("The Poets’", {}), (", J", {})]
    out = _punctuation_in_quote_segments(segments)
    assert "".join(t for t, _ in out) == "The Poets’, J"


def test_explicit_language_wins_over_script_guessing() -> None:
    from md_to_word.transform.citation_sort import _language_group

    assert _language_group({"language": "en", "title": "中文标题"}) == 2
    assert _language_group({"language": "ko", "title": "English title"}) == 4
    assert _language_group({"title": "中文标题"}) == 0


def test_single_quoted_style_attributes_are_read(tmp_path: Path) -> None:
    """合法 CSL 可以用单引号写属性；选项探测走解析后的节点，不能靠正则匹配双引号。"""
    style = tmp_path / "single-quote.csl"
    style.write_text(
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<style xmlns='http://purl.org/net/xbiblio/csl' class='in-text' version='1.0' "
        "default-locale='en-US'>\n"
        "  <info><title>Probe</title><id>http://example.com/probe</id>"
        "<updated>2024-01-01T00:00:00+00:00</updated></info>\n"
        "  <citation collapse='year'><layout prefix='(' suffix=')' delimiter='; '>\n"
        "    <group delimiter=', '><names variable='author'><name form='short'/></names>\n"
        "    <date variable='issued'><date-part name='year'/></date></group>\n"
        "  </layout></citation>\n"
        "  <bibliography><layout><text variable='title'/></layout></bibliography>\n"
        "</style>\n",
        encoding="utf-8",
    )
    bib = (
        "@article{a, author={Smith, John}, title={A}, journal={J}, year={2020}}\n"
        "@article{b, author={Smith, John}, title={B}, journal={J}, year={2021}}\n"
    )
    engine = CitationEngine(bib, style, lang="en")
    engine.reserve(["a", "b"])
    assert _text(engine, ("a", ""), ("b", "")) == "(Smith, 2020, 2021)"


def test_style_affix_spaces_do_not_double_or_precede_punctuation() -> None:
    """`suffix=" "` 遇上空子元素会留下 `Self-published .` 或双空格。"""
    bib = (
        '[{"id": "b", "type": "book", "title": "The Chicago Manual of Style", '
        '"edition": "17", "publisher": "University of Chicago Press", '
        '"publisher-place": "Chicago", "issued": {"date-parts": [[2017]]}}]'
    )
    engine = CitationEngine(bib, CSL / "elsevier-harvard.csl", lang="en")
    engine.reserve(["b"])
    engine.cite([("b", "")])
    text = "".join(t for t, _ in engine.bibliography_entries()[0][1])
    assert "  " not in text and " ." not in text, repr(text)

    undated = bib.replace(', "issued": {"date-parts": [[2017]]}', "").replace(
        "University of Chicago Press", "Self-published")
    bmj = CitationEngine(undated, CSL / "bmj.csl", lang="en")
    bmj.reserve(["b"])
    bmj.cite([("b", "")])
    text = "".join(t for t, _ in bmj.bibliography_entries()[0][1])
    assert "Self-published." in text and "Self-published ." not in text, repr(text)


def test_extended_creator_roles_do_not_crash() -> None:
    """Zotero 的影视条目会带 director/producer 等角色；这些字段不能当普通字符串。"""
    data = (
        '[{"id": "x", "type": "motion_picture", "title": "Film", '
        '"director": [{"family": "Doe", "given": "Jane"}], '
        '"issued": {"date-parts": [[2020]]}}]'
    )
    engine = CitationEngine(data, CSL / "apa.csl", lang="en")
    engine.reserve(["x"])
    engine.cite([("x", "")])
    text = "".join(t for t, _ in engine.bibliography_entries()[0][1])
    assert "Doe, J." in text and "Director" in text, text


def test_available_date_is_a_date_variable() -> None:
    data = (
        '[{"id": "x", "type": "book", "title": "Book", '
        '"author": [{"family": "Doe", "given": "Jane"}], '
        '"available-date": {"date-parts": [[2020, 5, 1]]}}]'
    )
    engine = CitationEngine(data, CSL / "chicago-author-date.csl", lang="en")
    engine.reserve(["x"])
    engine.cite([("x", "")])
    assert "Book" in "".join(t for t, _ in engine.bibliography_entries()[0][1])


def test_same_year_date_range_keeps_the_year() -> None:
    data = (
        '[{"id": "x", "type": "article-journal", "title": "R", '
        '"author": [{"family": "Doe", "given": "Jane"}], '
        '"container-title": "J", "issued": {"date-parts": [[2020, 3, 1], [2020, 3, 5]]}}]'
    )
    apa = CitationEngine(data, CSL / "apa.csl", lang="en")
    apa.reserve(["x"])
    assert _text(apa, ("x", "")) == "(Doe, 2020)"
    apa.cite([("x", "")])
    assert "2020" in "".join(t for t, _ in apa.bibliography_entries()[0][1])

    chicago = CitationEngine(data, CSL / "chicago-author-date.csl", lang="en")
    chicago.reserve(["x"])
    chicago.cite([("x", "")])
    text = "".join(t for t, _ in chicago.bibliography_entries()[0][1])
    assert "March 1–5" in text, text


def test_cjk_names_are_family_then_given_without_separator() -> None:
    data = (
        '[{"id": "x", "type": "article-journal", "title": "研究", '
        '"author": [{"family": "张", "given": "三"}], '
        '"container-title": "学报", "issued": {"date-parts": [[2020]]}, "language": "zh"}]'
    )
    for style in ("apa.csl", "chicago-author-date.csl", "chinese-gb7714-2015-author-date.csl"):
        engine = CitationEngine(data, CSL / style, lang="zh")
        engine.reserve(["x"])
        engine.cite([("x", "")])
        text = "".join(t for t, _ in engine.bibliography_entries()[0][1])
        assert "张三" in text and "张," not in text and "张 " not in text, (style, text)


def test_number_of_volumes_renders_number_and_label() -> None:
    data = (
        '[{"id": "x", "type": "book", "title": "Works", '
        '"author": [{"family": "Smith", "given": "John"}], '
        '"number-of-volumes": 3, "issued": {"date-parts": [[2020]]}}]'
    )
    engine = CitationEngine(data, CSL / "apa.csl", lang="en")
    engine.reserve(["x"])
    engine.cite([("x", "")])
    text = "".join(t for t, _ in engine.bibliography_entries()[0][1])
    assert "(Vols. 1–3)" in text, text


def test_expanded_page_range_pads_the_last_page() -> None:
    data = (
        '[{"id": "x", "type": "article-journal", "title": "R", '
        '"author": [{"family": "Doe", "given": "J"}], "container-title": "J", '
        '"page": "33-5", "issued": {"date-parts": [[2020]]}}]'
    )
    engine = CitationEngine(data, CSL / "apa.csl", lang="en")
    engine.reserve(["x"])
    engine.cite([("x", "")])
    assert "33–35" in "".join(t for t, _ in engine.bibliography_entries()[0][1])


def test_citation_order_without_sort_follows_the_text() -> None:
    bib = (
        "@article{a, author={Alpha, Ann}, title={A}, journal={J}, year={2020}}\n"
        "@article{b, author={Beta, Bob}, title={B}, journal={J}, year={2020}}\n"
    )
    engine = CitationEngine(bib, CSL / "modern-language-association.csl", lang="en")
    engine.reserve(["a", "b"])
    assert _text(engine, ("b", ""), ("a", "")) == "(Beta; Alpha)"


def test_if_variable_ignores_empty_values(tmp_path: Path) -> None:
    style = tmp_path / "if-var.csl"
    style.write_text(
        '<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">'
        "<info><title>p</title><id>p</id>"
        "<updated>2024-01-01T00:00:00+00:00</updated></info>"
        '<citation><layout><choose><if variable="title"><text value="HAS"/></if>'
        '<else><text value="NONE"/></else></choose></layout></citation>'
        '<bibliography><layout><text variable="title"/></layout></bibliography></style>',
        encoding="utf-8",
    )
    data = '[{"id": "x", "type": "book", "title": "", "author": [{"family": "A", "given": "B"}]}]'
    engine = CitationEngine(data, style, lang="en")
    assert _text(engine, ("x", "")) == "NONE"


def test_names_label_without_an_explicit_name_follows_the_names() -> None:
    """`<names>` 只有 `<label>`、没有 `<name>` 时，隐式 name 在前、label 在后。

    AMA 的 `<names variable="editor"><label form="short" prefix=", "/></names>`
    应出 `Smith A, Jones B, eds.`。citeproc-js 也是如此；pandoc 把 `eds.` 放到
    名字前面，是它自己的偏差，不跟。
    """
    bib = ("@book{e1, editor={Smith, Ann and Jones, Bob}, title={Book Title},"
           " publisher={Press}, year={2020}}")
    ama = CitationEngine(bib, CSL / "american-medical-association.csl", lang="en")
    ama.cite([("e1", "")])
    assert ama.bibliography()[0].endswith(
        "Smith A, Jones B, eds. Book Title. Press; 2020.")


SORT_STYLE = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>sort</title><id>sort</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <macro name="keynames">{body}</macro>
  <citation><layout><text variable="title"/></layout></citation>
  <bibliography>
    <sort><key macro="keynames"/></sort>
    <layout><text variable="title"/></layout>
  </bibliography>
</style>'''


def _sorted_titles(tmp_path: Path, body: str, items: list, order: list) -> list:
    import json

    style = tmp_path / "sort.csl"
    style.write_text(SORT_STYLE.replace("{body}", body), encoding="utf-8")
    engine = CitationEngine(json.dumps(items), style, lang="en")
    for key in order:
        engine.cite([(key, "")])
    return engine.bibliography()


def test_sort_keys_ignore_names_labels(tmp_path: Path) -> None:
    """排序键只取姓名：`eds.` 这类 label 不参与比较，同姓时保持引用顺序。

    citeproc-js 生成的排序键同样跳过 label。
    """
    items = [
        {"id": "b", "type": "book", "title": "B",
         "editor": [{"family": "Smith", "given": "J"}]},
        {"id": "a", "type": "book", "title": "A",
         "author": [{"family": "Smith", "given": "J"}]},
    ]
    body = ('<names variable="author editor">'
            '<label form="short" prefix=", "/></names>')
    assert _sorted_titles(tmp_path, body, items, ["b", "a"]) == ["B", "A"]


def test_sort_keys_ignore_the_et_al_term(tmp_path: Path) -> None:
    """截断后的 `et al.` 不写进排序键：两个键都是 `Smith, A`，按引用顺序。"""
    items = [
        {"id": "a", "type": "book", "title": "A",
         "author": [{"family": "Smith", "given": "A"},
                    {"family": "Zeta", "given": "B"}]},
        {"id": "b", "type": "book", "title": "B",
         "author": [{"family": "Smith", "given": "A"}]},
    ]
    body = ('<names variable="author">'
            '<name et-al-min="2" et-al-use-first="1"/></names>')
    assert _sorted_titles(tmp_path, body, items, ["a", "b"]) == ["A", "B"]


def test_name_form_count_respects_the_et_al_threshold(tmp_path: Path) -> None:
    """`form="count"` 是「本来会印出几个名字」：没触发 et-al 时就是全部。"""
    import json

    style_text = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>count</title><id>count</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout><names variable="author">
    <name form="count" et-al-min="{min}" et-al-use-first="1"/>
  </names></layout></citation>
  <bibliography><layout><text variable="title"/></layout></bibliography>
</style>'''
    items = [{
        "id": "a", "type": "book", "title": "A",
        "author": [{"family": f"Name{i}"} for i in range(5)],
    }]
    for minimum, expected in (("6", "5"), ("3", "1")):
        style = tmp_path / f"count{minimum}.csl"
        style.write_text(style_text.replace("{min}", minimum), encoding="utf-8")
        engine = CitationEngine(json.dumps(items), style, lang="en")
        assert _text(engine, ("a", "")) == expected


def test_initialize_false_only_marks_existing_initials(tmp_path: Path) -> None:
    """`initialize="false"` + `initialize-with="."`：`James T Kirk` → `James T. Kirk`。"""
    style_text = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>init</title><id>init</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout><names variable="author">
    <name initialize="false" initialize-with="."/>
  </names></layout></citation>
  <bibliography><layout><text variable="title"/></layout></bibliography>
</style>'''
    style = tmp_path / "init.csl"
    style.write_text(style_text, encoding="utf-8")
    engine = CitationEngine(
        "@book{b, author={Kirk, James T}, title={A Book}, year={2020}}",
        style, lang="en")
    assert _text(engine, ("b", "")) == "James T. Kirk"


DISAMBIG_HYPHEN_STYLE = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>hyphen</title><id>hyphen</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation disambiguate-add-givenname="true"
            givenname-disambiguation-rule="primary-name-with-initials">
    <layout prefix="(" suffix=")">
      <names variable="author"><name form="short" initialize-with=". "/></names>
      <date variable="issued" prefix=", "><date-part name="year"/></date>
    </layout>
  </citation>
  <bibliography><layout><text variable="title"/></layout></bibliography>
</style>'''


def test_disambiguation_initials_respect_hyphens(tmp_path: Path) -> None:
    """`Jean-Luc` 补首字母是 `J.-L.`，跟着样式的 `initialize-with`，不是固定的 `. `。"""
    import json

    style = tmp_path / "hyphen.csl"
    style.write_text(DISAMBIG_HYPHEN_STYLE, encoding="utf-8")
    items = [
        {"id": "a", "type": "book", "title": "A",
         "author": [{"family": "Dupont", "given": "Jean-Luc"}],
         "issued": {"date-parts": [[2020]]}},
        {"id": "b", "type": "book", "title": "B",
         "author": [{"family": "Dupont", "given": "Jean-Paul"}],
         "issued": {"date-parts": [[2020]]}},
    ]
    engine = CitationEngine(json.dumps(items), style, lang="en")
    engine.reserve(["a", "b"])
    assert _text(engine, ("a", "")) == "(J.-L. Dupont, 2020)"
    assert _text(engine, ("b", "")) == "(J.-P. Dupont, 2020)"

    no_hyphen = tmp_path / "space.csl"
    no_hyphen.write_text(DISAMBIG_HYPHEN_STYLE.replace(
        'initialize-with=". "',
        'initialize-with=". " initialize-with-hyphen="false"'), encoding="utf-8")
    engine = CitationEngine(json.dumps(items), no_hyphen, lang="en")
    engine.reserve(["a", "b"])
    assert _text(engine, ("a", "")) == "(J. L. Dupont, 2020)"


def test_no_date_entries_collapse_like_citeproc_js() -> None:
    """同作者两条无年份文献：`n.d.-a` / `n.d.-b`，合并引用折成 `(Smith, n.d.-a, n.d.-b)`。"""
    import json

    items = [
        {"id": "a", "type": "book", "title": "Alpha",
         "author": [{"family": "Smith", "given": "John"}], "publisher": "P"},
        {"id": "b", "type": "book", "title": "Beta",
         "author": [{"family": "Smith", "given": "John"}], "publisher": "P"},
    ]
    engine = CitationEngine(json.dumps(items), CSL / "apa.csl", lang="en")
    engine.reserve(["a", "b"])
    assert _text(engine, ("a", "")) == "(Smith, n.d.-a)"
    assert _text(engine, ("a", ""), ("b", "")) == "(Smith, n.d.-a, n.d.-b)"


SUBSTITUTE_STYLE = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>sub</title><id>sub</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout prefix="(" suffix=")"><text variable="title"/></layout></citation>
  <bibliography subsequent-author-substitute="">
    <sort><key variable="author"/><key variable="issued"/></sort>
    <layout suffix=".">
      <group display="block"><names variable="author"><name name-as-sort-order="all"/></names></group>
      <text variable="title"/>
    </layout>
  </bibliography>
</style>'''


def test_empty_subsequent_author_substitute_drops_the_block(tmp_path: Path) -> None:
    """`subsequent-author-substitute=""` 是「重复作者整个不印」，不是「没设置」。"""
    import json

    style = tmp_path / "sub.csl"
    style.write_text(SUBSTITUTE_STYLE, encoding="utf-8")
    items = [
        {"id": "a", "type": "book", "title": "Alpha",
         "author": [{"family": "Smith", "given": "John"}],
         "issued": {"date-parts": [[2020]]}},
        {"id": "b", "type": "book", "title": "Beta",
         "author": [{"family": "Smith", "given": "John"}],
         "issued": {"date-parts": [[2021]]}},
    ]
    engine = CitationEngine(json.dumps(items), style, lang="en")
    engine.cite([("a", "")])
    engine.cite([("b", "")])
    assert engine.bibliography() == ["Smith, John\nAlpha.", "Beta."]


def test_empty_citation_does_not_leave_layout_affixes(tmp_path: Path) -> None:
    """整条引用没有输出时，不能只印 layout 的前后缀（孤零零的 `()`）。"""
    import json

    style = tmp_path / "empty.csl"
    style.write_text(SUBSTITUTE_STYLE, encoding="utf-8")
    engine = CitationEngine(
        json.dumps([{"id": "x", "type": "book",
                     "author": [{"family": "Doe"}]}]),
        style, lang="en")
    assert _text(engine, ("x", "")) == ""
