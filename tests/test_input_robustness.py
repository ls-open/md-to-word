"""输入鲁棒性：编码、消息语言、只校验、门禁失败不留产物。

这些不是新功能，而是「看起来能跑、实际出错方式很难查」的几处边界。每一条都对应
一个曾经会抛 traceback、误判语言或覆盖上一版成品的具体路径。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from md_to_word.cli import build_parser, contract_cheatsheet, main
from md_to_word.i18n import t
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.utils.textio import TextDecodeError, decode_text


def _manuscript(tmp_path: Path, text: str, name: str = "m.md") -> Path:
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path


def test_textio_handles_bom_utf16_gb18030_and_crlf() -> None:
    assert decode_text(b"\xef\xbb\xbf# Title", "x")[1] == "utf-8-sig"
    assert decode_text("# Title".encode("utf-16"), "x")[0] == "# Title"
    assert decode_text("中文正文".encode("gb18030"), "x")[0] == "中文正文"
    assert decode_text(b"a\r\nb\rc", "x")[0] == "a\nb\nc"


def test_textio_rejects_binary() -> None:
    with pytest.raises(TextDecodeError):
        decode_text(b"\x00\x00\x00\x00", "x")


def test_gbk_format_is_read_with_a_language_matched_warning(tmp_path: Path) -> None:
    manuscript = _manuscript(tmp_path, "# 引言\n\n中文正文。\n")
    preset = Path(__file__).resolve().parents[1] / "src/md_to_word/presets/zh-academic.txt"
    fmt = tmp_path / "format.txt"
    fmt.write_bytes(preset.read_text(encoding="utf-8").encode("gbk"))

    result = run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=tmp_path / "o.docx")
    )

    assert result.ok, result.errors
    assert result.lang == "zh"
    assert any("gb18030" in warning for warning in result.warnings), result.warnings


def test_utf16_english_manuscript_warns_in_english(tmp_path: Path) -> None:
    manuscript = tmp_path / "paper.md"
    manuscript.write_bytes("# Introduction\n\nEnglish body.\n".encode("utf-16"))

    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript,
            output_path=tmp_path / "o.docx",
            preset="en-nature",
        )
    )

    assert result.ok, result.errors
    assert result.lang == "en"
    assert any("not UTF-8" in warning for warning in result.warnings), result.warnings


def test_message_language_does_not_choose_the_default_preset(tmp_path: Path) -> None:
    """`--lang en` 只换报错语言：中文稿仍应选 zh-academic。"""
    manuscript = _manuscript(tmp_path, "# 引言\n\n这是一段中文正文。\n")

    result = run_export_pipeline(
        ExportOptions(
            input_path=manuscript,
            output_path=tmp_path / "o.docx",
            lang="en",
        )
    )

    assert result.ok, result.errors
    assert result.lang == "en"
    assert any("zh-academic" in message for message in result.messages), result.messages
    assert not any("en-nature" in message for message in result.messages), result.messages


def test_language_detection_ignores_code_urls_and_math() -> None:
    """中文技术稿里夹大段英文代码，默认预设仍应是中文。"""
    from md_to_word.i18n import resolve_lang

    code = "```python\n" + "print('hello world')\n" * 80 + "```"
    inline = " ".join("`english_code`" for _ in range(40))
    text = (
        "# 引言\n\n本方法讨论确定性排版，正文是中文。\n\n"
        f"{inline}\n\n{code}\n\n详见 https://example.com/english/only 与 $E=mc^2$。\n"
    )
    assert resolve_lang(text) == "zh"


def test_contract_points_chinese_readers_to_the_chinese_guide() -> None:
    assert "guide_zh.md" in contract_cheatsheet("zh")
    assert "guide_zh.md" not in contract_cheatsheet("en")
    assert "guide.md" in contract_cheatsheet("en")


def test_legacy_r_flag_is_gone() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["m.md", "-r", "format.txt"])


def test_validate_only_writes_no_docx(tmp_path: Path, capsys) -> None:
    manuscript = _manuscript(tmp_path, "# 引言\n\n正文。\n")
    out = tmp_path / "m.docx"

    code = main([str(manuscript), "--preset", "zh-academic", "--validate-only", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == payload["returncode"] == 0
    assert payload["output"] is None
    assert payload["warnings"] == []
    assert not out.exists()


def test_validate_only_reports_blocking_errors(tmp_path: Path, capsys) -> None:
    manuscript = _manuscript(
        tmp_path,
        "---\ntitle: Positionless title\n---\n\n# 引言\n\n正文。\n",
    )

    code = main([str(manuscript), "--preset", "zh-academic", "--validate-only", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == payload["returncode"] == 1
    assert payload["ok"] is False
    assert payload["errors"]
    assert not (tmp_path / "m.docx").exists()


def test_json_separates_warnings_from_messages(tmp_path: Path, capsys) -> None:
    manuscript = _manuscript(tmp_path, "# 一级\n\n### 三级\n\n正文。\n")

    code = main([
        str(manuscript), "--preset", "zh-academic", "--json",
        "-o", str(tmp_path / "o.docx"),
    ])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["warnings"], payload
    assert all(warning in payload["messages"] for warning in payload["warnings"])


def test_failed_gate_keeps_the_previous_output(tmp_path: Path, monkeypatch) -> None:
    """门禁失败时目标位置必须还是上一版成品，不能留一份半成品或坏文件。"""
    import md_to_word.pipeline as pipeline

    manuscript = _manuscript(tmp_path, "# 引言\n\n正文。\n")
    out = tmp_path / "o.docx"
    out.write_bytes(b"previous-good-build")

    monkeypatch.setattr(
        pipeline, "_postflight_error", lambda *_args, **_kwargs: "simulated gate failure"
    )
    result = pipeline.run_export_pipeline(
        ExportOptions(input_path=manuscript, output_path=out, preset="zh-academic")
    )

    assert result.returncode == 1
    assert out.read_bytes() == b"previous-good-build"
    assert not list(tmp_path.glob(".o.*.docx")), "临时候选产物没清理干净"


def test_encoding_fallback_message_is_bilingual() -> None:
    zh = t("textio.fallback", "zh", label="稿件", encoding="gb18030")
    en = t("textio.fallback", "en", label="manuscript", encoding="gb18030")
    assert "UTF-8" in zh and "UTF-8" in en
    assert "gb18030" in zh and "gb18030" in en
