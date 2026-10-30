"""Unit tests for bilingual spec parsing (md_to_word.spec)."""

from __future__ import annotations

import pytest

from md_to_word.spec import list_available_presets, parse_format, read_preset_content


def test_presets_exist():
    presets = list_available_presets()
    assert "zh-academic" in presets
    assert "en-nature" in presets


def test_zh_academic_preset():
    content = read_preset_content("zh-academic")
    assert content is not None
    spec = parse_format(content)
    assert len(spec.styles) >= 20
    assert spec.page_size == "a4"
    assert spec.proofing_lang == "zh-CN"
    body_style = spec.get_style("Body Text")
    assert body_style is not None
    assert body_style["alignment"] is not None


def test_en_nature_preset_native_english():
    content = read_preset_content("en-nature")
    assert content is not None
    spec = parse_format(content)
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
    spec = parse_format(text)
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
        parse_format(text)


def test_duplicate_style_raises_error():
    text = """
Body Text: Times New Roman 12pt left
Body Text: Arial 10pt right
"""
    with pytest.raises(ValueError, match="重复定义"):
        parse_format(text)


def test_canonical_syntax():
    """测试正典标准语法（唯一正规中英写法，确定性 100% 解析）。"""
    from docx.shared import Pt
    from md_to_word.spec.models import MinLineSpacing

    cases = [
        ("正文: 宋体 小四 行距1.5倍 首行缩进2字符 两端对齐", 1.5, Pt(12)),
        ("正文: 宋体 小四号 行距1.5倍 首行缩进2字符 两端对齐", 1.5, Pt(12)),
        ("正文: 宋体 12pt 行距20磅 首行缩进0字符 两端对齐", Pt(20), Pt(12)),
        ("正文: 宋体 小四 行距最小值20磅 首行缩进2字符", MinLineSpacing(20), Pt(12)),
        ("正文: Times New Roman 12pt line-spacing 20pt indent 0 justify", Pt(20), Pt(12)),
        ("正文: Times New Roman 12pt line-spacing 1.5 hanging-indent 0.5in", 1.5, Pt(12)),
    ]
    for text, exp_ls, exp_fs in cases:
        spec = parse_format(text + "\n")
        s = spec.get_style("Body Text")
        assert s is not None, f"Failed for {text}"
        if exp_ls is not None:
            assert s["line_spacing"] == exp_ls, f"Line spacing mismatch for {text}: {s['line_spacing']} vs {exp_ls}"
        if exp_fs is not None:
            assert s["font_size"] == exp_fs, f"Font size mismatch for {text}: {s['font_size']} vs {exp_fs}"


def test_rejection_with_canonical_hints():
    """测试非正典变体被严格拦截，且给出精准单一正典纠偏提示。"""
    # 1. 裸倍数拦截
    with pytest.raises(ValueError, match="行距倍数请统一写「行距N倍」"):
        parse_format("正文: 宋体 小四 1.5倍\n")

    # 2. 固定值写法拦截
    with pytest.raises(ValueError, match="固定磅值行距请统一写「行距N磅」"):
        parse_format("正文: 宋体 小四 固定值20磅\n")

    # 3. 裸单倍行距拦截
    with pytest.raises(ValueError, match="行距倍数请统一写「行距1.0倍」"):
        parse_format("正文: 宋体 小四 单倍行距\n")

    # 4. 无缩进拦截，引导到首行缩进0
    with pytest.raises(ValueError, match="免缩进请统一写「首行缩进0」"):
        parse_format("正文: 宋体 小四 无缩进\n")

    # 5. 字号裸磅值拦截，引导到 12pt
    with pytest.raises(ValueError, match="数值字号必须带单位 pt"):
        parse_format("正文: 宋体 12磅 行距20磅\n")


def test_table_image_caption_key_aliases():
    """测试表名/图名别名直达 Table Caption / Image Caption。"""
    text = """
表名: 宋体 五号 居中
图名: 宋体 五号 居中
"""
    spec = parse_format(text)
    tbl_c = spec.get_style("Table Caption")
    assert tbl_c is not None
    assert tbl_c["style_name"] == "Table Caption"

    img_c = spec.get_style("Image Caption")
    assert img_c is not None
    assert img_c["style_name"] == "Image Caption"
