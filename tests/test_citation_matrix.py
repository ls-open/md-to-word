"""全条目类型 × 主流 CSL 样式矩阵回归测试（纯 Python `citeproc-py` + shim 层）。

覆盖主要 BibTeX 条目类型（article/book/inbook/incollection/inproceedings/proceedings/
techreport/phdthesis/mastersthesis/online/software/dataset/patent/standard/booklet/
unpublished/manual/misc）与常见边角情况（缺省字段、团体/译者/编者、LaTeX 重音、
大小写保护、多语言混排、同姓首字母分组消歧、`disambiguate="true"`、页码缩写、
中文序数词、全名/缩写初始化控制），确保全部 29 份内置 CSL 样式零报错、无幽灵标签或
静默丢字，并与 CSL 1.0 预期对齐。
"""

from __future__ import annotations

import pytest

from md_to_word.config import get_csl_dir
from md_to_word.transform.bibtex import parse_bibtex
from md_to_word.transform.citations import CitationEngine

CSL_DIR = get_csl_dir()
ALL_STYLES = sorted(p.name for p in CSL_DIR.glob("*.csl"))

MATRIX_BIB = r"""
@string{mit = "MIT Press"}

@article{art_en,
  author = {Venkatesh, Viswanath and Davis, Fred D.},
  title = {Why Does {AI} Adoption Vary? A Longitudinal Analysis},
  journal = {Management Information Systems Quarterly},
  volume = {45},
  number = {2},
  pages = {101--135},
  doi = {10.25300/MISQ/2021/15000},
  year = {2021}
}

@article{art_zh,
  author = {{王伟伟} and {顾炎辉} and {余隋怀}},
  title = {基于生成式人工智能的工业设计方法研究},
  journal = {机械工程学报},
  volume = {60},
  number = {12},
  pages = {45--58},
  year = {2024}
}

@article{art_multi4,
  author = {Bearman, Margaret and Ryan, Juliana and Ajjawi, Rola and Boud, David},
  title = {Discourses of artificial intelligence in higher education},
  journal = {Higher Education},
  volume = {86},
  number = {2},
  pages = {369--385},
  year = {2023}
}

@book{book_auth,
  author = {Hayes, Andrew F.},
  title = {Introduction to Mediation, Moderation, and Conditional Process Analysis},
  edition = {3},
  address = {New York},
  publisher = {Guilford Press},
  year = {2022}
}

@book{book_ed_only,
  editor = {Stensaker, Bjorn and Harvey, Lee},
  title = {Accountability in Higher Education: Global Perspectives},
  edition = {2},
  publisher = {Routledge},
  year = {2023}
}

@book{book_trans,
  author = {Kahneman, Daniel},
  translator = {胡晓姣 and 李爱民},
  title = {Thinking, Fast and Slow},
  publisher = mit,
  year = {2011}
}

@incollection{incoll,
  author = {Stake, Robert E. and Cisneros-Cohernour, Edith J.},
  editor = {Guba, Egon G. and Lincoln, Yvonna S.},
  title = {Situational evaluation of teaching on campus},
  booktitle = {New Directions for Teaching and Learning},
  pages = {51--72},
  address = {San Francisco},
  publisher = {Jossey-Bass},
  year = {2000}
}

@inproceedings{inproc,
  author = {Lin, Wei and Zhang, Qiang and van Berg, Jan},
  title = {Evaluating Structured Formatting Pipelines},
  booktitle = {Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics},
  pages = {1120--1134},
  address = {Bangkok},
  publisher = {Association for Computational Linguistics},
  year = {2024}
}

@techreport{techrep,
  author = {{Higher Education Evaluation and Accreditation Council of Taiwan}},
  title = {Third Cycle Institutional Accreditation Handbook},
  type = {Technical Report},
  number = {HEEACT-TR-2023--04},
  institution = {HEEACT},
  address = {Taipei},
  url = {https://example.org/heeact-tr--2023},
  year = {2023}
}

@phdthesis{phd,
  author = {Chen, Yi-Ling},
  title = {Algorithmic Fairness in Automated Scoring Systems},
  school = {National Taiwan University},
  address = {Taipei},
  year = {2024}
}

@mastersthesis{master,
  author = {Smith, Jr., John},
  title = {Deterministic Document Compilation},
  school = {Stanford University},
  type = {Master's thesis},
  year = {2023}
}

@misc{web_howpub_url,
  author = {{Ministry of Education}},
  title = {Guidelines on Generative {AI} Use in Universities},
  howpublished = {\url{https://example.edu/ai-guidelines~v2}},
  year = {2025},
  urldate = {2026-10-15}
}

@misc{web_platform_text,
  author = {{教育部}},
  title = {大學、技專校院各系所註冊率},
  howpublished = {政府資料開放平臺},
  url = {https://data.gov.tw/dataset/26228},
  year = {2026},
  urldate = {2026-11-01}
}

@misc{arxiv_preprint,
  author = {Zhang, Wei and Li, Ming},
  title = {Scaling Laws for Synthetic Benchmarks},
  eprint = {2501.01234},
  archivePrefix = {arXiv},
  year = {2025}
}

@online{online_entry,
  author = {Doe, Jane},
  title = {Structured Markdown Workflows},
  organization = {Open Publishing Collective},
  url = {https://example.com/workflow},
  date = {2025-06-15},
  urldate = {2026-11-10}
}

@software{software_entry,
  author = {{Open Science Lab}},
  title = {md-to-word},
  version = {3.5.0--rc1},
  organization = {GitHub},
  url = {https://github.com/ls-open/md-to-word},
  year = {2026}
}

@dataset{dataset_entry,
  author = {Wang, Lei},
  title = {Academic Formatting Corpus 2025},
  publisher = {Zenodo},
  doi = {10.5281/zenodo.1234567},
  year = {2025}
}

@patent{patent_entry,
  author = {Li, Hua},
  title = {Document Style Verification Engine},
  number = {CN114000001A},
  location = {China},
  date = {2024-05-20}
}

@standard{standard_entry,
  author = {{中华人民共和国国家质量监督检验检疫总局}},
  title = {信息与文献 参考文献著录规则},
  number = {GB/T 7714--2015},
  address = {北京},
  publisher = {中国标准出版社},
  year = {2015}
}

@misc{no_author_entry,
  title = {Editorial Note on Reproducibility},
  journal = {Nature Methods},
  volume = {20},
  pages = {1--2},
  year = {2023}
}

@misc{no_year_entry,
  author = {{World Health Organization}},
  title = {Global Health Data Standards},
  url = {https://www.who.int/standards}
}

@article{disambig_same_1,
  author = {Wang, Tao and Chen, Bo},
  title = {First Paper in 2024},
  journal = {J. Testing},
  year = {2024}
}

@article{disambig_same_2,
  author = {Wang, Tao and Chen, Bo},
  title = {Second Paper in 2024},
  journal = {J. Testing},
  year = {2024}
}

@article{disambig_given_1,
  author = {Li, Ming},
  title = {Given Name Study One},
  journal = {J. Testing},
  year = {2022}
}

@article{disambig_given_2,
  author = {Li, Mei},
  title = {Given Name Study Two},
  journal = {J. Testing},
  year = {2023}
}

@article{corp_comma_and,
  author = {{Procter & Gamble} and {Food and Agriculture Organization, UN}},
  title = {Supply Chain Sustainability Report},
  journal = {Global Operations},
  year = {2024}
}

@inbook{inbook_chap,
  author = {Knuth, Donald E.},
  title = {Fundamental Algorithms},
  booktitle = {The Art of Computer Programming},
  chapter = {3},
  pages = {1--40},
  publisher = {Addison-Wesley},
  address = {Reading, MA},
  year = {1997}
}

@proceedings{proc_ed,
  editor = {Vaswani, Ashish and Brown, Tom},
  title = {Advances in Neural Information Processing Systems 36},
  volume = {36},
  publisher = {Curran Associates},
  address = {New Orleans},
  year = {2023}
}

@booklet{booklet_entry,
  author = {Torvalds, Linus},
  title = {Git User Manual},
  howpublished = {Self-published},
  year = {2020}
}

@unpublished{unpub_entry,
  author = {Chen, Bo},
  title = {Towards Zero-Defect Document Compilation},
  note = {Manuscript in preparation},
  year = {2026}
}

@manual{manual_entry,
  title = {Python Language Reference},
  organization = {Python Software Foundation},
  edition = {3.12},
  year = {2024}
}

@phdthesis{phd_zh,
  author = {{张三}},
  title = {面向复杂版式的自动化排版研究},
  school = {清华大学},
  address = {北京},
  type = {博士学位论文},
  year = {2024}
}

@phdthesis{phd_num,
  author = {Taylor, Alex},
  title = {Scalable Citation Resolution},
  school = {MIT},
  number = {AAI-1234567},
  year = {2022}
}

@patent{patent_holder,
  holder = {{Huawei Technologies Co., Ltd.}},
  title = {Adaptive Layout Method},
  number = {CN115000002B},
  authority = {CNIPA},
  date = {2025-03-10}
}

@misc{misc_plain,
  title = {Internal Design Memorandum},
  howpublished = {Personal communication},
  year = {2025}
}

@article{accents_entry,
  author = {M\"{u}ller, Hans and Dvo{\v r}\'{a}k, Anton\'{\i}n and S{\o}rensen, Erik},
  title = {Caf\'{e} Systems and Na\"{i}ve Parsing},
  journal = {Nordic Computing},
  year = {2024}
}
"""


def _style_lang(style: str) -> str:
    return "zh" if ("chinese" in style or "china" in style) else "en"


def _cite_str(eng: CitationEngine, items: list[tuple], narrative: bool = False) -> str:
    return "".join(t for t, _ in eng.cite(items, narrative=narrative))


def _bib_map(eng: CitationEngine) -> dict[str, str]:
    return {k: "".join(t for t, _ in segs) for k, segs in eng.bibliography_entries()}


@pytest.mark.parametrize("style", ALL_STYLES)
def test_all_bundled_styles_render_full_heterogeneous_matrix(style: str) -> None:
    """29 份内置样式在 36 条异构文献矩阵上全部可渲染，且不漏条目、不泄露未解码实体或报错标记。"""
    entries = parse_bibtex(MATRIX_BIB)
    keys = [e["id"] for e in entries]
    assert len(keys) == 36

    eng = CitationEngine(MATRIX_BIB, CSL_DIR / style, lang=_style_lang(style))
    eng.reserve(keys)
    for k in keys:
        rendered = _cite_str(eng, [(k, "")])
        assert rendered.strip(), f"{style} empty inline citation for {k}"

    multi = _cite_str(eng, [("art_en", "15"), ("art_zh", ""), ("book_auth", "")])
    assert multi.strip(), f"{style} empty multi-citation"
    narr = _cite_str(eng, [("art_en", "")], narrative=True)
    assert narr.strip(), f"{style} empty narrative citation"

    bibs = eng.bibliography_entries()
    assert len(bibs) == len(keys), f"{style} expected {len(keys)} entries, got {len(bibs)}"
    for k, segs in bibs:
        text = "".join(t for t, _ in segs)
        assert text.strip(), f"{style} blank bibliography entry for {k}"
        for bad_tok in ("None", "&amp;", "&lt;", "&gt;", "citeproc", "VariableError"):
            assert bad_tok not in text, f"{style} [{k}] leaked {bad_tok!r}: {text}"


def test_bibtex_accents_and_edge_field_mappings() -> None:
    """LaTeX 重音、`@misc` 期刊回流、`@patent` holder/authority、`@inbook` 章节、`@booklet` 发布方。"""
    by_id = {e["id"]: e for e in parse_bibtex(MATRIX_BIB)}

    acc = by_id["accents_entry"]
    assert [a["family"] for a in acc["author"]] == ["Müller", "Dvořák", "Sørensen"]
    assert [a["given"] for a in acc["author"]] == ["Hans", "Antonín", "Erik"]
    assert acc["title"] == "Café Systems and Naïve Parsing"

    # 更多重音变体：\c{c} / {\c c} / \H{o} / {\ss} / {\L}，同时不破坏 \url
    extra = parse_bibtex(
        r"""
        @article{x,
          author = {Fran\c{c}ois, Jean and Erd\H{o}s, P\'al and {\L}ukasz, Jan and Gro{\ss}, Max},
          title = {{\c C}a va},
          journal = {J},
          year = {2020}
        }
        """
    )[0]
    assert [a["family"] for a in extra["author"]] == ["François", "Erdős", "Łukasz", "Groß"]
    assert extra["author"][1]["given"] == "Pál"
    assert extra["title"] == "Ça va"

    assert by_id["no_author_entry"]["type"] == "article-journal"
    assert by_id["inbook_chap"]["chapter-number"] == "3"
    assert by_id["booklet_entry"]["publisher"] == "Self-published"
    assert by_id["misc_plain"]["publisher"] == "Personal communication"
    with_both = parse_bibtex(
        "@misc{m, title={T}, institution={Org}, howpublished={Special note}, year={2025}}"
    )[0]
    assert with_both["publisher"] == "Org"
    assert with_both["note"] == "Special note"
    assert by_id["patent_holder"]["author"] == [{"literal": "Huawei Technologies Co., Ltd."}]
    assert by_id["patent_holder"]["authority"] == "CNIPA"


def test_gb7714_matrix_types_and_chinese_ordinals() -> None:
    """GB/T 7714-2015 与 GB/T 7714-2025：全类型文献标志码、中文序数版次 (`3 版`)、无幽灵 `V.`。"""
    keys = [e["id"] for e in parse_bibtex(MATRIX_BIB)]

    for style in ("chinese-gb7714-2015-numeric.csl", "china-national-standard-gb-t-7714-2025-numeric.csl"):
        eng = CitationEngine(MATRIX_BIB, CSL_DIR / style, lang="zh")
        eng.reserve(keys)
        for k in keys:
            _cite_str(eng, [(k, "")])
        bib = _bib_map(eng)

        assert "3 版" in bib["book_auth"] and "3rd 版" not in bib["book_auth"]
        assert "2 版" in bib["book_ed_only"] and "2nd 版" not in bib["book_ed_only"]
        assert "Self-published" in bib["booklet_entry"]
        assert "[D]" in bib["phd_zh"] and "清华大学" in bib["phd_zh"]
        assert "AAI-1234567" in bib["phd_num"]
        assert "[P]" in bib["patent_holder"] and "huawei technologies" in bib["patent_holder"].lower()
        assert "MÜLLER" in bib["accents_entry"] or "Müller" in bib["accents_entry"]
        assert "V." not in bib["book_auth"] and "V." not in bib["art_en"]
        assert _cite_str(eng, [("disambig_same_1", ""), ("disambig_same_2", "")]) == "[22,23]"

    eng_2015 = CitationEngine(MATRIX_BIB, CSL_DIR / "chinese-gb7714-2015-numeric.csl", lang="zh")
    eng_2015.reserve(keys)
    for k in keys:
        _cite_str(eng_2015, [(k, "")])
    bib15 = _bib_map(eng_2015)
    assert "[J/OL]" in bib15["art_en"]
    assert "[CP/OL]" in bib15["software_entry"]
    assert "[DS/OL]" in bib15["dataset_entry"]
    assert "[S]" in bib15["standard_entry"]
    assert "Personal communication" in bib15["misc_plain"]

    eng_2025 = CitationEngine(MATRIX_BIB, CSL_DIR / "china-national-standard-gb-t-7714-2025-numeric.csl", lang="zh")
    eng_2025.reserve(keys)
    for k in keys:
        _cite_str(eng_2025, [(k, "")])
    bib25 = _bib_map(eng_2025)
    assert "[PP/OL]" in bib25["arxiv_preprint"]
    assert "Personal communication" in bib25["misc_plain"]


def test_apa_thesis_no_ghost_group_and_version_singular() -> None:
    """APA 7th：缺 `number` 的学位论文不出幽灵 `(Publication)`、`Version` 不误变复数、`Eds.` 首字母大写。"""
    keys = [e["id"] for e in parse_bibtex(MATRIX_BIB)]
    apa = CitationEngine(MATRIX_BIB, CSL_DIR / "apa.csl", lang="en")
    apa.reserve(keys)
    for k in keys:
        _cite_str(apa, [(k, "")])
    bib = _bib_map(apa)

    assert bib["phd"] == (
        "Chen, Y.-L. (2024). Algorithmic Fairness in Automated Scoring Systems "
        "[Doctoral dissertation]. National Taiwan University."
    )
    assert "(Publication)" not in bib["phd"]
    assert "(Publication AAI-1234567)" in bib["phd_num"]
    assert bib["phd_zh"].endswith("[博士学位论文]. 清华大学.")
    assert "(Version 3.5.0--rc1)" in bib["software_entry"]
    assert "Versions" not in bib["software_entry"]
    assert "(3rd ed.)" in bib["book_auth"]
    assert "(Eds.)." in bib["proc_ed"] and bib["proc_ed"].count("Vaswani") == 1
    assert "Venkatesh, V., & Davis, F. D." in bib["art_en"]
    assert bib["misc_plain"] == "Internal Design Memorandum. (2025). Personal communication."
    assert _cite_str(apa, [("no_year_entry", "")], narrative=True) == "World Health Organization (n.d.)"


def test_chicago_and_mla_preserve_full_given_names() -> None:
    """Chicago 与 MLA 的 `<name initialize="false">` 必须保留作者全名，不跟着顶层 `initialize-with` 缩成首字母。"""
    keys = [e["id"] for e in parse_bibtex(MATRIX_BIB)]

    chicago = CitationEngine(MATRIX_BIB, CSL_DIR / "chicago-author-date.csl", lang="en")
    chicago.reserve(keys)
    for k in keys:
        _cite_str(chicago, [(k, "")])
    cbib = _bib_map(chicago)
    assert cbib["art_en"].startswith("Venkatesh, Viswanath, and Fred D. Davis. 2021.")
    assert cbib["book_auth"].startswith("Hayes, Andrew F. 2022.")
    assert "Chap. 3 in The Art of Computer Programming." in cbib["inbook_chap"]
    assert "GitHub, released." in cbib["software_entry"]
    assert _cite_str(chicago, [("no_year_entry", "")], narrative=True) == "World Health Organization (n.d.)"

    mla = CitationEngine(MATRIX_BIB, CSL_DIR / "modern-language-association.csl", lang="en")
    mla.reserve(keys)
    for k in keys:
        _cite_str(mla, [(k, "")])
    mbib = _bib_map(mla)
    assert mbib["art_en"].startswith("Venkatesh, Viswanath, and Fred D. Davis.")
    assert mbib["book_auth"].startswith("Hayes, Andrew F.")
    assert "pp. 1–40." in mbib["inbook_chap"]
    assert "Version 3.5.0--rc1" in mbib["software_entry"]


def test_mla_disambiguate_if_only_triggers_on_colliding_cites() -> None:
    """MLA 仅在真实撞车条目上激活 `<if disambiguate="true">` 补题名，未撞车条目不凭空附题名。"""
    keys = [e["id"] for e in parse_bibtex(MATRIX_BIB)]
    mla = CitationEngine(MATRIX_BIB, CSL_DIR / "modern-language-association.csl", lang="en")
    mla.reserve(keys)

    assert _cite_str(mla, [("art_en", "")]) == "(Venkatesh and Davis)"
    assert _cite_str(mla, [("disambig_same_1", "")]) == "(Wang and Chen, “First Paper in 2024”)"
    assert _cite_str(mla, [("disambig_same_2", "")]) == "(Wang and Chen, “Second Paper in 2024”)"


def test_per_initial_subgroup_givenname_disambiguation() -> None:
    """同一姓氏按首字母分组消歧：首字母唯一只补首字母 (`H. Li`)，首字母相同展全名 (`Ming Li` / `Mei Li`)。"""
    bib = """
@article{li_ming, author={Li, Ming}, title={Study One}, journal={J}, year={2022}}
@article{li_mei, author={Li, Mei}, title={Study Two}, journal={J}, year={2023}}
@article{li_hao, author={Li, Hao}, title={Study Three}, journal={J}, year={2024}}
"""
    keys = ["li_ming", "li_mei", "li_hao"]

    chicago = CitationEngine(bib, CSL_DIR / "chicago-author-date.csl", lang="en")
    chicago.reserve(keys)
    assert _cite_str(chicago, [("li_hao", "")]) == "(H. Li 2024)"
    assert _cite_str(chicago, [("li_ming", "")]) == "(Ming Li 2022)"
    assert _cite_str(chicago, [("li_mei", "")]) == "(Mei Li 2023)"

    mla = CitationEngine(bib, CSL_DIR / "modern-language-association.csl", lang="en")
    mla.reserve(keys)
    assert _cite_str(mla, [("li_hao", "")]) == "(H. Li)"
    assert _cite_str(mla, [("li_ming", "")]) == "(Ming Li)"
    assert _cite_str(mla, [("li_mei", "")]) == "(Mei Li)"

    # by-cite 规则（Harvard）：年份不同本就不撞车，各自保持短形式
    harvard = CitationEngine(bib, CSL_DIR / "harvard-cite-them-right.csl", lang="en")
    harvard.reserve(keys)
    assert _cite_str(harvard, [("li_ming", "")]) == "(Li, 2022)"
    assert _cite_str(harvard, [("li_mei", "")]) == "(Li, 2023)"
    assert _cite_str(harvard, [("li_hao", "")]) == "(Li, 2024)"


def test_page_range_minimal_and_minimal_two_digit_boundaries() -> None:
    """`minimal` / `minimal-two` 对不同位数页码区间不得错截（如 `1–40` 变 `1–0` 或 `11–112` 变 `11–2`）。"""
    bib = """
@article{p1_40, author={A, One}, title={T1}, journal={J}, volume={1}, pages={1--40}, year={2020}}
@article{p11_112, author={B, Two}, title={T2}, journal={J}, volume={1}, pages={11--112}, year={2021}}
@article{p101_105, author={C, Three}, title={T3}, journal={J}, volume={1}, pages={101--105}, year={2022}}
"""
    keys = ["p1_40", "p11_112", "p101_105"]

    mla = CitationEngine(bib, CSL_DIR / "modern-language-association.csl", lang="en")
    mla.reserve(keys)
    for k in keys:
        _cite_str(mla, [(k, "")])
    mbib = _bib_map(mla)
    assert "pp. 1–40" in mbib["p1_40"]
    assert "pp. 11–112" in mbib["p11_112"]
    assert "pp. 101–05" in mbib["p101_105"]

    lancet = CitationEngine(bib, CSL_DIR / "the-lancet.csl", lang="en")
    lancet.reserve(keys)
    for k in keys:
        _cite_str(lancet, [(k, "")])
    lbib = _bib_map(lancet)
    assert "1–40." in lbib["p1_40"]
    assert "11–112." in lbib["p11_112"]
    assert "101–5." in lbib["p101_105"]

    ieee = CitationEngine(bib, CSL_DIR / "ieee.csl", lang="en")
    ieee.reserve(keys)
    for k in keys:
        _cite_str(ieee, [(k, "")])
    ibib = _bib_map(ieee)
    assert "pp. 101–105" in ibib["p101_105"]
