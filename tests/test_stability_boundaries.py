"""这一版补上的边界：每个用例都对应一次审查里「导出成功但结果不对/输入被毁」。

这些不是排版细节，而是输入输出边界、跨请求状态、以及「预检绿、导出红」的具体路径。
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.enum.section import WD_SECTION

from md_to_word.cli import main
from md_to_word.model.reader import MarkdownError, read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline, run_validation
from md_to_word.spec.parser import parse_format
from md_to_word.spec.serializer import serialize_format
from md_to_word.template.builder import build_template
from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "src/md_to_word/presets/zh-academic.txt"
PNG = REPO_ROOT / "demo/00_quickstart/page-1.png"


def _md(tmp_path: Path, text: str, name: str = "m.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _two_section_docx(path: Path) -> None:
    doc = Document()
    doc.add_paragraph("Cover")
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_paragraph("Body")
    doc.save(path)


# ── 输入/输出边界 ──────────────────────────────────────────────────────


def test_output_must_be_docx_and_never_overwrites_an_existing_pdf(tmp_path: Path) -> None:
    manuscript = _md(tmp_path, "# 一\n\n正文。\n")
    old_pdf = tmp_path / "out.pdf"
    old_pdf.write_bytes(b"REAL-PDF")
    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=old_pdf, preset="zh-academic")
    )
    assert result.returncode == 1
    assert any(".docx" in error for error in result.errors), result.errors
    assert old_pdf.read_bytes() == b"REAL-PDF"


def test_output_cannot_be_the_base_template(tmp_path: Path) -> None:
    base = tmp_path / "paper.docx"
    _two_section_docx(base)
    before = base.read_bytes()
    manuscript = _md(tmp_path, "# Introduction\n\nBody.\n", "paper.md")
    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript,
            base_template=base,
            cover_sections=1,
            preset="en-nature",
        )
    )
    assert result.returncode == 1
    assert base.read_bytes() == before, "底模被本次导出覆盖了"


def test_stale_pdf_is_reported_and_old_file_kept(tmp_path: Path, monkeypatch) -> None:
    import md_to_word.pipeline as pipeline

    manuscript = _md(tmp_path, "# 一\n\n正文。\n")
    out = tmp_path / "m.docx"
    old_pdf = tmp_path / "m.pdf"
    old_pdf.write_bytes(b"OLD-PDF")
    monkeypatch.setattr(pipeline, "render_pdf_via_word", lambda *_a, **_k: (False, "no-word"))
    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript, output_path=out, preset="zh-academic", make_pdf=True
        )
    )
    assert result.returncode == 3
    assert any("pipeline.stale_pdf" == d.code for d in result.diagnostics), result.diagnostics
    assert old_pdf.read_bytes() == b"OLD-PDF"


def test_pdf_is_staged_then_replaced(tmp_path: Path, monkeypatch) -> None:
    import md_to_word.pipeline as pipeline

    manuscript = _md(tmp_path, "# 一\n\n正文。\n")
    out = tmp_path / "m.docx"

    def fake_render(_docx, pdf_path):
        Path(pdf_path).write_bytes(b"NEW-PDF")
        return True, None

    monkeypatch.setattr(pipeline, "render_pdf_via_word", fake_render)
    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript, output_path=out, preset="zh-academic", make_pdf=True
        )
    )
    assert result.returncode == 0
    assert result.output_pdf == tmp_path / "m.pdf"
    assert (tmp_path / "m.pdf").read_bytes() == b"NEW-PDF"


# ── 确定性与公开 API ───────────────────────────────────────────────────


def test_bookmarks_are_deterministic_across_exports_in_one_process(tmp_path: Path) -> None:
    (tmp_path / "r.bib").write_text(
        "@article{a&b, author={A B}, title={T}, journal={J}, year={2020}}\n",
        encoding="utf-8",
    )
    manuscript = _md(
        tmp_path,
        "---\nbibliography: r.bib\ncsl: apa.csl\n---\n\n# 一\n\n见 [@a&b]。\n",
    )
    blobs = []
    for index in range(2):
        out = tmp_path / f"o{index}.docx"
        result = run_export_pipeline(
            ExportOptions(input_path=manuscript, output_path=out, preset="zh-academic")
        )
        assert result.ok, result.errors
        blobs.append(out.read_bytes())
    assert blobs[0] == blobs[1], "同一进程两次导出的字节不同"


def test_serializer_round_trips_every_field_and_template_keeps_page_decor(tmp_path: Path) -> None:
    spec = parse_format(PRESET.read_text(encoding="utf-8"))
    again = parse_format(serialize_format(spec))
    assert again == spec, "serialize_format → parse_format 改变了规约"

    out = tmp_path / "t.docx"
    build_template(spec, out)
    with zipfile.ZipFile(out) as z:
        doc = z.read("word/document.xml").decode("utf-8")
        assert "pgNumType" in doc, "页码格式丢了"
        assert any(n.startswith("word/footer") for n in z.namelist()), "页脚部件丢了"


# ── 引用块与脚注 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("line", "code"),
    [
        ("> %% 摘要 引用里的样式行", "reader.quote_style_unsupported"),
        ("> ## 引用里的标题", "reader.quote_unsupported"),
        ("> [^1]: 引用里的脚注", "reader.quote_footnote_unsupported"),
    ],
)
def test_quote_blocks_reject_what_the_writer_cannot_hold(line: str, code: str) -> None:
    with pytest.raises(MarkdownError) as exc:
        read_markdown(f"# 一\n\n{line}\n")
    assert exc.value.code == code


def test_validate_only_catches_writer_level_failures(tmp_path: Path, capsys) -> None:
    manuscript = _md(tmp_path, "# 一\n\n> ## 引用里的标题\n")
    code = main([str(manuscript), "--preset", "zh-academic", "--validate-only", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 == payload["returncode"]
    assert payload["errors"], payload


def test_footnote_duplicates_unused_and_multiline(tmp_path: Path) -> None:
    duplicate = _md(
        tmp_path, "# 一\n\n正文[^a]。\n\n[^a]: 第一条。\n[^a]: 第二条。\n", "dup.md"
    )
    report = validate_manuscript(duplicate, lang="zh")
    assert not report.valid
    assert any(d.code == "gate.footnote.duplicate" for d in report.diagnostics)

    unused = _md(tmp_path, "# 一\n\n正文。\n\n[^a]: 没人引用。\n", "unused.md")
    report = validate_manuscript(unused, lang="zh")
    assert report.valid
    assert any(d.code == "gate.footnote.unused" for d in report.diagnostics)

    multiline = _md(tmp_path, "# 一\n\n正文[^a]。\n\n[^a]: 第一行\n    续行。\n", "multi.md")
    report = validate_manuscript(multiline, lang="zh")
    assert not report.valid
    assert any(d.code == "gate.footnote.multiline" for d in report.diagnostics)


# ── 稿件内容与路径 ─────────────────────────────────────────────────────


@pytest.mark.parametrize("text", ["", "   \n\n", "<!-- 只有注释 -->\n"])
def test_empty_manuscripts_are_rejected(tmp_path: Path, text: str) -> None:
    manuscript = _md(tmp_path, text)
    report = validate_manuscript(manuscript, lang="zh")
    assert not report.valid
    assert any(d.code == "gate.manuscript.empty" for d in report.diagnostics)


def test_image_paths_with_parentheses_and_spaces_work(tmp_path: Path) -> None:
    image = tmp_path / "Screen Shot (2).png"
    image.write_bytes(PNG.read_bytes())
    manuscript = _md(tmp_path, "# 一\n\n![](Screen Shot (2).png)\n")
    report = validate_manuscript(manuscript, lang="zh")
    assert report.valid, report.errors

    out = tmp_path / "o.docx"
    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=out, preset="zh-academic")
    )
    assert result.ok, result.errors
    with zipfile.ZipFile(out) as z:
        assert "<w:drawing" in z.read("word/document.xml").decode("utf-8")
        assert any(n.startswith("word/media/") for n in z.namelist())


def test_yaml_errors_carry_a_line_and_non_mapping_is_reported(tmp_path: Path) -> None:
    broken = _md(tmp_path, "---\ntitle: [unclosed\n---\n\n# 一\n\n正文。\n", "broken.md")
    report = validate_manuscript(broken, lang="zh")
    assert not report.valid
    assert any(d.code == "gate.yaml.parse_failed" and d.line for d in report.diagnostics)

    listed = _md(tmp_path, "---\n- a\n- b\n---\n\n# 一\n\n正文。\n", "list.md")
    report = validate_manuscript(listed, lang="zh")
    assert not report.valid
    assert any(d.code == "gate.yaml.not_mapping" for d in report.diagnostics)


def test_duplicate_bibliography_keys_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "r.bib").write_text(
        "@article{dup, author={A B}, title={First}, journal={J}, year={2020}}\n"
        "@article{dup, author={C D}, title={Second}, journal={J}, year={2021}}\n",
        encoding="utf-8",
    )
    manuscript = _md(
        tmp_path, "---\nbibliography: r.bib\n---\n\n# 一\n\n见 [@dup]。\n"
    )
    report = validate_manuscript(manuscript, lang="zh")
    assert not report.valid
    assert any("重复的引用键" in error for error in report.errors), report.errors


def test_format_proofing_language_wins_over_mixed_prose(tmp_path: Path) -> None:
    """英文稿里夹长中文引文：显式 en-nature 的 CSL 与前缀不能被正文判成中文。"""
    (tmp_path / "r.bib").write_text(
        "@article{smith2024, author={Smith, John}, title={T}, journal={J}, year={2024}}\n",
        encoding="utf-8",
    )
    manuscript = _md(
        tmp_path,
        "---\nbibliography: r.bib\n---\n\n# Introduction\n\nEnglish body. "
        + "中文引文" * 40
        + " See [@smith2024].\n\n$$E=mc^2$$ {#eq-a}\n\nSee @eq-a.\n",
    )
    out = tmp_path / "o.docx"
    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=out, preset="en-nature")
    )
    assert result.ok, result.errors
    assert result.doc_lang == "en"
    with zipfile.ZipFile(out) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    assert "Equation (1)" in xml
    assert "SMITH J" not in xml  # GB/T 的首字母缩写形式
    assert any(d.code == "pipeline.doc_lang_format" for d in result.diagnostics)


def test_cli_early_errors_follow_the_interface_language(tmp_path: Path, capsys) -> None:
    code = main([str(tmp_path / "nope.md")])
    stderr = capsys.readouterr().err
    assert code == 1
    assert "输入稿件不存在" in stderr, stderr
    assert "Input manuscript not found" not in stderr


def test_cut_flags_without_base_template_are_reported(tmp_path: Path) -> None:
    manuscript = _md(tmp_path, "# 一\n\n正文。\n")
    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript,
            output_path=tmp_path / "o.docx",
            preset="zh-academic",
            keep_until="版权使用授权书",
        )
    )
    assert result.ok
    assert any(d.code == "pipeline.cut_without_base" for d in result.diagnostics)


def test_template_errors_carry_the_missing_style_details(tmp_path: Path) -> None:
    fmt = tmp_path / "format.txt"
    fmt.write_text(
        "\n".join(
            line for line in PRESET.read_text(encoding="utf-8").splitlines()
            if not line.startswith("正文：")
        ),
        encoding="utf-8",
    )
    manuscript = _md(tmp_path, "# 一\n\n正文。\n")
    result = run_validation(
        ExportOptions(input_path=manuscript, format_path=fmt, lang="zh")
    )
    assert result.returncode == 1
    joined = "\n".join(result.errors)
    assert "正文" in joined and "Body Text" in joined, joined


def test_validate_only_catches_unsupported_math(tmp_path: Path, capsys) -> None:
    manuscript = _md(tmp_path, "# 一\n\n$$\\xrightarrow{abc}$$\n")
    code = main([str(manuscript), "--preset", "zh-academic", "--validate-only", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1 == payload["returncode"]
    assert any("mpadded" in error for error in payload["errors"]), payload


def test_json_exposes_the_pdf_skip_reason(tmp_path: Path, monkeypatch, capsys) -> None:
    import md_to_word.pipeline as pipeline

    monkeypatch.setattr(pipeline, "render_pdf_via_word", lambda *_a, **_k: (False, "no-word"))
    manuscript = _md(tmp_path, "# 一\n\n正文。\n")
    code = main([
        str(manuscript), "--preset", "zh-academic", "--pdf", "--json",
        "-o", str(tmp_path / "o.docx"),
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 3 == payload["returncode"]
    assert payload["pdf"] is None
    assert payload["pdf_skip_reason"] == "no-word"


def test_a_word_failure_is_a_stable_code_with_details_in_the_log(
    tmp_path: Path, monkeypatch, caplog,
) -> None:
    """`pdf_skip_reason` 是给 Agent 分支用的契约字段，不能塞 AppleScript 的整段 stderr。"""
    import logging
    from types import SimpleNamespace

    from md_to_word.visual_qa import word_pdf

    monkeypatch.setattr(word_pdf, "can_render_word_pdf", lambda: (True, "ok"))
    monkeypatch.setattr(
        word_pdf.subprocess, "run",
        lambda *_a, **_k: SimpleNamespace(returncode=1, stdout="", stderr="AppleScript failed\nstack"),
    )
    with caplog.at_level(logging.WARNING):
        ok, reason = word_pdf.render_pdf_via_word(
            tmp_path / "x.docx", tmp_path / "x.pdf",
        )
    assert not ok and reason == "word-error"
    assert "AppleScript failed" in caplog.text


def test_traditional_manuscript_gets_a_preset_hint(tmp_path: Path) -> None:
    manuscript = _md(tmp_path, "# 緒論\n\n這是一份繁體中文稿件，討論學術排版與資料處理。\n")
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=tmp_path / "o.docx"
    ))
    assert result.ok, result.errors
    assert any(d.code == "pipeline.traditional_preset" for d in result.diagnostics)


def test_yaml_duplicate_keys_warn_with_both_lines(tmp_path: Path) -> None:
    manuscript = _md(
        tmp_path,
        "---\nbibliography: a.bib\nbibliography: b.bib\n---\n\n# 一\n\n正文。\n",
    )
    report = validate_manuscript(manuscript, lang="zh")
    hits = [d for d in report.diagnostics if d.code == "gate.yaml.duplicate_key"]
    assert hits and hits[0].line
    assert "bibliography" in hits[0].message


def test_init_never_tracebacks_on_an_unwritable_directory(tmp_path: Path, capsys) -> None:
    if sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0):
        pytest.skip("无法在 Windows/root 下制造不可写目录")
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o500)
    try:
        code = main(["init", str(locked)])
    finally:
        os.chmod(locked, 0o700)
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.out + captured.err
