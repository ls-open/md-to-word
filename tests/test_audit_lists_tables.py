"""审计回归：嵌套有序列表的起始号、表格单元格的行内换行、列表项里的代码块。

三条都是「产物看着像对的、结构其实已经丢了」的形态：深层编号被 Word 重数成 a)、
单元格里的换行标记被印成反斜杠或被 `strip()` 吃掉、代码块从列表项掉到顶层。
这里钉住读与写两层的事实，而不是只比最后印出来的几行字。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.model.document import CodeBlock, LineBreak, ListBlock
from md_to_word.model.reader import read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.template.builder import build_template
from md_to_word.writer.docx_writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"


@pytest.fixture
def template(tmp_path: Path) -> Path:
    out = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), out)
    return out


def _part(docx_path: Path, name: str) -> str:
    with zipfile.ZipFile(docx_path) as archive:
        return archive.read(name).decode("utf-8")


def _table_xml(document_xml: str) -> str:
    match = re.search(r"<w:tbl>.*?</w:tbl>", document_xml, re.S)
    assert match is not None, "稿件里有一个表格，产物里却没有 <w:tbl>"
    return match.group(0)


# ── 1. 嵌套有序列表的起始号 ────────────────────────────────────────────

def test_nested_ordered_list_keeps_its_own_start(tmp_path: Path, template: Path) -> None:
    """深层从 `3.` 开始时，要把 3 写进该层的 lvlOverride，而不是让它从 a) 重数。"""
    document = read_markdown("1. 顶层一\n   3. 嵌套从三开始\n   4. 嵌套四\n")
    out = write_docx(document, template, tmp_path / "nested.docx")
    numbering = _part(out, "word/numbering.xml")

    assert '<w:lvlOverride w:ilvl="1"><w:startOverride w:val="3"/></w:lvlOverride>' in numbering


def test_nested_levels_starting_at_one_do_not_bloat_numbering(tmp_path: Path, template: Path) -> None:
    """起始号本来就是 1 的层不写 override：默认值已经是 1，多写只是让 XML 变胖。"""
    document = read_markdown("1. 一\n   1. 甲\n2. 二\n")
    out = write_docx(document, template, tmp_path / "plain.docx")
    numbering = _part(out, "word/numbering.xml")

    assert numbering.count("<w:startOverride") == 1, numbering


def test_deeper_start_does_not_disturb_the_top_level_count(tmp_path: Path, template: Path) -> None:
    """深层起始号只落在自己那一层，顶层仍按 1、2 数。"""
    document = read_markdown("1. 顶层一\n   5. 嵌套五\n2. 顶层二\n")
    block = document.blocks[0]
    assert isinstance(block, ListBlock)
    assert [(item.level, item.ordered) for item in block.items] == [(0, True), (1, True), (0, True)]

    out = write_docx(document, template, tmp_path / "deep.docx")
    numbering = _part(out, "word/numbering.xml")
    assert '<w:lvlOverride w:ilvl="0"><w:startOverride w:val="1"/></w:lvlOverride>' in numbering
    assert '<w:lvlOverride w:ilvl="1"><w:startOverride w:val="5"/></w:lvlOverride>' in numbering


# ── 2. 表格单元格里的换行 ───────────────────────────────────────────────

def test_backslash_at_cell_end_is_a_break_not_printed_text() -> None:
    """`| 第一行\\ |` 是段内换行，不是字面反斜杠：模型里该是「第一行 + LineBreak」。"""
    document = read_markdown("| 第一行\\ | 普通 |\n| --- | --- |\n| 甲 | 乙 |\n")
    inlines = document.blocks[0].header[0]

    assert "".join(getattr(node, "value", "") for node in inlines) == "第一行"
    assert any(isinstance(node, LineBreak) for node in inlines)


def test_two_trailing_spaces_in_a_cell_survive_the_split() -> None:
    """行尾两个空格在单元格里也是换行标记，不能被 `strip()` 一起吃掉。"""
    document = read_markdown("| 第一行  | 普通 |\n| --- | --- |\n| 甲 | 乙 |\n")
    inlines = document.blocks[0].header[0]

    assert "".join(getattr(node, "value", "") for node in inlines) == "第一行"
    assert any(isinstance(node, LineBreak) for node in inlines)


@pytest.mark.parametrize("marker", ["\\", "  "])
def test_cell_break_is_written_as_br(tmp_path: Path, template: Path, marker: str) -> None:
    document = read_markdown(
        f"%% 文档标题 题目\n\n| 第一行{marker} | 普通 |\n| --- | --- |\n| 甲 | 乙 |\n"
    )
    out = write_docx(document, template, tmp_path / "cell.docx")
    table = _table_xml(_part(out, "word/document.xml"))

    assert "第一行" in table
    assert "<w:br/>" in table, table
    assert "\\" not in table, "反斜杠是换行标记，不该印进单元格"


def test_single_trailing_space_is_just_padding() -> None:
    """一个行尾空格是表格的排版留白，不是换行标记——不许把它读成 w:br。"""
    document = read_markdown("| 第一行 | 普通 |\n| --- | --- |\n| 甲 | 乙 |\n")
    inlines = document.blocks[0].header[0]

    assert not any(isinstance(node, LineBreak) for node in inlines)


# ── 3. 列表项里的代码块 ────────────────────────────────────────────────

LIST_WITH_CODE_BODY = "- 列表项一\n  ```python\n  print(1)\n  ```\n"
LIST_WITH_CODE = "%% 文档标题 题目\n\n# 一\n\n" + LIST_WITH_CODE_BODY


def test_code_block_after_a_list_item_belongs_to_that_item() -> None:
    """缩进围栏属于上面的列表项：至少模型里不能把它读成顶层块。"""
    document = read_markdown(LIST_WITH_CODE_BODY)
    assert [type(block).__name__ for block in document.blocks] == ["ListBlock"]
    item = document.blocks[0].items[0]
    assert [type(inner).__name__ for inner in item.blocks] == ["Paragraph", "CodeBlock"]
    assert isinstance(item.blocks[1], CodeBlock) and "print(1)" in item.blocks[1].value


def test_code_block_inside_a_list_item_is_refused_not_misplaced(tmp_path: Path) -> None:
    """写出器还没有「列表项里的代码块」这种结构：明确报错，总比静默提到列表外好。"""
    source = tmp_path / "list-code.md"
    source.write_text(LIST_WITH_CODE, encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(
            input_path=source, output_path=tmp_path / "list-code.docx", preset="zh-academic"
        )
    )

    assert result.returncode != 0, "代码块没有落进列表项，就不该当成导出成功"
    assert result.errors and "列表项" in result.errors[0], result.errors


def test_top_level_code_block_after_a_list_still_works(tmp_path: Path, template: Path) -> None:
    """顶格围栏是另一个块，不该被误认成列表项的孩子。"""
    document = read_markdown("- 项一\n\n```python\nprint(1)\n```\n")
    assert [type(block).__name__ for block in document.blocks] == ["ListBlock", "CodeBlock"]

    out = write_docx(document, template, tmp_path / "top.docx")
    assert "print(1)" in _part(out, "word/document.xml")
