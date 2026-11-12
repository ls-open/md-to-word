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
