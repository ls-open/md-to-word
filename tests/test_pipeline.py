"""Unit and integration tests for md_to_word.pipeline."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from md_to_word.pipeline import ExportOptions, run_export_pipeline


def test_pipeline_export_zh_academic(tmp_path: Path):
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    for name in ("manuscript.md", "refs.bib"):
        shutil.copy(fixture_dir / name, tmp_path / name)

    output = tmp_path / "output_zh.docx"
    options = ExportOptions(
        input_path=tmp_path / "manuscript.md",
        output_path=output,
        preset="zh-academic",
    )
    result = run_export_pipeline(options)
    assert result.returncode == 0, f"Errors: {result.errors}"
    assert output.exists()
    assert output.stat().st_size > 5000


def test_pipeline_export_en_nature(tmp_path: Path):
    fixture_dir = Path(__file__).resolve().parent / "fixtures"
    for name in ("manuscript.md", "refs.bib"):
        shutil.copy(fixture_dir / name, tmp_path / name)

    output = tmp_path / "output_en.docx"
    options = ExportOptions(
        input_path=tmp_path / "manuscript.md",
        output_path=output,
        preset="en-nature",
    )
    result = run_export_pipeline(options)
    assert result.returncode == 0, f"Errors: {result.errors}"
    assert output.exists()
    assert output.stat().st_size > 5000


def test_pipeline_fails_on_invalid_manuscript(tmp_path: Path):
    bad_md = tmp_path / "bad.md"
    bad_md.write_text("""---
title: Broken
---

## 1. Wrong heading level
![](missing_image.png)
""", encoding="utf-8")

    output = tmp_path / "bad.docx"
    options = ExportOptions(
        input_path=bad_md,
        output_path=output,
        preset="zh-academic",
    )
    result = run_export_pipeline(options)
    assert result.returncode == 1
    assert any("图片文件不存在" in e for e in result.errors)


def _write_bib(directory: Path) -> None:
    (directory / "refs.bib").write_text(
        "@article{smith2024,\n  author={Smith, John},\n  title={A Study},\n"
        "  year={2024},\n  journal={Journal of Tests}\n}\n",
        encoding="utf-8",
    )


def _paragraph_texts(docx_path: Path) -> list[str]:
    from docx import Document

    return [p.text for p in Document(docx_path).paragraphs]


def test_default_csl_is_shared_by_both_writers(tmp_path: Path) -> None:
    """稿件没写 `csl:` 时，两条通道必须用同一个默认样式。

    否则同一份稿子换个后端就换出两种文献表——作者只会觉得"怎么又变了"。
    """
    _write_bib(tmp_path)
    (tmp_path / "m.md").write_text(
        '---\nbibliography: refs.bib\n---\n\n# 一 引言\n\n'
        "中文正文引用一次 [@smith2024] 即可。\n",
        encoding="utf-8",
    )
    native = tmp_path / "native.docx"
    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "m.md", output_path=native, check_md=False)
    )
    assert result.returncode == 0, result.errors
    text = "\n".join(_paragraph_texts(native))
    assert "[1]" in text, "中文稿未写 csl: 时应走 GB/T 数字制"
    assert "Smith, John. (2024)" not in text, "不该走作者-年份制"


def test_default_csl_follows_language(tmp_path: Path) -> None:
    """英文稿不写 `csl:` 走 APA：同一个机制，按字种选样式。"""
    from md_to_word.config import default_csl_path

    assert default_csl_path("这是一份中文稿件。" * 20).name == "chinese-gb7714-2015-numeric.csl"
    assert default_csl_path("This is an English manuscript. " * 20).name == "apa.csl"


def test_export_reminds_to_open_the_result(tmp_path: Path) -> None:
    """门禁全绿不等于版面合格。行高列宽、公式与题注的落版只能目视核对，
    因此每次成功导出都必须附一条核对提醒，使其成为交付流程的一环。"""
    (tmp_path / "m.md").write_text('---\n---\n\n# 一 引言\n\n正文。\n', encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors
    assert any("在 Word 中打开该文档并核对" in m for m in result.messages), result.messages


def test_image_paths_are_relative_to_the_manuscript(tmp_path: Path, monkeypatch) -> None:
    """稿里的图片路径相对稿件目录，不相对进程 cwd——否则换个目录调用就全是"图不存在"。"""
    work = tmp_path / "paper"
    (work / "figures").mkdir(parents=True)
    shutil.copy(
        Path(__file__).resolve().parents[1] / "demo/01_chinese_thesis/figures/qa_pipeline.png",
        work / "figures" / "x.png",
    )
    (work / "m.md").write_text(
        '---\n---\n\n![](figures/x.png){width=8cm}\n\n%% 图片题注 图 1 示意图\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)  # 站在别的目录调用
    result = run_export_pipeline(
        ExportOptions(input_path=work / "m.md", output_path=work / "o.docx", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors
    assert "drawing" in __import__("zipfile").ZipFile(work / "o.docx").read("word/document.xml").decode()


def test_bad_requirements_return_error_instead_of_exiting(tmp_path: Path) -> None:
    """作为库调用时，写错的格式要求必须返回错误码，不能 sys.exit 掉调用方的进程。"""
    (tmp_path / "m.md").write_text('---\n---\n\n# 一\n\n正文。\n', encoding="utf-8")
    (tmp_path / "req.txt").write_text("正文：宋体 小四\n", encoding="utf-8")

    try:
        result = run_export_pipeline(
            ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx",
                          requirements_path=tmp_path / "req.txt")
        )
    except SystemExit:  # pragma: no cover - 旧实现会走到这里
        pytest.fail("写错的 requirements 不应终止进程，应返回 returncode=1")

    assert result.returncode == 1
    assert any("格式要求" in e for e in result.errors), result.errors


def test_custom_template_must_be_single_section(tmp_path: Path) -> None:
    """第三方模板只取正文那一节的页面几何与页眉页脚；多节模板会整体错位，必须当场拒绝。"""
    from docx import Document

    multi = tmp_path / "multi.docx"
    doc = Document()
    doc.add_paragraph("第一节")
    doc.add_section()
    doc.add_paragraph("第二节")
    doc.save(str(multi))

    (tmp_path / "m.md").write_text("# 一\n\n正文。\n", encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx", template_path=multi)
    )
    assert result.returncode == 1
    assert any("单节" in e for e in result.errors), result.errors


def test_user_csl_direct_formatting_is_stripped(tmp_path: Path) -> None:
    """用户自带的 CSL 里若有 hanging-indent 之类的直接格式，导出时要忽略它。

    直接格式的优先级高于样式：不剥，同一份 requirements.txt 换个 CSL，参考文献的
    悬挂缩进和行距就跟着变——「同一份稿件重跑一致」当场作废。
    """
    (tmp_path / "refs.bib").write_text(
        "@article{a2020, author={Doe, Jane}, title={A Paper}, journal={J}, year={2020}}\n",
        encoding="utf-8",
    )
    (tmp_path / "mine.csl").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<style xmlns="http://purl.org/net/xbiblio/csl" class="in-text" version="1.0">\n'
        "<info><title>Mine</title><id>http://example.com/mine</id></info>\n"
        "<citation><layout><text variable=\"title\"/></layout></citation>\n"
        '<bibliography hanging-indent="true" second-field-align="flush">\n'
        "<layout><text variable=\"title\"/></layout></bibliography></style>\n",
        encoding="utf-8",
    )
    (tmp_path / "m.md").write_text(
        "---\nbibliography: refs.bib\ncsl: mine.csl\n---\n\n# 一 引言\n\n见 [@a2020]。\n\n"
        "%% 参考文献标题 参考文献\n",
        encoding="utf-8",
    )

    result = run_export_pipeline(ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx"))
    assert result.returncode == 0, result.errors
    assert any("hanging-indent" in m for m in result.messages), result.messages


def test_contract_cheatsheet_needs_no_manuscript(capsys) -> None:
    """只装了包、手上没有技能文档的调用方，要能自己问出稿件怎么写。"""
    from md_to_word.cli import main

    assert main(["--contract"]) == 0
    out = capsys.readouterr().out
    assert "%% 样式名" in out and "文档标题" in out and "@eq-" in out
