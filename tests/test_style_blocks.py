"""段落样式行 `%% 样式名 内容`。

与 `# 标题` 同一条排布规则：符号在最前，内容跟在同行。单位是段落，不是区域——
一行即一段，没有闭合符号，也就没有「忘记闭合」。这里锁住认得对、不误伤、写错能报。
"""

from __future__ import annotations

import pytest

from md_to_word.preprocessor.blocks import (
    expand_style_lines,
    split_style_line,
    style_line_issues,
    style_line_names,
)
from md_to_word.validator.check import validate_manuscript


def test_splits_name_and_content() -> None:
    assert split_style_line("%% 摘要 本文提出一种方法") == ("摘要", "本文提出一种方法")
    assert split_style_line("%% 关键词 Word；排版") == ("关键词", "Word；排版")


def test_longest_name_wins() -> None:
    """`摘要标题` 必须先于 `摘要` 命中，否则会被拆成 `摘要` + 内容「标题 摘　要」。"""
    assert split_style_line("%% 摘要标题 摘　要") == ("摘要标题", "摘　要")


def test_non_style_lines_are_ignored() -> None:
    assert split_style_line("# 一 引言") is None
    assert split_style_line("% 不是样式行") is None
    assert split_style_line("%%摘要 缺空格") is None


def test_expands_to_pandoc_div() -> None:
    expanded = expand_style_lines("%% 摘要 本文提出一种方法\n")
    assert expanded == '::: {custom-style="Abstract"}\n本文提出一种方法\n:::\n'


def test_table_row_after_caption_is_untouched() -> None:
    text = "%% 表题 表 1 实验数据\n| 甲 | 乙 |\n"
    expanded = expand_style_lines(text)
    assert "| 甲 | 乙 |" in expanded
    assert expanded.count(":::") == 2


def test_code_fence_is_not_rewritten() -> None:
    text = "```\n%% 摘要 示例\n```\n"
    assert expand_style_lines(text) == text


@pytest.mark.parametrize(
    ("line", "fragment"),
    [
        ("%% 摘要", "没有正文"),
        ("%% 一级标题 引言", "标题类样式"),
        ("%% 乱写的名字 内容", "不认识样式名"),
        ("%% 摘要 第一行\n续行", "疑似软换行"),
    ],
)
def test_issues_are_reported(line: str, fragment: str) -> None:
    issues = style_line_issues(line)
    assert issues and any(fragment in why for _line, why in issues)


def test_unknown_name_fails_preflight(tmp_path) -> None:
    manuscript = tmp_path / "m.md"
    manuscript.write_text('---\ntitle: "t"\n---\n\n%% 乱写的名字 内容\n', encoding="utf-8")

    report = validate_manuscript(manuscript)
    assert not report.valid
    assert any("乱写的名字" in error for error in report.errors)


def test_old_fenced_form_is_rejected(tmp_path) -> None:
    """V2 只用段落样式行；旧包裹写法要明确拒绝，而不是当普通文本静默放过。"""
    manuscript = tmp_path / "m.md"
    manuscript.write_text(
        '---\ntitle: "t"\n---\n\n::: {custom-style="Abstract"}\n正文\n:::\n', encoding="utf-8"
    )

    report = validate_manuscript(manuscript)
    assert not report.valid
    assert any("旧写法" in error for error in report.errors)


def test_style_names_are_collected_for_template_check() -> None:
    names = style_line_names("%% 摘要 正文\n\n%% 表题 表 1\n")
    assert names == [(1, "Abstract"), (3, "Table Caption")]
