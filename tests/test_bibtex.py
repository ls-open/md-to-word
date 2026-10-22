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
