"""三道防丢闸门：汉字守恒，以及两个「声明了但没人查」的格式项。

它们的共同点是产物上看不出来——字少了、颜色没生效、行照样跨页，导出都还是成功。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from md_to_word.audit.inspector import audit
from md_to_word.audit.postflight import (
    verify_chinese_integrity, verify_latin_integrity, verify_numeric_integrity,
)
from md_to_word.pipeline import ExportOptions, run_export_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")
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
    """`{{< section 正文 >}}` 的节名是指令，不落成文字，不能算丢字。"""
    md, docx = _export(tmp_path)
    text = md.read_text(encoding="utf-8") + "\n{{< section 正文 >}}\n"
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
    import shutil

    shutil.copyfile(REPO_ROOT / "tests" / "fixtures" / "images" / "tiny.png", tmp_path / "pic.png")
    md = tmp_path / "m.md"
    md.write_text(
        "# 标题\n\n![value 1.234](pic.png){width=2cm}\n\n%% 图片题注 图 1 示意图\n\n"
        "正文 2.718。\n",
        encoding="utf-8",
    )
    docx = tmp_path / "m.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=md, output_path=docx, preset="zh-academic",
    ))
    assert result.returncode == 0, result.errors
    ok, missing = verify_numeric_integrity(md, docx)
    assert ok, missing


def _export_english(tmp_path: Path, body: str) -> tuple[Path, Path]:
    md = tmp_path / "en.md"
    md.write_text(body, encoding="utf-8")
    docx = tmp_path / "en.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=md, output_path=docx, preset="en-nature",
    ))
    assert result.returncode == 0, result.errors
    return md, docx


def test_a_missing_english_word_is_caught(tmp_path):
    """英文整段/整词丢失时，产物仍然打得开、退出码也还是 0——必须自己数。"""
    md, docx = _export_english(
        tmp_path,
        "# Title\n\nThe quick brown fox jumps over the lazy dog.\n\n"
        "Second paragraph keeps the page honest.\n",
    )
    assert verify_latin_integrity(md, docx)[0]

    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    _rewrite(docx, "word/document.xml", xml.replace("jumps ", ""))
    ok, missing = verify_latin_integrity(md, docx)
    assert not ok and "jumps" in missing, missing


def test_repeated_english_words_are_counted_not_just_checked_for_presence(tmp_path):
    """同一个词出现两次、产物只剩一次，也是丢内容；集合式比对会漏掉。"""
    md, docx = _export_english(tmp_path, "# Title\n\nalpha beta alpha gamma.\n")
    assert verify_latin_integrity(md, docx)[0]

    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    _rewrite(docx, "word/document.xml", xml.replace("alpha", "", 1))
    ok, missing = verify_latin_integrity(md, docx)
    assert not ok and missing == ["alpha"], missing


def test_markdown_syntax_and_generated_content_are_not_counted_as_lost(tmp_path):
    """加粗、链接、行内代码、注释、公式、交叉引用、短码都不是正文文字。"""
    md, docx = _export_english(
        tmp_path,
        "# Title\n\n"
        "Keep **bold words** and *italic words*, a [linked phrase](https://example.com/a), "
        "and `code_token`. Inline math $x^2 + y^2$ is generated, not literal. "
        "before<!-- hidden -->after stays adjacent. "
        "A footnote carries real text.[^note]\n\n"
        "{{< pagebreak >}}\n\n"
        "$$\\frac{a}{b} = c$$\n\n"
        "[^note]: Footnote sentence survives in footnotes.xml.\n",
    )
    ok, missing = verify_latin_integrity(md, docx)
    assert ok, missing


def test_integer_loss_is_caught_not_only_high_precision_decimals(tmp_path):
    """表格里的整数、样本量、年份整块消失时，产物仍然看起来正常。"""
    md, docx = _export_english(
        tmp_path,
        "# Title\n\n| group | n |\n|:--|--:|\n| control | 42 |\n| treatment | 43 |\n",
    )
    assert verify_numeric_integrity(md, docx)[0]

    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    _rewrite(docx, "word/document.xml", xml.replace(">42<", "><"))
    ok, missing = verify_numeric_integrity(md, docx)
    assert not ok and missing == ["42"], missing


def test_blockquote_text_is_kept_in_the_body(tmp_path):
    """引用块是正文，不是注释；导出必须保留，防丢检查也要把它算进去。"""
    from md_to_word.audit.postflight import docx_text

    md, docx = _export_english(
        tmp_path,
        "# Title\n\n> Quoted sentence stays in the body.\n\nAfter the quote.\n",
    )
    assert "Quoted sentence stays in the body." in docx_text(docx)
    assert verify_latin_integrity(md, docx)[0]


def test_english_split_across_runs_is_reassembled(tmp_path):
    """`Hel` + `lo` 两个 run 是一个词；按 run 断开会把正常导出误判成丢词。"""
    md, docx = _export_english(
        tmp_path,
        "# Title\n\nA **bold** word and a normal word.\n",
    )
    ok, missing = verify_latin_integrity(md, docx)
    assert ok, missing
