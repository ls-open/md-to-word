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


def test_extended_syntax_variations():
    """测试常见的中英文格式写法变体（100% 确定性解析）。"""
    from docx.shared import Pt
    from md_to_word.spec.models import MinLineSpacing

    cases = [
        ("正文: 宋体 小四 1.5倍", 1.5, Pt(12)),
        ("正文: 宋体 小四 1.5倍行距", 1.5, Pt(12)),
        ("正文: 宋体 小四 单倍行距", 1.0, Pt(12)),
        ("正文: 宋体 小四 固定值20磅", Pt(20), Pt(12)),
        ("正文: 宋体 12磅 行距20磅", Pt(20), Pt(12)),
        ("正文: 宋体 小四号 行距 1.5倍 首行缩进 2字符", 1.5, Pt(12)),
        ("正文: 宋体 小四 首行缩进2字", None, Pt(12)),
        ("正文: Times New Roman 12pt line-spacing 20pt", Pt(20), Pt(12)),
        ("正文: Times New Roman 12pt line-spacing 1.5", 1.5, Pt(12)),
    ]
    for text, exp_ls, exp_fs in cases:
        spec = parse_requirements(text + "\n")
        s = spec.get_style("Body Text")
        assert s is not None, f"Failed for {text}"
        if exp_ls is not None:
            assert s["line_spacing"] == exp_ls, f"Line spacing mismatch for {text}: {s['line_spacing']} vs {exp_ls}"
        if exp_fs is not None:
            assert s["font_size"] == exp_fs, f"Font size mismatch for {text}: {s['font_size']} vs {exp_fs}"


def test_table_image_caption_key_aliases():
    """测试表名/图名别名直达 Table Caption / Image Caption。"""
    text = """
表名: 宋体 五号 居中
图名: 宋体 五号 居中
"""
    spec = parse_requirements(text)
    tbl_c = spec.get_style("Table Caption")
    assert tbl_c is not None
    assert tbl_c["style_name"] == "Table Caption"

    img_c = spec.get_style("Image Caption")
    assert img_c is not None
    assert img_c["style_name"] == "Image Caption"
