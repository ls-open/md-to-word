"""机器可读契约与结构化诊断。

契约（`--contract --json` / MCP `get_contract`）是 Agent 读的一屏事实：版本、路径、
预设指纹、样式词表、退出码、JSON 键。诊断（`diagnostics`）是给程序读的错误与提醒：
稳定 code、文件、行号。这两样都必须与真实运行同源，不能是手写的第二份名单。
"""

from __future__ import annotations

import json
from pathlib import Path

from md_to_word.cli import main
from md_to_word.contract import RESULT_JSON_KEYS, contract_payload
from md_to_word.pipeline import ExportOptions, run_export_pipeline


def _manuscript(tmp_path: Path, text: str, name: str = "m.md") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_contract_payload_comes_from_real_files() -> None:
    payload = contract_payload("zh")

    assert payload["version"]
    assert Path(payload["guides"]["agent"]).is_file()
    assert Path(payload["manuals"]["zh"]).is_file()

    for preset in payload["presets"]:
        path = Path(preset["path"])
        assert path.is_file()
        assert preset["sha256"] == __import__("hashlib").sha256(path.read_bytes()).hexdigest()

    ids = {p["id"] for p in payload["presets"]}
    assert {"zh-academic", "zh-tw-academic", "zh-report", "en-nature"} <= ids

    styles = {s["style"]: s for s in payload["styles"]}
    assert styles["Body Text"]["zh"] == "正文"
    assert styles["Body Text"]["en"] == "Body Text"
    assert styles["Heading 1"]["zh"] == "一级标题"

    assert set(payload["exit_codes"]) == {"0", "1", "2", "3"}
    assert payload["json_keys"] == list(RESULT_JSON_KEYS)


def test_contract_json_is_one_object_on_stdout(capsys) -> None:
    code = main(["--contract", "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["version"] == contract_payload("zh")["version"]


def test_json_result_keys_match_the_declared_contract(tmp_path: Path, capsys) -> None:
    manuscript = _manuscript(tmp_path, "# 引言\n\n正文。\n")

    code = main([str(manuscript), "--preset", "zh-academic", "--json",
                 "-o", str(tmp_path / "o.docx")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert tuple(payload) == RESULT_JSON_KEYS


def test_diagnostics_carry_code_file_and_line(tmp_path: Path, capsys) -> None:
    manuscript = _manuscript(tmp_path, "# 引言\n\n![图](missing.png)\n\n正文。\n")

    code = main([str(manuscript), "--preset", "zh-academic", "--json",
                 "-o", str(tmp_path / "o.docx")])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    missing = [d for d in payload["diagnostics"]
               if d["code"] == "gate.image.missing" and d["line"] == 3]
    assert missing, payload["diagnostics"]
    assert missing[0]["severity"] == "error"
    assert missing[0]["file"] == str(manuscript.resolve())
    assert missing[0]["message"] in payload["errors"]


def test_format_and_preset_conflict_is_rejected(tmp_path: Path) -> None:
    manuscript = _manuscript(tmp_path, "# 引言\n\n正文。\n")
    preset = Path(__file__).resolve().parents[1] / "src/md_to_word/presets/zh-academic.txt"

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "o.docx",
        format_path=preset,
        preset="zh-academic",
    ))

    assert result.returncode == 2  # 参数用法错误，不是稿件问题
    assert [d.code for d in result.diagnostics] == ["pipeline.format_preset_conflict"]
    assert not (tmp_path / "o.docx").exists()


def test_base_template_is_checked_before_rendering(tmp_path: Path, monkeypatch) -> None:
    """底模不存在时不该先排版再报错：前置条件必须在渲染前拦下。"""
    import md_to_word.pipeline as pipeline

    manuscript = _manuscript(tmp_path, "# 引言\n\n正文。\n")

    def _boom(*_args, **_kwargs):
        raise AssertionError("rendering must not start when the base template is missing")

    monkeypatch.setattr(pipeline, "build_template", _boom)

    result = pipeline.run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "o.docx",
        preset="zh-academic",
        base_template=tmp_path / "missing.docx",
        keep_until="目录",
    ))

    assert result.returncode == 1
    assert [d.code for d in result.diagnostics] == ["pipeline.base_missing"]
    assert not (tmp_path / "o.docx").exists()


def test_multiple_base_cut_points_are_rejected(tmp_path: Path) -> None:
    """三个切点同时给时不能静默挑一个：调用方会以为另一个生效了。"""
    from md_to_word.config import get_base_template_path

    manuscript = _manuscript(tmp_path, "# 引言\n\n正文。\n")

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "o.docx",
        preset="zh-academic",
        base_template=get_base_template_path(),
        cover_sections=1,
        keep_until="目录",
    ))

    assert result.returncode == 1
    assert [d.code for d in result.diagnostics] == ["pipeline.base_multi_cut"]
    assert not (tmp_path / "o.docx").exists()


def test_help_lists_every_builtin_preset() -> None:
    """帮助文本里的预设名不能停在旧清单：与目录分叉时，用户会以为只有那几个。"""
    from md_to_word.cli import build_parser
    from md_to_word.config import get_presets_dir

    # argparse 按终端宽度折行，预设名可能被拆到两行；去掉空白再比对。
    compact = "".join(build_parser("zh").format_help().split())
    for preset in get_presets_dir().glob("*.txt"):
        assert preset.stem in compact, preset.stem


def test_failed_export_keeps_diagnostics_in_sync_with_human_lists(tmp_path: Path) -> None:
    """失败时提醒仍在 diagnostics 里，就必须仍在 warnings/messages 里。"""
    manuscript = _manuscript(
        tmp_path, "# 一级\n\n### 三级\n\n![图](missing.png)\n"
    )

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "o.docx",
        preset="zh-academic",
    ))

    assert result.returncode == 1
    assert result.warnings, "标题跳级的提醒不该在被阻断时消失"
    for diag in result.diagnostics:
        if diag.severity == "warning":
            assert diag.message in result.warnings
        else:
            assert diag.message in result.errors
