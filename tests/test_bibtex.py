"""`.bib` → CSL-JSON 的转换。

这一层是引文的原料：名字、年份、题名解析错了，文献表就错，而且**不会报错**——Word 里
只是少了几位作者或丢了 `[M]`。下面每条都对应一次真实踩过的坑。
"""

from __future__ import annotations

from md_to_word.config import get_csl_dir
from md_to_word.transform.bibtex import parse_bibtex
from md_to_word.transform.citations import CitationEngine, _collapse_numeric_runs


def _entry(text: str, key: str) -> dict:
    return next(e for e in parse_bibtex(text) if e["id"] == key)


def test_brace_protected_names_are_all_kept() -> None:
    """中文名常写成 `{{王伟伟} and {顾炎辉}}`：非贪婪正则会只读到第一个 `}`，丢掉后面的人。"""
    entry = _entry(
        "@article{k,\n  author = {{王伟伟} and {顾炎辉} and {余隋怀}},\n  year = {2024}\n}\n", "k"
    )
    assert [a["literal"] for a in entry["author"]] == ["王伟伟", "顾炎辉", "余隋怀"]


def test_latex_escapes_are_unescaped() -> None:
    entry = _entry(
        "@techreport{k,\n  title = {A \\& B study of 50\\% cases},\n  institution = {McKinsey \\& Company}\n}\n",
        "k",
    )
    assert entry["title"] == "A & B study of 50% cases"
    assert entry["publisher"] == "McKinsey & Company"


def test_name_particle_is_split_out() -> None:
    """`van Wee` 的前缀单列成 non-dropping-particle，CSL 才知道它不该跟着姓氏大写。"""
    entry = _entry("@article{k,\n  author = {van Wee, Bert and Liao, F}\n}\n", "k")
    assert entry["author"][0]["family"] == "Wee"
    assert entry["author"][0]["non-dropping-particle"] == "van"


def test_url_date_becomes_accessed() -> None:
    entry = _entry("@article{k,\n  urldate = {2026-09-09}\n}\n", "k")
    assert entry["accessed"] == {"date-parts": [[2026, 9, 9]]}


def test_printed_book_keeps_type_marker() -> None:
    """印刷版专著没有 URL/DOI，`[M]` 不能因为"组里变量全空"被整组抑制掉。"""
    engine = CitationEngine(
        "@book{k,\n  author = {Hayes, Andrew F.},\n  title = {T},\n  year = {2022},\n"
        "  publisher = {Guilford Press}\n}\n",
        get_csl_dir() / "chinese-gb7714-2015-numeric.csl",
    )
    engine.cite([("k", "")])
    text = engine.bibliography()[0]
    assert "[M]" in text, text


def test_consecutive_numbers_collapse_to_range() -> None:
    """数字制里连续三条以上要压成区间（GB/T 7714 与 IEEE 的硬要求）。"""
    assert _collapse_numeric_runs("[4,5,6]") == "[4–6]"
    assert _collapse_numeric_runs("[1,2,3,7,8,9]") == "[1–3,7–9]"
    # 两条不压：只有三条及以上才合并
    assert _collapse_numeric_runs("[4,5]") == "[4,5]"
    assert _collapse_numeric_runs("[4,6]") == "[4,6]"


def test_braced_and_and_compound_surname_preserved() -> None:
    """花括号保护的机构名内含 `and` 不能拆；复合姓氏 `{Smith Jr.}` 作为整体姓氏，不拆成粒子或掉后缀。"""
    bib = """
@misc{fao,
  author = {{Food and Agriculture Organization} and J. R. {Smith Jr.} and {World Bank}},
  year = {2024}
}
"""
    authors = _entry(bib, "fao")["author"]
    assert authors == [
        {"literal": "Food and Agriculture Organization"},
        {"family": "Smith Jr.", "given": "J. R."},
        {"literal": "World Bank"},
    ]

    particle_comma = _entry("@article{v, author = {{van Berg}, Jan}, year = {2023}}", "v")["author"]
    assert particle_comma == [{"family": "van Berg", "given": "Jan"}]


def test_periodical_vs_non_periodical_number_and_verbatim_fields() -> None:
    """`number` 在期刊里是 issue、在报告里是 number；URL/DOI/报告号里的 `--`/`~` 不可被排版引号/破折号改写。"""
    bib = """
@article{art,
  author = {Lin, Wei},
  title = {A--B Study},
  journal = {J. Test},
  volume = {10},
  number = {3},
  doi = {10.1000/a--b~1},
  url = {https://example.org/~user/a--b},
  year = {2025}
}
@techreport{tr,
  author = {{FAO}},
  title = {Annual Report},
  institution = {Food and Agriculture Organization},
  location = {Rome},
  number = {FAO-TR-2024--01},
  type = {Technical Report},
  year = {2024}
}
"""
    art = _entry(bib, "art")
    assert art["type"] == "article-journal"
    assert art["issue"] == "3"
    assert "number" not in art
    assert art["DOI"] == "10.1000/a--b~1"
    assert art["URL"] == "https://example.org/~user/a--b"
    assert "–" in art["title"]  # 普通正文题名的 -- 仍然正常转为短破折号

    tr = _entry(bib, "tr")
    assert tr["type"] == "report"
    assert tr["number"] == "FAO-TR-2024--01"
    assert "issue" not in tr
    assert tr["publisher"] == "Food and Agriculture Organization"
    assert tr["publisher-place"] == "Rome"
    assert tr["genre"] == "Technical Report"


def test_modern_types_howpublished_url_and_arxiv_misc() -> None:
    """现代类型映射、`howpublished={\\url{...}}` 提取、以及 `@misc` 网页与 arXiv 预印本的分流。"""
    bib = """
@software{sw,
  author = {Chen, Yi},
  title = {md-to-word},
  organization = {Open Science Lab},
  version = {3.5.0--beta},
  url = {https://github.com/example/md-to-word},
  year = {2025}
}
@dataset{ds,
  author = {Wang, Lei},
  title = {Corpus},
  publisher = {Zenodo},
  year = {2024}
}
@misc{web,
  author = {{Ministry of Education}},
  title = {Policy Notice},
  howpublished = {\\url{https://www.moe.gov.example/a--b}},
  year = {2025},
  urldate = {2026-11-12}
}
@misc{arxiv,
  author = {Zhang, Wei},
  title = {Preprint Paper},
  eprint = {2501.01234},
  archivePrefix = {arXiv},
  year = {2025}
}
"""
    sw = _entry(bib, "sw")
    assert sw["type"] == "software"
    assert sw["publisher"] == "Open Science Lab"
    assert sw["version"] == "3.5.0--beta"

    ds = _entry(bib, "ds")
    assert ds["type"] == "dataset"

    web = _entry(bib, "web")
    assert web["type"] == "webpage"
    assert web["URL"] == "https://www.moe.gov.example/a--b"

    arxiv = _entry(bib, "arxiv")
    assert arxiv["type"] == "article"
    assert arxiv["URL"] == "https://arxiv.org/abs/2501.01234"
    assert arxiv["genre"] == "preprint"

    # 真实走一遍 CSL 渲染，确认 `@misc` + URL 在 GB/T 7714 出 `[EB/OL]` 而 APA/IEEE 均可渲染
    gb = CitationEngine(bib, get_csl_dir() / "chinese-gb7714-2015-numeric.csl", lang="zh")
    gb.reserve(["web", "tr"])
    gb.cite([("web", "")])
    bib_entries = dict(gb.bibliography_entries())
    assert "[EB/OL]" in "".join(t for t, _ in bib_entries["web"])
    assert "https://www.moe.gov.example/a--b" in "".join(t for t, _ in bib_entries["web"])

    apa = CitationEngine(bib, get_csl_dir() / "apa.csl", lang="en")
    apa.reserve(["sw", "ds", "web", "arxiv"])
    for k in ("sw", "ds", "web", "arxiv"):
        assert apa.cite([(k, "")])
    assert len(apa.bibliography_entries()) == 4


def test_misc_with_url_and_text_howpublished_renders_platform() -> None:
    """`@misc` 同时带 `url` 与纯文本 `howpublished`（平台/发布方名称）时，APA 与 GB/T 7714 都不能悄悄丢掉。"""
    bib = """
@misc{moe2026b,
  author = {{教育部}},
  year = {2026},
  title = {大學、技專校院各系所註冊率［資料集］},
  howpublished = {政府資料開放平臺},
  url = {https://data.gov.tw/dataset/26228}
}
"""
    entry = _entry(bib, "moe2026b")
    assert entry["type"] == "webpage"
    assert entry["publisher"] == "政府資料開放平臺"

    for csl_name in ("apa.csl", "chinese-gb7714-2015-numeric.csl"):
        eng = CitationEngine(bib, get_csl_dir() / csl_name, lang="zh")
        eng.reserve(["moe2026b"])
        assert eng.cite([("moe2026b", "")])
        rendered = "".join(t for t, _ in dict(eng.bibliography_entries())["moe2026b"])
        assert "政府資料開放平臺" in rendered, (csl_name, rendered)
        assert "https://data.gov.tw/dataset/26228" in rendered, (csl_name, rendered)


# ── 真实文献库（arXiv / ACL / DBLP / GB/T / biblatex / CNKI 导出）里实际出现过、
# ── 而上面那批用例没覆盖的形态。每一条都对应一次「成稿里看得见」的错。

def test_parenthesised_entries_are_parsed() -> None:
    """BibTeX 标准允许 `@article(key, … )`。只认花括号时整份括号式文献库**静默消失**
    （真实文件 27 条只解析出 4 条，无异常、无警告）。"""
    entries = parse_bibtex(
        "@article(p1,\n  author = {Pearson, William R.},\n  title = {T},\n  journal = {J},\n  year = {2000}\n)\n"
        "@book(p2, author = {Doe, J.}, title = {B}, year = {2001})\n"
    )
    assert [e["id"] for e in entries] == ["p1", "p2"]
    assert entries[0]["container-title"] == "J"


def test_verbatim_fields_unescape_latex_but_keep_literal_chars() -> None:
    """DOI/URL 里的 `\\_` `\\%` `\\&` 是**转义**，必须还原（DBLP 导出里 296 条有 44 条这样）；
    而 `~` `--` 是技术字段的原样字符，不能当成排版连字。"""
    entry = _entry(
        "@article{k,\n  doi = {10.1007/3-540-48749-2\\_2},\n"
        "  url = {https://x/a\\%20b?x=1\\&y=2},\n  year = {2020}\n}\n", "k"
    )
    assert entry["DOI"] == "10.1007/3-540-48749-2_2"
    assert entry["URL"] == "https://x/a%20b?x=1&y=2"


def test_and_others_is_et_al_not_an_author_named_others() -> None:
    entry = _entry("@article{k,\n  author = {王临慧 and others},\n  year = {2020}\n}\n", "k")
    assert [a["literal"] for a in entry["author"]] == ["王临慧"]


def test_isbn_issn_pagetotal_bookauthor_are_kept() -> None:
    book = _entry(
        "@book{b,\n  author = {A, B},\n  title = {T},\n  isbn = {978-1-119-59612-7},\n"
        "  issn = {1674-120X},\n  pagetotal = {813},\n  year = {2020}\n}\n", "b"
    )
    assert book["ISBN"] == "978-1-119-59612-7"
    assert book["ISSN"] == "1674-120X"
    assert book["number-of-pages"] == "813"

    chapter = _entry(
        "@inbook{c,\n  author = {某甲},\n  bookauthor = {罗卫东 and 姚中秋},\n"
        "  title = {某章},\n  booktitle = {某书},\n  year = {2020}\n}\n", "c"
    )
    assert [a["literal"] for a in chapter["container-author"]] == ["罗卫东", "姚中秋"]


def test_type_only_becomes_genre_on_report_like_entries() -> None:
    """期刊条目的 `type` 是数据字段（DBLP 写 `Journal Articles`），不是描述语；
    无条件映射会让 APA 印出 `… [Journal articles]. 146, 106875.`"""
    article = _entry(
        "@article{k,\n  author = {A, B},\n  title = {T},\n  journal = {J},\n"
        "  type = {Journal Articles},\n  year = {2022}\n}\n", "k"
    )
    assert "genre" not in article

    report = _entry(
        "@techreport{r,\n  author = {A, B},\n  title = {T},\n  institution = {I},\n"
        "  type = {Technical Report},\n  year = {2019}\n}\n", "r"
    )
    assert report["genre"] == "Technical Report"


def test_published_article_with_eprint_is_not_a_preprint() -> None:
    """已正式发表的期刊论文常同时带 arXiv 号：那是附加信息，不是「预印本」。
    一律打 `genre=preprint` 会让 APA 给正经论文印 `[Preprint]`。"""
    published = _entry(
        "@article{p,\n  author = {Doe, J.},\n  title = {Pub},\n  journal = {Phys Rev D},\n"
        "  volume = {101},\n  number = {3},\n  pages = {034001},\n  year = {2020},\n"
        "  eprint = {1909.12345},\n  archiveprefix = {arXiv}\n}\n", "p"
    )
    assert "genre" not in published
    assert published["URL"] == "https://arxiv.org/abs/1909.12345"

    preprint = _entry(
        "@misc{m,\n  author = {Doe, J.},\n  title = {Pre},\n  year = {2021},\n"
        "  eprint = {2101.00001},\n  archiveprefix = {arXiv}\n}\n", "m"
    )
    assert preprint["genre"] == "preprint"


def test_eprint_with_arxiv_prefix_and_eprinttype_alias() -> None:
    """`eprint = {arXiv:2101.00001}` 自带前缀，再拼一次就是坏链（`abs/arXiv:…`）；
    `eprinttype` 是 biblatex 对 `archiveprefix` 的写法，两个都要认。"""
    prefixed = _entry(
        "@misc{e,\n  author = {A, B},\n  title = {T},\n  year = {2021},\n"
        "  eprint = {arXiv:2101.00001},\n  archiveprefix = {arXiv}\n}\n", "e"
    )
    assert prefixed["URL"] == "https://arxiv.org/abs/2101.00001"

    aliased = _entry(
        "@online{o,\n  author = {B, C},\n  title = {T},\n  year = {2004},\n"
        "  eprint = {math/0307200v3},\n  eprinttype = {arxiv}\n}\n", "o"
    )
    assert aliased["URL"] == "https://arxiv.org/abs/math/0307200v3"


def test_misc_with_journal_and_eprint_is_a_journal_article() -> None:
    """APS/INSPIRE 与 Google Scholar 混导常见「刊名 + 卷期页 + arXiv 号」的 `@misc`；
    判成章节会让 GB/T 印 `[A/OL]`、APA 印成 `In … (Preprint No. …)`。"""
    entry = _entry(
        "@misc{m,\n  author = {A, B},\n  title = {T},\n  journal = {Phys Rev D},\n"
        "  volume = {101},\n  number = {3},\n  eprint = {1909.1},\n  year = {2020}\n}\n", "m"
    )
    assert entry["type"] == "article-journal"


def test_venue_subtitle_and_shortjournal_map_to_csl_fields() -> None:
    """DBLP 派生的 `venue` 是刊名的另一个字段名（166 条期刊论文因此没有刊名）；
    `subtitle` 丢掉等于题名被腰斩。"""
    entry = _entry(
        "@article{k,\n  author = {A, B},\n  title = {主标题},\n  subtitle = {副标题},\n"
        "  venue = {Information and Software Technology},\n"
        "  shortjournal = {Inf. Softw. Technol.},\n  langid = {english},\n  year = {2022}\n}\n", "k"
    )
    assert entry["title"] == "主标题: 副标题"
    assert entry["container-title"] == "Information and Software Technology"
    assert entry["container-title-short"] == "Inf. Softw. Technol."
    assert entry["language"] == "english"


def test_percent_comments_are_not_fields_but_values_keep_percent() -> None:
    """biber 与人手写文件用 `%` 注释；注释掉的作者不能变成真作者，
    而 `title = {50% off}` 这种值里的百分号必须留着。"""
    commented = _entry(
        "@article{k,\n  title = {Real},\n  % author = {Commented, Out},\n  year = {2020}\n}\n", "k"
    )
    assert "author" not in commented
    assert commented["title"] == "Real"

    inline = _entry("@article{k, title = {50% off}, year = {2020}}\n", "k")
    assert inline["title"] == "50% off"


def test_junior_suffix_without_comma() -> None:
    """`John Smith Jr.` 的末词是后缀，不是姓氏；`Smith, Jr., John` 与 `J. R. {Smith Jr.}`
    两条路本来就对，这条补的是无逗号写法。"""
    entry = _entry("@article{k, author = {John Smith Jr.}, year = {2020}}\n", "k")
    assert entry["author"] == [{"family": "Smith", "given": "John", "suffix": "Jr."}]


def test_set_and_xdata_are_not_bibliography_entries() -> None:
    """`@set` / `@xdata` 是 biblatex 的组合与复用构造，不是文献；
    收下会得到没有题名作者的幽灵条目，被引用时渲染成空白。"""
    entries = parse_bibtex(
        "@set{s1, entryset={a,b}}\n@xdata{x1, publisher={P}}\n"
        "@article{a, title={T}, year={2020}}\n"
    )
    assert [e["id"] for e in entries] == ["a"]


def test_latex_markup_is_stripped_from_titles() -> None:
    """题名里的 `\\emph{…}` / `\\textsc{…}` 很常见。花括号先删再处理的话，
    命令与实词会粘成 `\\emphFoo`，成稿里就是乱码。"""
    entry = _entry(
        "@article{k,\n  title = {The \\emph{Foo} and \\textit{Bar} \\TeX\\ book},\n  year = {2020}\n}\n",
        "k",
    )
    assert entry["title"] == "The Foo and Bar TeX book"
