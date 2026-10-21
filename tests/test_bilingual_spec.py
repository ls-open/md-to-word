"""Unit tests for bilingual spec parsing (md_to_word.spec)."""

from __future__ import annotations

import sys
from pathlib import Path
import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from md_to_word.spec import parse_requirements, list_available_presets, read_preset_content


def test_presets_exist():
    presets = list_available_presets()
    assert "zh-academic" in presets
    assert "en-nature" in presets


def test_zh_academic_preset():
    content = read_preset_content("zh-academic")
    assert content is not None
    spec = parse_requirements(content)
    assert len(spec.styles) >= 20
    assert spec.page_size == "a4"
    assert spec.proofing_lang == "zh-CN"
    body_style = spec.get_style("Body Text")
    assert body_style is not None
    assert body_style["alignment"] is not None


def test_en_nature_preset_native_english():
    content = read_preset_content("en-nature")
    assert content is not None
    spec = parse_requirements(content)
    assert len(spec.styles) >= 20
    assert spec.page_size == "a4"
    assert spec.proofing_lang == "en-US"
    assert spec.table.get("style") == "three-line"
    title_style = spec.get_style("Title")
    assert title_style is not None
    assert title_style["bold"] is True


def test_english_compound_syntax():
    text = """
Paper: A4
Margins: top 2.54cm bottom 2.54cm left 2.54cm right 2.54cm
Font: Times New Roman
Proofing Language: en-US

Title: Times New Roman 18pt bold left line-spacing 1.5 space-before 0pt space-after 12pt indent 0
Heading 1: Times New Roman 14pt bold left line-spacing 1.5 space-before 18pt space-after 6pt indent 0 keep-with-next
Body Text: Times New Roman 12pt justify line-spacing 1.5 space-before 0pt space-after 6pt indent 0
Table: center three-line border-top 1pt border-bottom 1pt border-header 0.5pt valign center
Table Header: Times New Roman 10pt bold center repeat-header
Bibliography: Times New Roman 9pt left line-spacing 1.0 hanging-indent 0.5in
Page Number: decimal start 1
Footer Content: {page}
"""
    spec = parse_requirements(text)
    assert spec.page_size == "a4"
    assert spec.margins == {"top": 2.54, "bottom": 2.54, "left": 2.54, "right": 2.54}
    assert spec.default_latin == "Times New Roman"
    assert spec.proofing_lang == "en-US"
    assert spec.table["style"] == "three-line"
    assert spec.table["align"] == "center"
    assert spec.table["valign"] == "center"
    assert spec.table["widths"]["top"] == 1.0


def test_unknown_keyword_raises_error():
    text = "InvalidKey: Arial 12pt bold"
    with pytest.raises(ValueError, match="不认识的键名"):
        parse_requirements(text)


def test_duplicate_style_raises_error():
    text = """
Body Text: Times New Roman 12pt left
Body Text: Arial 10pt right
"""
    with pytest.raises(ValueError, match="重复定义"):
        parse_requirements(text)
