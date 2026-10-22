"""Unit and integration tests for md_to_word.pipeline."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

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
        '---\ntitle: "题"\nbibliography: refs.bib\n---\n\n# 一 引言\n\n'
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
    """门禁全绿 ≠ 版面没问题。行高列宽、公式与题注的落版只有真 Word 能看，
    所以每次成功导出都要带一条"打开看一眼"的提醒，让它成为交付动作的一部分。"""
    (tmp_path / "m.md").write_text('---\ntitle: "t"\n---\n\n# 一 引言\n\n正文。\n', encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "m.md", output_path=tmp_path / "o.docx", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors
    assert any("用 Word 打开核对" in m for m in result.messages), result.messages


def test_image_paths_are_relative_to_the_manuscript(tmp_path: Path, monkeypatch) -> None:
    """稿里的图片路径相对稿件目录，不相对进程 cwd——否则换个目录调用就全是"图不存在"。"""
    work = tmp_path / "paper"
    (work / "figures").mkdir(parents=True)
    shutil.copy(
        Path(__file__).resolve().parents[1] / "demo/01_chinese_thesis/figures/qa_pipeline.png",
        work / "figures" / "x.png",
    )
    (work / "m.md").write_text(
        '---\ntitle: "t"\n---\n\n![](figures/x.png){width=8cm}\n\n%% 图片题注 图 1 示意图\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)  # 站在别的目录调用
    result = run_export_pipeline(
        ExportOptions(input_path=work / "m.md", output_path=work / "o.docx", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors
    assert "drawing" in __import__("zipfile").ZipFile(work / "o.docx").read("word/document.xml").decode()
