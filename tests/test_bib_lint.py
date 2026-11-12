""".bib 体检器：报的问题必须是**导出时真会出事**的，用词要指得出位置。

上一版这个脚本自己写了一套 BibTeX 解析，只认 `@type{`——`@article(`（括号式）的库被它
判成「文件中未发现任何条目」。所以这里第一条测试就盯着它必须走导出器那套解析器。

另一半测的是**不要误报**：干净的库要一条提示都不出，否则用户很快就会无视它。
"""

from __future__ import annotations

from pathlib import Path

from md_to_word.utils.bib_lint import lint_bibtex, lint_bibtex_file

REPO_ROOT = Path(__file__).resolve().parents[1]

CLEAN = """\
@article{smith2020,
  author = {Smith, John and Doe, Jane},
  title = {A Study of Things},
  journal = {Journal of Things},
  year = {2020},
}
"""


def _levels(findings) -> list[str]:
    return [f.level for f in findings]


def test_a_clean_library_produces_no_noise() -> None:
    """一条提示都不该有：体检器一旦爱报，用户就会学会无视它。"""
    assert lint_bibtex(CLEAN) == []


def test_duplicate_keys_are_errors() -> None:
    """重复键不报错的话，两条引文会悄悄指向同一条文献。"""
    text = CLEAN + CLEAN
    findings = lint_bibtex(text)
    assert _levels(findings) == ["error"]
    assert "重复" in findings[0].message


def test_missing_title_is_an_error() -> None:
    """没有 title 的条目在文献表里是一行空白，必须拦。"""
    findings = lint_bibtex(
        "@article{notitle,\n  author = {Smith, John},\n  journal = {J},\n  year = {2020},\n}\n"
    )
    assert [f.level for f in findings] == ["error"]
    assert "title" in findings[0].message


def test_comma_separated_authors_are_flagged() -> None:
    """`Zhang San, Li Si, Wang Wu` 会被 BibTeX 当成一个人，这是最常见的坑。"""
    findings = lint_bibtex(
        "@article{cn2020,\n  author = {张三, 李四, 王五},\n"
        "  title = {标题},\n  journal = {期刊},\n  year = {2020},\n}\n"
    )
    assert any("and" in f.message for f in findings), findings


def test_missing_required_field_is_a_warning() -> None:
    """缺刊名照样导得出来，只是那一项空着——提示而不是错误。"""
    findings = lint_bibtex(
        "@article{nojournal,\n  author = {Smith, John},\n"
        "  title = {A Study},\n  year = {2020},\n}\n"
    )
    assert [f.level for f in findings] == ["warning"]
    assert "journal" in findings[0].message


def test_unprotected_acronyms_are_flagged() -> None:
    """APA 一类句首大写样式会把 DNA 转成 dna，除非加大括号。"""
    findings = lint_bibtex(
        "@article{dna2020,\n  author = {Smith, John},\n"
        "  title = {Sequencing DNA with BERT},\n  journal = {J},\n  year = {2020},\n}\n"
    )
    assert any("{DNA}" in f.message for f in findings), findings


def test_already_protected_acronyms_are_not_flagged() -> None:
    findings = lint_bibtex(
        "@article{dna2020,\n  author = {Smith, John},\n"
        "  title = {Sequencing {DNA} with {BERT}},\n  journal = {J},\n  year = {2020},\n}\n"
    )
    assert findings == []


def test_parenthesised_entries_are_read() -> None:
    """`@article(key, ...)` 是合法的 BibTeX 写法。上一版体检器在这里判定「没有条目」。"""
    findings = lint_bibtex(
        "@article(paren2020,\n  author = {Smith, John},\n"
        "  title = {A Study},\n  journal = {J},\n  year = {2020},\n)\n"
    )
    assert findings == [], findings


def test_findings_point_at_the_right_line() -> None:
    """行号要能直接跳过去；重复键时两条各指各的行。"""
    # CLEAN 自身以换行结尾，中间再空一行，第二条从第 8 行开始
    findings = lint_bibtex(CLEAN + "\n" + CLEAN)
    assert findings[0].line == 8, findings[0]


def test_the_sample_libraries_are_clean() -> None:
    """仓库自带的样例是给人抄的，不该自己先被体检器挑出错。"""
    for bib in (
        REPO_ROOT / "demo" / "01_chinese_thesis" / "references.bib",
        REPO_ROOT / "demo" / "02_modern_report" / "references.bib",
        REPO_ROOT / "demo" / "03_english_paper" / "refs.bib",
    ):
        findings, failure = lint_bibtex_file(bib)
        assert failure is None, f"{bib} 读不了：{failure}"
        errors = [f for f in findings if f.level == "error"]
        assert not errors, f"{bib.name} 有错误：{[f.format() for f in errors]}"


def test_an_empty_library_says_so_instead_of_passing_silently() -> None:
    """读不出条目却一声不响，和「体检通过」长得一模一样。"""
    findings = lint_bibtex("% 只有注释\n")
    assert [f.level for f in findings] == ["warning"]
    assert "条目" in findings[0].message


def test_an_unreadable_file_reports_a_reason_instead_of_raising() -> None:
    findings, failure = lint_bibtex_file(REPO_ROOT / "no-such-file.bib")
    assert findings == []
    assert failure
