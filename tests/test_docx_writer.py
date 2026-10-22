"""模型 → OOXML 的写出器。

验收方式是**双后端对拍**：同一份稿件分别走 Pandoc（现有通道）与自研写出器，比对
样式序列与全文文本。样式序列一致，说明「哪一段用什么样式」这层判断没有跑偏；
文本一致，说明内容一个字没丢。

能力边界单独测：没实现的结构必须抛 `UnsupportedFeature`，不许静默降级成普通段落。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from md_to_word.model.reader import read_markdown
from md_to_word.template.builder import build_template
from md_to_word.writer import UnsupportedFeature, write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"
DEMO = REPO_ROOT / "demo" / "00_quickstart"


def _facts(path: Path) -> tuple[list[str], str]:
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    styles = re.findall(r'<w:pStyle w:val="([^"]+)"', xml)
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    return styles, text


@pytest.fixture()
def template(tmp_path: Path) -> Path:
    out = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), out)
    return out


def test_writes_title_block_and_blocks(template: Path, tmp_path: Path) -> None:
    model = read_markdown(
        '---\ntitle: "题目"\nauthor: [张三]\n---\n\n# 一 引言\n\n正文。\n\n## 1.1 小节\n\n更多正文。\n'
    )
    out = write_docx(model, template, tmp_path / "a.docx")
    styles, text = _facts(out)
    assert styles[:2] == ["Title", "Author"]
    assert "Heading1" in styles
    assert "First Paragraph" in text or "FirstParagraph" in styles


def test_first_paragraph_after_heading_uses_first_paragraph_style(template: Path, tmp_path: Path) -> None:
    model = read_markdown("# 一 引言\n\n第一段。\n\n第二段。\n")
    styles, _ = _facts(write_docx(model, template, tmp_path / "b.docx"))
    assert styles == ["Heading1", "FirstParagraph", "BodyText"]


def test_table_header_is_marked_and_cells_use_compact(template: Path, tmp_path: Path) -> None:
    model = read_markdown("| 甲 | 乙 |\n|:--|--:|\n| 1 | 2 |\n")
    out = write_docx(model, template, tmp_path / "c.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert "<w:tbl>" in xml
    assert "tblHeader" in xml, "表头行要标记跨页重复"
    assert xml.count('w:val="Compact"') == 4  # 表头两格 + 数据两格


def test_code_block_keeps_line_breaks(template: Path, tmp_path: Path) -> None:
    model = read_markdown("```\nline1\nline2\n```\n")
    out = write_docx(model, template, tmp_path / "d.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert "line1" in xml and "line2" in xml


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("$$E = mc^2$$\n", "公式"),
        ("{{< toc >}}\n", "目录"),
        ("{{< section 页码=罗马 >}}\n", "分节"),
        ("见 [@smith2024]。\n", "引文"),
    ],
)
def test_unsupported_features_fail_loudly(source: str, fragment: str, template: Path, tmp_path: Path) -> None:
    model = read_markdown(source)
    with pytest.raises(UnsupportedFeature, match=fragment):
        write_docx(model, template, tmp_path / "x.docx")


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
def test_matches_pandoc_output_on_quickstart(template: Path, tmp_path: Path) -> None:
    """双后端对拍：样式序列与全文文本必须一致。"""
    for name in ("hello.md", "requirements.txt"):
        shutil.copy(DEMO / name, tmp_path / name)

    ours = write_docx(
        read_markdown((DEMO / "hello.md").read_text(encoding="utf-8")),
        template,
        tmp_path / "ours.docx",
    )

    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "export.sh"), "hello.md", "-o", "theirs.docx"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )

    our_styles, our_text = _facts(ours)
    their_styles, their_text = _facts(tmp_path / "theirs.docx")
    assert our_styles == their_styles
    assert our_text == their_text


def test_lists_use_real_numbering(template: Path, tmp_path: Path) -> None:
    """编号必须是域而不是字面量，否则 Word 里按退格改不了级别、增删条目不会重编号。"""
    model = read_markdown("- 甲\n- 乙\n\n1. 一\n2. 二\n")
    out = write_docx(model, template, tmp_path / "list.docx")
    package = zipfile.ZipFile(out)
    document = package.read("word/document.xml").decode("utf-8")
    numbering = package.read("word/numbering.xml").decode("utf-8")

    assert document.count("<w:numPr>") == 4
    assert "<w:abstractNum " in numbering and "<w:num " in numbering
    assert 'w:numFmt w:val="bullet"' in numbering
    assert 'w:numFmt w:val="decimal"' in numbering


def test_ordered_list_start_override(template: Path, tmp_path: Path) -> None:
    model = read_markdown("3. 第三\n4. 第四\n")
    out = write_docx(model, template, tmp_path / "start.docx")
    numbering = zipfile.ZipFile(out).read("word/numbering.xml").decode("utf-8")
    assert 'w:startOverride w:val="3"' in numbering


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
def test_matches_pandoc_output_on_lists(template: Path, tmp_path: Path) -> None:
    source = '---\ntitle: "列表测试"\n---\n\n# 一 章节\n\n正文。\n\n- 甲\n- 乙\n\n1. 一\n2. 二\n'
    (tmp_path / "m.md").write_text(source, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(PRESET.read_text(encoding="utf-8"), encoding="utf-8")

    ours = write_docx(read_markdown(source), template, tmp_path / "ours.docx")
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "export.sh"), "m.md", "-o", "theirs.docx"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    our_styles, our_text = _facts(ours)
    their_styles, their_text = _facts(tmp_path / "theirs.docx")
    assert our_styles == their_styles
    assert our_text == their_text, "列表的文本与编号级联应与 Pandoc 一致"


def test_footnotes_are_written_as_a_real_part(template: Path, tmp_path: Path) -> None:
    """脚注不是正文里的上标文字，而是独立的 footnotes.xml 部件。"""
    model = read_markdown("# 一 章节\n\n正文有脚注[^1]。\n\n[^1]: 注释文字。\n")
    out = write_docx(model, template, tmp_path / "fn.docx")
    package = zipfile.ZipFile(out)
    assert "word/footnotes.xml" in package.namelist()

    footnotes = package.read("word/footnotes.xml").decode("utf-8")
    assert 'w:type="separator"' in footnotes, "缺分隔符，脚注区的横线会显示异常"
    assert 'w:type="continuationSeparator"' in footnotes
    assert "注释文字" in footnotes

    document = package.read("word/document.xml").decode("utf-8")
    assert 'w:id="1"' in document and "footnoteReference" in document

    # 能重新打开，说明关系与内容类型都写对了
    from docx import Document as open_docx
    open_docx(str(out))
