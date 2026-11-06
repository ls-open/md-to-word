"""三道防丢闸门：汉字守恒，以及两个「声明了但没人查」的格式项。

它们的共同点是产物上看不出来——字少了、颜色没生效、行照样跨页，导出都还是成功。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from md_to_word.audit.inspector import audit
from md_to_word.audit.postflight import verify_chinese_integrity
from md_to_word.pipeline import ExportOptions, run_export_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")
TABLE_LINE = re.search(r"^表格：.*$", PRESET, re.M).group(0)
TITLE_LINE = re.search(r"^文档标题：.*$", PRESET, re.M).group(0)
SPEC = PRESET.replace(TABLE_LINE, TABLE_LINE + " 行不跨页").replace(
    TITLE_LINE, TITLE_LINE + " 颜色#1A2B3C")

BODY = "---\n---\n\n# 一 引言\n\n正文第一段。\n\n| 指标 | 值 |\n|:--|:--|\n| 增长率 | 0.5 |\n"


def _export(tmp_path: Path):
    (tmp_path / "m.md").write_text(BODY, encoding="utf-8")
    (tmp_path / "f.txt").write_text(SPEC, encoding="utf-8")
    result = run_export_pipeline(ExportOptions(
        input_path=tmp_path / "m.md", output_path=tmp_path / "m.docx", format_path=tmp_path / "f.txt",
    ))
    assert result.returncode == 0, result.errors
    return tmp_path / "m.md", tmp_path / "m.docx"


def _rewrite(docx: Path, name: str, content: str) -> None:
    with zipfile.ZipFile(docx) as src:
        items = [(info, src.read(info.filename)) for info in src.infolist()]
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as dst:
        for info, data in items:
            dst.writestr(info, content.encode("utf-8") if info.filename == name else data)


def test_a_missing_character_stops_the_export(tmp_path):
    """少一个汉字，产物照样打得开、退出码照样是 0——所以要在导出末尾自己数一遍。"""
    md, docx = _export(tmp_path)
    ok, _ = verify_chinese_integrity(md, docx)
    assert ok

    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    _rewrite(docx, "word/document.xml", xml.replace("正文第一段", "正第一段"))
    ok, missing = verify_chinese_integrity(md, docx)
    assert not ok and missing == ["文"], missing


def test_shortcode_arguments_are_not_required_text(tmp_path):
    """`{{< section 页码=小写罗马 >}}` 的参数是指令，不落成文字，不能算丢字。"""
    md, docx = _export(tmp_path)
    text = md.read_text(encoding="utf-8") + "\n{{< section 页码=小写罗马 起始=1 >}}\n"
    md.write_text(text, encoding="utf-8")
    assert verify_chinese_integrity(md, docx)[0]


def test_colour_is_audited(tmp_path):
    _, docx = _export(tmp_path)
    fmt = tmp_path / "f.txt"
    assert audit(docx, fmt) == []

    styles = zipfile.ZipFile(docx).read("word/styles.xml").decode("utf-8")
    _rewrite(docx, "word/styles.xml", styles.replace("1A2B3C", "000000"))
    assert any("颜色" in msg for _, msg in audit(docx, fmt))


def test_row_split_lock_is_audited(tmp_path):
    _, docx = _export(tmp_path)
    fmt = tmp_path / "f.txt"
    assert audit(docx, fmt) == []

    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    _rewrite(docx, "word/document.xml", xml.replace("<w:cantSplit/>", ""))
    assert any("行不跨页" in msg for _, msg in audit(docx, fmt))


def test_image_alt_is_not_counted_as_body_text(tmp_path):
    """替代文字写进 `docPr/descr`，不进正文；防丢检查不能拿它当正文里的字。"""
    from md_to_word.audit.postflight import extract_numbers, load_source_text

    md = tmp_path / "m.md"
    md.write_text("# 标题\n\n![value 1.234](pic.png)\n\n正文 2.718。\n", encoding="utf-8")
    assert extract_numbers(load_source_text(md)) == {"2.718"}
