"""列表的层级、混合编号，以及引用块里的列表。

三条都是「用户会写、但写出来看不出错」的形态：拍平、编号错位、原始语法漏进成品。
这里锁的是模型与 XML 两层事实——层级落在 `ilvl` 上，而不是靠行首空格假装缩进。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from md_to_word.model.document import ListBlock, Quote
from md_to_word.model.reader import read_markdown
from md_to_word.template.builder import build_template

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"


@pytest.fixture
def template(tmp_path: Path) -> Path:
    out = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), out)
    return out


def _levels(block: ListBlock) -> list[int]:
    return [item.level for item in block.items]


def test_nested_bullets_get_levels() -> None:
    doc = read_markdown("- 甲\n  - 甲一\n    - 甲一一\n  - 甲二\n- 乙\n")
    block = doc.blocks[0]
    assert isinstance(block, ListBlock)
    assert _levels(block) == [0, 1, 2, 1, 0]


def test_nested_ordered_list_inside_bullet_stays_in_one_block() -> None:
    doc = read_markdown("- 甲\n  1. 一\n  2. 二\n- 乙\n")
    block = doc.blocks[0]
    assert isinstance(block, ListBlock)
    assert len(doc.blocks) == 1, "子项属于外层列表，不该另起一块"
    assert [item.ordered for item in block.items] == [False, True, True, False]
    assert _levels(block) == [0, 1, 1, 0]


def test_top_level_type_change_starts_a_new_list() -> None:
    doc = read_markdown("- 甲\n- 乙\n\n1. 一\n2. 二\n")
    assert [type(b).__name__ for b in doc.blocks] == ["ListBlock", "ListBlock"]
    assert doc.blocks[0].ordered is False and doc.blocks[1].ordered is True


def test_levels_stop_at_three() -> None:
    doc = read_markdown("- 甲\n  - 乙\n    - 丙\n      - 丁\n")
    assert _levels(doc.blocks[0]) == [0, 1, 2, 2], "第四层及以下并到第三层，不造出读不清的缩进"


def test_quote_parses_block_level_content() -> None:
    doc = read_markdown("> 说明：\n>\n> - 项一\n> - 项二\n")
    quote = doc.blocks[0]
    assert isinstance(quote, Quote)
    assert [type(b).__name__ for b in quote.blocks] == ["Paragraph", "ListBlock"]


def test_list_starting_at_five_keeps_counting(tmp_path: Path, template: Path) -> None:
    """从 5 开始的列表要 5、6、7——每项各建一个编号实例的话会变成 5、5、5。"""
    from md_to_word.model.reader import read_markdown as read
    from md_to_word.writer.docx_writer import write_docx

    out = write_docx(read("5. 甲\n6. 乙\n7. 丙\n"), template, tmp_path / "b.docx")
    with zipfile.ZipFile(out) as archive:
        numbering = archive.read("word/numbering.xml").decode("utf-8")
    assert numbering.count("<w:num ") == 3, "两套基础定义 + 一个带起始号的实例，多一个就是重复计数"
    assert numbering.count("<w:startOverride") == 1


def test_nested_list_writes_ilvl_not_spaces(tmp_path: Path, template: Path) -> None:
    """层级要落成 Word 的 ilvl——写死空格的话，在 Word 里回车、改级别都会失效。"""
    from md_to_word.model.reader import read_markdown as read
    from md_to_word.writer.docx_writer import write_docx

    out = write_docx(read("- 甲\n  - 甲一\n- 乙\n"), template, tmp_path / "a.docx")
    with zipfile.ZipFile(out) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert '<w:ilvl w:val="0"/>' in xml and '<w:ilvl w:val="1"/>' in xml
    numbering = ""
    with zipfile.ZipFile(out) as archive:
        numbering = archive.read("word/numbering.xml").decode("utf-8")
    assert numbering.count('<w:lvl w:ilvl="2"') == 2, "无序与有序各要三级定义"
