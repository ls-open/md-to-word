"""产物结构基线（golden）。

「能导出」不够：改 A 坏 B 的时候，导出照样成功。这里把一份固定稿件的结构事实
（段落样式序列、可见文本序列、公式/表格/脚注计数、引文是否上标）存成基线，
改动后逐项比对。

不比对二进制：Pandoc 补丁版本会改文件头与 rsid，那种差异没有信息量。
基线需要重写时：`UPDATE_GOLDEN=1 pytest tests/test_golden_output.py`。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import zipfile
from pathlib import Path

import pytest

from md_to_word.pipeline import ExportOptions, run_export_pipeline

FIXTURES = Path(__file__).resolve().parent / "fixtures"
GOLDEN = Path(__file__).resolve().parent / "golden" / "manuscript_zh.json"

def _document_xml(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def _facts(xml: str) -> dict:
    runs = [t for t in re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml) if t.strip()]
    return {
        "paragraph_styles": re.findall(r'<w:pStyle w:val="([^"]+)"', xml),
        "text": runs,
        "equations": xml.count("<m:oMath"),
        "tables": xml.count("<w:tbl>"),
        "three_line_borders": xml.count("<w:tblBorders"),
        "footnote_refs": xml.count('w:type="footnoteReference"') + xml.count("footnoteReference"),
        "superscript_runs": xml.count('w:vertAlign w:val="superscript"'),
    }


def test_manuscript_structure_matches_golden(tmp_path: Path) -> None:
    for name in ("manuscript.md", "refs.bib"):
        shutil.copy(FIXTURES / name, tmp_path / name)

    result = run_export_pipeline(
        ExportOptions(input_path=tmp_path / "manuscript.md", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors

    facts = _facts(_document_xml(result.output_docx))

    if os.environ.get("UPDATE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
        pytest.skip("已重写基线")

    assert GOLDEN.is_file(), f"缺少基线文件 {GOLDEN}；用 UPDATE_GOLDEN=1 生成"
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))

    for key in expected:
        assert facts[key] == expected[key], f"{key} 与基线不一致"
