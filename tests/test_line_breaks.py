"""段内换行与「一行一段」的分工。

两种需求必须各走各的路：

- **短段落序列**：每行一个段落，各自能挂样式。这是「一行一段」的本意，不许被合并。
- **同一段落内换行**：行尾 `\\` 或两个空格，写出时落成 `<w:br/>`，段落属性仍是一套。

这两件事混在一起时，作者要么拿到一堆被拆开的段（每段多吃一次首行缩进），要么拿不到
真正的段内换行。这里把三条路径都钉住。
"""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from md_to_word.model.reader import read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline


def _paragraphs(xml: str) -> list[tuple[str, int]]:
    """(纯文本, `<w:br/>` 个数) 序列，只看正文段落。"""
    import re

    out = []
    for raw in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", raw))
        if text.strip():
            out.append((text, raw.count("<w:br/>")))
    return out


def _export(tmp_path: Path, manuscript: str, name: str = "m") -> zipfile.ZipFile:
    path = tmp_path / f"{name}.md"
    path.write_text(manuscript, encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(input_path=path, output_path=tmp_path / f"{name}.docx", preset="zh-academic")
    )
    assert result.returncode == 0, result.errors
    return zipfile.ZipFile(tmp_path / f"{name}.docx")


def test_backslash_at_line_end_is_one_paragraph_with_breaks(tmp_path: Path) -> None:
    archive = _export(tmp_path, "%% 文档标题 题目\n\n# 一\n\n第一行\\\n第二行\\\n第三行。\n")
    paragraphs = _paragraphs(archive.read("word/document.xml").decode("utf-8"))

    assert ("第一行第二行第三行。", 2) in paragraphs, paragraphs


def test_two_trailing_spaces_are_the_same_thing(tmp_path: Path) -> None:
    archive = _export(tmp_path, "%% 文档标题 题目\n\n# 一\n\n上一行  \n下一行。\n")
    paragraphs = _paragraphs(archive.read("word/document.xml").decode("utf-8"))

    assert ("上一行下一行。", 1) in paragraphs, paragraphs


def test_plain_lines_stay_separate_paragraphs() -> None:
    """短段落序列是合法的：不写换行标记就各自成段，各自能挂样式。"""
    document = read_markdown("第一段\n第二段\n%% 表题 **表 1** 题注\n")

    assert [getattr(block, "style", None) for block in document.blocks] == [None, None, "Table Caption"]


def test_double_backslash_is_a_literal_backslash() -> None:
    """`\\\\` 是字面反斜杠（Windows 路径），不该被当成换行标记吃掉一个字符。"""
    document = read_markdown("路径 C:\\\\\n下一段\n")

    first = document.blocks[0]
    assert "".join(getattr(node, "value", "") for node in first.inlines) == "路径 C:\\"


def test_line_break_inside_a_list_item_keeps_one_item(tmp_path: Path) -> None:
    archive = _export(tmp_path, "%% 文档标题 题目\n\n# 一\n\n- 第一行\\\n  第二行\n- 下一项\n")
    xml = archive.read("word/document.xml").decode("utf-8")
    paragraphs = _paragraphs(xml)

    assert ("第一行第二行", 1) in paragraphs, paragraphs
    assert xml.count("<w:numPr>") == 2, "列表项逐条编号，段内换行不该多出一个编号"


def test_soft_wrap_warning_is_skipped_when_the_appearance_break_is_explicit() -> None:
    from md_to_word.utils.skill_utils import soft_wrap_issues

    assert soft_wrap_issues("上一行\\\n下一行\n") == []
    assert soft_wrap_issues("上一行  \n下一行\n") == []
    assert len(soft_wrap_issues("上一行\n下一行\n")) == 1


@pytest.mark.parametrize("marker", ["\\", "  "])
def test_break_at_the_end_of_the_document_does_not_crash(marker: str) -> None:
    """文档最后一行带换行标记时没有下一行可接，不能吞掉也不能崩。"""
    document = read_markdown(f"正文末行{marker}\n")

    assert len(document.blocks) == 1
