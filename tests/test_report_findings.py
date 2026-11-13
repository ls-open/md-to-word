"""另一路实测报回来的四条：多行公式编号、误报连锁、BibTeX 重音、表头跨页重复。

共同的形状是「一处没写对，后面全跟着错」或「写了但没生效」：前者把真病因淹掉，
后者静默——都是产物上看不出来、退出码还是 0 的那一类。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.transform.bibtex import parse_bibtex
from md_to_word.utils.skill_utils import math_comment_issues, unbalanced_math_issues

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")


def _export(tmp_path: Path, body: str, name: str = "m.docx", spec: str | None = None):
    (tmp_path / "m.md").write_text(body, encoding="utf-8")
    options = dict(input_path=tmp_path / "m.md", output_path=tmp_path / name)
    if spec is not None:
        (tmp_path / "f.txt").write_text(spec, encoding="utf-8")
        options["format_path"] = tmp_path / "f.txt"
    return run_export_pipeline(ExportOptions(**options))


def _xml(tmp_path: Path, name: str = "m.docx") -> str:
    return zipfile.ZipFile(tmp_path / name).read("word/document.xml").decode("utf-8")


def test_multiline_equation_can_carry_its_label(tmp_path):
    """收尾行带 `{#eq-x}` 必须认——否则论文里任何需要编号的多行公式都做不出来。"""
    body = "---\n---\n\n# 一 引言\n\n$$\na+b\n$$ {#eq-1}\n\n见 @eq-1。\n"
    result = _export(tmp_path, body)
    assert result.returncode == 0, result.errors
    assert "式（1）" in _xml(tmp_path)


def test_unclosed_fence_does_not_cascade(tmp_path):
    """一个没闭合的 `$$` 只该报一条：后面每行的 `%` 都被当成公式内容，会刷一屏假错误。"""
    text = (
        "$$\n"
        "a+b\n"
        "\n"
        "| 指标 | 值 |\n"
        "|:--|:--|\n"
        "| 增长率 | -7.09% |\n"
        "\n"
        "%% 表题 **表 1** 测试\n"
        "\n"
        "正文里 71% 的样本。\n"
    )
    assert math_comment_issues(text) == []
    assert unbalanced_math_issues(text) == []
    # 围栏闭合时该报的照样报——上面的空列表不能是"这个函数什么都不报"换来的
    assert math_comment_issues("行内：$a%b$"), "闭合公式里的裸 `%` 仍然要报"


def test_bibtex_accents_are_decoded():
    """`{\\^o}` / `{\\"u}` / `{\\v r}` 是 BibTeX 的重音写法，要还原成 ô / ü / ř。"""
    entry = parse_bibtex(
        "@article{k, title={T}, year={2020}, journal={J},\n"
        ' author={T{\\^o}, A. and M{\\"u}ller, B. and Dvo{\\v r}{\\\'a}k, C. and {\\O}stergaard, D.}}\n'
    )[0]
    assert [a["family"] for a in entry["author"]] == ["Tô", "Müller", "Dvořák", "Østergaard"]


def test_header_row_repeats_across_pages(tmp_path):
    """预设里写了「跨页重复」，产物就得有 `w:tblHeader`——写在样式里 Word 不认。"""
    body = "---\n---\n\n# 一 引言\n\n| 指标 | 值 |\n|:--|:--|\n| 增长率 | 0.5 |\n"
    result = _export(tmp_path, body, spec=PRESET)
    assert result.returncode == 0, result.errors
    assert "<w:tblHeader/>" in _xml(tmp_path)


def test_bibtex_string_macro_is_expanded():
    """`@string{acm = "ACM Press"}` + `publisher = acm` → 展开成 ACM Press，不是印出 acm。"""
    entry = parse_bibtex(
        '@string{acm = "ACM Press"}\n'
        "@article{k, title={T}, year={2020}, journal={J}, publisher = acm}\n"
    )[0]
    assert entry["publisher"] == "ACM Press"


def test_bibtex_hash_concatenation():
    """`#` 是字符串拼接：不认它，后面整段会被吞进同一个值，整条条目跟着坏。"""
    entry = parse_bibtex(
        '@inproceedings{k, title={T}, year={2020}, publisher = "ACM" # " Press",\n'
        " booktitle={Proc}}\n"
    )[0]
    assert entry["publisher"] == "ACM Press"
    assert entry["container-title"] == "Proc"


def test_bibtex_quoted_value_stops_at_its_closing_quote():
    """引号包裹的值不能吞到条目末尾——开符与闭符是同一个字符时最易踩。"""
    entry = parse_bibtex(
        '@article{k, title="Quoted title", year="2020", journal="J. Test"}\n'
    )[0]
    assert entry["title"] == "Quoted title"
    assert entry["container-title"] == "J. Test"


def test_crossref_is_reported_not_silently_dropped(tmp_path):
    """`crossref` 的字段继承本工具不做：条目会缺项，所以必须说一句。"""
    (tmp_path / "lit.bib").write_text(
        "@inproceedings{child, title={A Paper}, crossref={parent}}\n"
        "@proceedings{parent, title={Proc}, publisher={ACM}, year={2020}}\n",
        encoding="utf-8",
    )
    body = "---\nbibliography: lit.bib\n---\n\n# 一 引言\n\n见 [@child]。\n"
    result = _export(tmp_path, body)
    assert result.returncode == 0, result.errors
    assert any("crossref" in w for w in result.warnings), result.warnings
