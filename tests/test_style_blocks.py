"""`::: 摘要` 短写法的展开与校验。

投稿人不必记 `custom-style="Table Caption"` 这种带属性的围栏；短写法在主仓先还原成
Pandoc 的 fenced div，再由 Pandoc 负责段落包裹。这里锁住三件事：认得对、不误伤、写错能报。
"""

from __future__ import annotations

import pytest

from md_to_word.preprocessor.blocks import expand_style_blocks, resolve_style_alias, style_block_names
from md_to_word.validator.check import validate_manuscript


def test_resolves_chinese_and_english_names() -> None:
    assert resolve_style_alias("摘要") == "Abstract"
    assert resolve_style_alias("表格题注") == "Table Caption"
    assert resolve_style_alias("Keywords") == "Keywords"
    assert resolve_style_alias("乱写的名字") is None


def test_expands_short_form() -> None:
    text = "::: 摘要\n正文\n:::\n"
    assert expand_style_blocks(text) == '::: {custom-style="Abstract"}\n正文\n:::\n'


def test_leaves_attribute_form_untouched() -> None:
    text = '::: {custom-style="Table Caption"}\n表 1\n:::\n'
    assert expand_style_blocks(text) == text


def test_ignores_fences_inside_code_blocks() -> None:
    text = "```\n::: 摘要\n```\n::: 关键词\nx\n:::\n"
    expanded = expand_style_blocks(text)
    assert "::: 摘要" in expanded, "代码块里的示例不能被改写"
    assert '::: {custom-style="Keywords"}' in expanded


def test_unknown_name_is_reported_by_preflight(tmp_path) -> None:
    manuscript = tmp_path / "m.md"
    manuscript.write_text('---\ntitle: "t"\n---\n\n::: 乱写的名字\nx\n:::\n', encoding="utf-8")

    report = validate_manuscript(manuscript)
    assert not report.valid
    assert any("乱写的名字" in error for error in report.errors)


def test_short_form_counts_as_custom_style_for_template_check(tmp_path) -> None:
    """短写法也要参与「样式在不在模板里」的校验，否则会静默退回正文样式。"""
    manuscript = tmp_path / "m.md"
    manuscript.write_text('---\ntitle: "t"\n---\n\n::: 摘要\n正文\n:::\n', encoding="utf-8")
    names = [written for _line, written, resolved in style_block_names(manuscript.read_text(encoding="utf-8"))]
    assert names == ["摘要"]
