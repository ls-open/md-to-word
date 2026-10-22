"""目录条目样式必须是 Word 的**内置**样式。

Word 的内置目录样式是 `styleId="TOC1"`、`name="toc 1"`、**不带** `w:customStyle`。
用 python-docx 新建同名样式会写成自建样式，Word 更新目录域时按内置定义重建，
字体/字号/加粗全部丢失——作者会以为"设置没生效"。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.template.builder import build_template

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"


def _styles_xml(tmp_path: Path) -> str:
    out = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), out)
    with zipfile.ZipFile(out) as archive:
        return archive.read("word/styles.xml").decode("utf-8")


@pytest.mark.parametrize("level", [1, 2, 3])
def test_toc_styles_are_builtin(level: int, tmp_path: Path) -> None:
    xml = _styles_xml(tmp_path)
    match = re.search(rf'<w:style [^>]*w:styleId="TOC{level}"[^>]*>.*?</w:style>', xml, re.S)
    assert match, f"模板里没有 TOC{level} 样式"
    style = match.group(0)
    assert 'w:customStyle' not in style, "带 customStyle 会被 Word 当成自建样式并重置"
    assert f'<w:name w:val="toc {level}"/>' in style, "内置样式名是小写 toc N"


def test_toc_heading_stays_builtin(tmp_path: Path) -> None:
    xml = _styles_xml(tmp_path)
    match = re.search(r'<w:style [^>]*w:styleId="TOCHeading"[^>]*>.*?</w:style>', xml, re.S)
    assert match and "<w:name w:val=\"TOC Heading\"/>" in match.group(0)
