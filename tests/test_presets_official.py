"""内置预设的官方验收。

预设不是「看起来像」就够了：每一条官方数值都要在真实产物里落成 OOXML。这里分两层：

1. **通用层**：每个内置预设都要能解析、能生成模板，页面尺寸与四边页边距必须与声明
   一致（cm → twips 精确到 1）。这层保护所有预设，包括以后新增的。
2. **官方数值层**：`zh-gb9704`（GB/T 9704-2012）与 `en-apa-student`（APA 7 student）
   逐条断言字体、字号、行距、缩进、页码位置、表格线。数值来自标准/官方样张，
   写错一个就会在真 Word 里显形。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.config import get_presets_dir, resolve_preset_path
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.spec.parser import parse_format
from md_to_word.template.builder import build_template

PAGE_SIZES = {"a4": (11906, 16838), "letter": (12240, 15840)}


def _built(name: str, workdir: Path) -> tuple[object, str, str, str]:
    """返回 (spec, document.xml, styles.xml, settings.xml)。"""
    path = resolve_preset_path(name)
    assert path is not None, name
    text = path.read_text(encoding="utf-8")
    spec = parse_format(text)
    out = workdir / "template.docx"
    build_template(text, out)
    with zipfile.ZipFile(out) as archive:
        doc = archive.read("word/document.xml").decode("utf-8")
        styles = archive.read("word/styles.xml").decode("utf-8")
        settings = (
            archive.read("word/settings.xml").decode("utf-8")
            if "word/settings.xml" in archive.namelist() else ""
        )
    return spec, doc, styles, settings


def _style(styles_xml: str, style_id: str) -> str:
    match = re.search(
        r'<w:style [^>]*w:styleId="%s".*?</w:style>' % re.escape(style_id),
        styles_xml, re.S,
    )
    assert match, f"样式 {style_id} 没有生成"
    return match.group(0)


def _attr(fragment: str, tag: str, attr: str) -> str | None:
    match = re.search(r"<w:%s\b[^>]*w:%s=\"([^\"]*)\"" % (tag, attr), fragment)
    return match.group(1) if match else None


def _sect(doc_xml: str) -> str:
    match = re.search(r"<w:sectPr.*?</w:sectPr>", doc_xml, re.S)
    assert match, "产物没有 sectPr"
    return match.group(0)


def _cm_to_twips(value: float) -> int:
    return round(value / 2.54 * 1440)


def test_builtin_presets_are_not_empty() -> None:
    """预设目录为空时，下面两组参数化会各收集 0 条而不是失败。"""
    assert list(get_presets_dir().glob("*.txt")), "预设目录为空"


@pytest.mark.parametrize("name", sorted(p.stem for p in get_presets_dir().glob("*.txt")))
def test_every_preset_exports_a_minimal_manuscript(name: str, tmp_path: Path) -> None:
    """每个内置预设都必须能独立完成一次导出，而不只是生成模板。

    预设是用户的第一入口：`--preset X` 选完却报缺样式，等于这个预设不可用。这里用
    最小稿件过完整流水线（预检、模板、写出、防丢、对账），并确认格式来源就是该预设。
    """
    chinese = not name.startswith("en-")
    text = "# 一级\n\n正文。\n" if chinese else "# Heading\n\nBody text.\n"
    manuscript = tmp_path / "m.md"
    manuscript.write_text(text, encoding="utf-8")
    out = tmp_path / f"{name}.docx"

    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=out, preset=name)
    )

    assert result.ok, f"{name}: {result.errors}"
    assert result.format_source == f"preset:{name}"
    assert out.is_file() and out.stat().st_size > 1000


@pytest.mark.parametrize("name", sorted(p.stem for p in get_presets_dir().glob("*.txt")))
def test_declared_geometry_lands_in_the_document(name: str, tmp_path: Path) -> None:
    spec, doc, _styles, settings = _built(name, tmp_path)
    sect = _sect(doc)

    assert (int(_attr(sect, "pgSz", "w")), int(_attr(sect, "pgSz", "h"))) == PAGE_SIZES[spec.page_size]

    for side, cm in spec.margins.items():
        assert int(_attr(sect, "pgMar", side)) == _cm_to_twips(cm), f"{name} {side}"

    if spec.header_distance is not None:
        assert int(_attr(sect, "pgMar", "header")) == _cm_to_twips(spec.header_distance)
    if spec.footer_distance is not None:
        assert int(_attr(sect, "pgMar", "footer")) == _cm_to_twips(spec.footer_distance)

    assert ("<w:mirrorMargins" in settings) is bool(spec.mirror_margins)


def test_gb9704_body_layout_matches_the_standard(tmp_path: Path) -> None:
    _spec, doc, styles, settings = _built("zh-gb9704", tmp_path)

    body = _style(styles, "BodyText")
    assert _attr(body, "sz", "val") == "32"                  # 3号 = 16pt
    assert _attr(body, "rFonts", "eastAsia") == "仿宋"
    assert _attr(body, "spacing", "line") == "578"           # 28.9pt 固定行距
    assert _attr(body, "spacing", "lineRule") == "exact"
    assert _attr(body, "ind", "firstLineChars") == "200"     # 左空二字
    assert _attr(body, "jc", "val") == "both"

    title = _style(styles, "Title")
    assert _attr(title, "sz", "val") == "44"                 # 2号 = 22pt
    assert _attr(title, "rFonts", "eastAsia") == "方正小标宋简体"
    assert _attr(title, "jc", "val") == "center"
    assert _attr(title, "b", "val") == "0"

    for level, font in (("Heading1", "黑体"), ("Heading2", "楷体"), ("Heading3", "仿宋")):
        heading = _style(styles, level)
        assert _attr(heading, "rFonts", "eastAsia") == font
        assert _attr(heading, "sz", "val") == "32"
        assert _attr(heading, "b", "val") == "0"

    footer = _style(styles, "Footer")
    assert _attr(footer, "jc", "val") == "right"
    assert _attr(footer, "sz", "val") == "28"                # 4号 = 14pt
    # 中文字槽是宋体；数字随西文字体（Times New Roman），这是已知且写明的偏差。
    assert _attr(footer, "rFonts", "eastAsia") == "宋体"

    assert "<w:mirrorMargins" in settings
    assert 'w:fmt="decimal"' in _sect(doc)
    assert 'w:start="1"' in _sect(doc)

    # 22 行必须真的装得下：版心高度 ÷ 行距 ≥ 22
    usable_pt = (29.7 - 3.7 - 3.5) / 2.54 * 72
    assert usable_pt / 28.9 >= 22


def test_gb9704_footer_carries_dash_page_dash(tmp_path: Path) -> None:
    path = resolve_preset_path("zh-gb9704")
    out = tmp_path / "template.docx"
    build_template(path.read_text(encoding="utf-8"), out)
    with zipfile.ZipFile(out) as archive:
        footer = "".join(
            archive.read(n).decode("utf-8")
            for n in archive.namelist() if re.match(r"word/footer\d*\.xml", n)
        )
    assert "PAGE" in footer
    assert "—" in footer


def test_apa_student_body_layout_matches_the_style_guide(tmp_path: Path) -> None:
    _spec, doc, styles, _settings = _built("en-apa-student", tmp_path)
    sect = _sect(doc)

    assert "footerReference" not in sect                       # 学生版页码在页眉
    assert "headerReference" in sect

    body = _style(styles, "BodyText")
    assert _attr(body, "sz", "val") == "24"                    # 12pt
    assert _attr(body, "spacing", "line") == "480"             # double
    assert _attr(body, "spacing", "lineRule") == "auto"
    assert _attr(body, "ind", "firstLine") == "720"            # 0.5in
    assert _attr(body, "jc", "val") == "left"

    title = _style(styles, "Title")
    assert _attr(title, "sz", "val") == "24"
    assert "<w:b/>" in title
    assert _attr(title, "jc", "val") == "center"

    h1, h2, h3 = (_style(styles, n) for n in ("Heading1", "Heading2", "Heading3"))
    assert _attr(h1, "jc", "val") == "center" and "<w:b/>" in h1
    assert _attr(h2, "jc", "val") == "left" and "<w:b/>" in h2
    assert "<w:b/>" in h3 and "<w:i/>" in h3

    h4 = _style(styles, "Heading4")
    assert _attr(h4, "ind", "firstLine") == "720"

    bib = _style(styles, "Bibliography")
    assert _attr(bib, "ind", "hanging") == "720"
    assert _attr(bib, "ind", "left") == "720"
    assert _attr(bib, "spacing", "line") == "480"

    header = _style(styles, "Header")
    assert _attr(header, "jc", "val") == "right"

    abstract = _style(styles, "AbstractTitle")
    assert "<w:pageBreakBefore/>" in abstract

    table = _style(styles, "Table")
    assert _attr(table, "top", "val") == "single"
    assert _attr(table, "bottom", "val") == "single"
    assert _attr(table, "insideV", "val") == "none"
    assert _attr(table, "left", "val") == "none"


def test_apa_student_header_carries_page_number(tmp_path: Path) -> None:
    path = resolve_preset_path("en-apa-student")
    out = tmp_path / "template.docx"
    build_template(path.read_text(encoding="utf-8"), out)
    with zipfile.ZipFile(out) as archive:
        header = "".join(
            archive.read(n).decode("utf-8")
            for n in archive.namelist() if re.match(r"word/header\d*\.xml", n)
        )
    assert "PAGE" in header


def test_zh_report_can_generate_a_toc(tmp_path: Path) -> None:
    """报告预设必须能生成目录，且页眉跟随章节，不是写死的一句宣传语。"""
    manuscript = tmp_path / "report.md"
    manuscript.write_text(
        "%% 文档标题 2026 年度技术白皮书\n\n{{< toc >}}\n\n"
        "# 一、背景\n\n正文。\n\n## 1.1 现状\n\n正文。\n",
        encoding="utf-8",
    )
    out = tmp_path / "report.docx"

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=out, preset="zh-report",
    ))

    assert result.ok, result.errors
    with zipfile.ZipFile(out) as archive:
        document = archive.read("word/document.xml").decode("utf-8")
        headers = "".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if re.match(r"word/header\d*\.xml", name)
        )
    assert "TOC" in document
    assert "智能体与数字化交付技术白皮书" not in headers
    assert "STYLEREF" in headers or "PAGEREF" in headers
