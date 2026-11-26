"""文献库与 CSL 的错误路径：每个失败都要有稳定诊断，而不是 traceback 或静默回退。

这些路径在代码里已经存在，但过去没有测试；缺一条，预检与导出就可能一个报错、
一个悄悄换默认样式，用户从成品上看不出来。
"""

from __future__ import annotations

from pathlib import Path

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt"

BIB = """
@article{alpha,
  author = {Alpha, Ann},
  title = {Alpha One},
  journal = {Journal of Tests},
  year = {2020},
}
"""


def _manuscript(tmp_path: Path, frontmatter: str, body: str = "# 一\n\n正文 [@alpha]。\n") -> Path:
    path = tmp_path / "paper.md"
    path.write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")
    return path


def _codes(report) -> set[str]:
    return {d.code for d in report.diagnostics}


def test_invalid_yaml_without_preflight_fails_explicitly(tmp_path: Path) -> None:
    """`--no-check` 跳过预检时，坏 YAML 不能静默退回默认 CSL。"""
    manuscript = tmp_path / "bad-yaml.md"
    manuscript.write_text("---\nbibliography: [unclosed\n---\n\n# 一\n\n正文。\n", encoding="utf-8")
    out = tmp_path / "bad-yaml.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=out, preset="zh-academic", check_md=False,
    ))
    assert result.returncode != 0
    assert "gate.yaml.parse_failed" in {d.code for d in result.diagnostics}, result.errors
    assert not out.exists()


def test_a_missing_bibliography_file_is_a_gate_error(tmp_path: Path) -> None:
    report = validate_manuscript(
        _manuscript(tmp_path, "bibliography: missing.bib"), spec_path=PRESET,
    )
    assert not report.valid
    assert "gate.bib.missing" in _codes(report), report.errors


def test_a_missing_csl_file_is_a_gate_error(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    report = validate_manuscript(
        _manuscript(tmp_path, "bibliography: refs.bib\ncsl: missing.csl"),
        spec_path=PRESET,
    )
    assert not report.valid
    assert "gate.csl.missing" in _codes(report), report.errors


def test_an_unknown_citation_key_is_a_gate_error(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    report = validate_manuscript(
        _manuscript(tmp_path, "bibliography: refs.bib", "# 一\n\n正文 [@beta]。\n"),
        spec_path=PRESET,
    )
    assert not report.valid
    assert "gate.citation.key" in _codes(report), report.errors


def test_an_empty_bibliography_with_a_citation_is_a_gate_error(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text("", encoding="utf-8")
    report = validate_manuscript(
        _manuscript(tmp_path, "bibliography: refs.bib"), spec_path=PRESET,
    )
    assert not report.valid
    assert "gate.bib.empty" in _codes(report), report.errors


def test_duplicate_bibliography_keys_are_reported(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(BIB + BIB, encoding="utf-8")
    report = validate_manuscript(
        _manuscript(tmp_path, "bibliography: refs.bib"), spec_path=PRESET,
    )
    assert not report.valid
    assert any("重复" in error or "duplicate" in error.lower() for error in report.errors)


def test_a_broken_csl_fails_the_export_not_falls_back_to_default(tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "bad.csl").write_text("<style>not closed", encoding="utf-8")
    manuscript = _manuscript(tmp_path, "bibliography: refs.bib\ncsl: bad.csl")
    out = tmp_path / "paper.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=out, format_path=PRESET,
    ))
    assert result.returncode != 0
    assert "pipeline.csl_error" in {d.code for d in result.diagnostics}, result.errors
    assert not out.exists()
