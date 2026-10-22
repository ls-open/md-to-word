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


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
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


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
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


def test_missing_renderer_reports_environment_error(tmp_path: Path, monkeypatch):
    """渲染引擎不可用是环境问题（退出码 2），不能和「稿件有问题」（1）混在一起。"""
    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text('---\ntitle: "环境测试"\n---\n\n# 一 引言\n\n正文。\n', encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("未在系统 PATH 中找到 quarto 可执行程序")

    monkeypatch.setattr("md_to_word.pipeline.QuartoRenderer.render", _boom)

    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, preset="zh-academic", postflight=False, audit=False)
    )
    assert result.returncode == 2
    assert any("渲染引擎" in error for error in result.errors)


def test_build_template_rejects_spec_object(tmp_path: Path):
    """TemplateSpec → 文本的序列化还没做：宁可当场报清楚，也不拼出乱码要求文本。"""
    from md_to_word.spec.parser import parse_requirements
    from md_to_word.template.builder import build_template

    spec = parse_requirements(
        "正文：宋体 小四 不加粗 不倾斜 左对齐 行距1.5倍 段前0磅 段后6磅 首行缩进2字符"
    )
    with pytest.raises(TypeError, match="序列化尚未实现"):
        build_template(spec, tmp_path / "t.docx")
