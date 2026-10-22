"""面向用户的消息双语。

判据不是"每条都有英文"，而是：**同一份稿件，中文用户与英文用户读到的进度与结论
等价**，且不会因为 `%% 表题` 这类词表写法把英文稿认成中文稿。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from md_to_word.cli import build_parser
from md_to_word.i18n import _MESSAGES, SUPPORTED, resolve_lang, t

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("key", sorted(_MESSAGES))
def test_every_message_has_both_languages(key: str) -> None:
    zh, en = _MESSAGES[key]
    assert zh.strip() and en.strip(), f"{key} 缺一边"
    assert zh != en, f"{key} 中英两栏一模一样，八成是忘了翻"


def test_messages_format_without_keyword_errors() -> None:
    """带占位符的条目必须能被格式化——少一个参数会在导出中途炸掉。"""
    samples = {"path": "/tmp/x", "name": "zh", "dir": "/tmp", "reason": "r", "count": 1, "sample": "s"}
    for key, (zh, en) in _MESSAGES.items():
        for text in (zh, en):
            text.format(**samples)  # 多余的 kwargs 不会报错，缺参才会


def test_language_follows_the_manuscript() -> None:
    assert resolve_lang("这是一份中文稿件。") == "zh"
    assert resolve_lang("This is an English manuscript.") == "en"
    # 英文稿里出现中文样式名（词表写法）不算中文稿
    assert resolve_lang("%% 表题 Table 1\n\n# Introduction\n\nEnglish body.\n") == "en"


def test_language_override_wins() -> None:
    assert resolve_lang("中文正文", "en") == "en"
    assert resolve_lang("English body", "zh") == "zh"
    assert resolve_lang("English body", "auto") == "en"


def test_cli_help_follows_the_manuscript(tmp_path: Path) -> None:
    zh = tmp_path / "zh.md"
    zh.write_text('---\ntitle: "题目"\n---\n\n# 一 引言\n\n中文正文一段。\n', encoding="utf-8")
    en = tmp_path / "en.md"
    en.write_text('---\ntitle: "T"\n---\n\n# Introduction\n\nEnglish body.\n', encoding="utf-8")

    from md_to_word.cli import _message_lang

    assert _message_lang([str(zh)]) == "zh"
    assert _message_lang([str(en)]) == "en"
    assert _message_lang([str(zh), "--lang", "en"]) == "en"


def test_parser_language_switches_every_help_line() -> None:
    english = build_parser("en").format_help()
    chinese = build_parser("zh").format_help()
    assert "Compile Markdown into publication-ready Word" in english
    assert "现代学术 Markdown" in chinese
    assert "现代学术 Markdown" not in english


def test_reminder_is_localized_end_to_end(tmp_path: Path) -> None:
    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    manuscript = tmp_path / "m.md"
    manuscript.write_text('---\ntitle: "T"\n---\n\n# Introduction\n\nEnglish body.\n', encoding="utf-8")
    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=tmp_path / "o.docx", preset="en-nature")
    )
    assert result.returncode == 0, result.errors
    assert result.lang == "en"
    assert any("Reminder: open the .docx" in m for m in result.messages), result.messages
