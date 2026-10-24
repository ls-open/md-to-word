"""错误路径不许甩 traceback，退出码不许跑出契约。

这些用例都是**真出现过**的：`-t` 传 PDF 炸 BadZipFile、`-o` 传目录炸 IsADirectoryError、
只读目录炸 PermissionError。技能与脚本靠退出码判断结果，所以每一条都钉在这里，
不再靠人工把命令挨个敲一遍。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from md_to_word.cli import main
from md_to_word.status import EXIT_ERROR, EXIT_OK, EXIT_PDF_SKIPPED, EXIT_USAGE

MANUSCRIPT = "%% 文档标题 A title\n\n# Section\n\nBody text.\n"


@pytest.fixture()
def workdir(tmp_path: Path) -> Path:
    (tmp_path / "ok.md").write_text(MANUSCRIPT, encoding="utf-8")
    return tmp_path


def _run(argv: list[str], capsys) -> tuple[int, str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, captured.out + captured.err


def test_output_pointing_at_a_directory_is_reported(workdir: Path, capsys) -> None:
    (workdir / "outdir").mkdir()

    code, output = _run([str(workdir / "ok.md"), "-o", str(workdir / "outdir")], capsys)

    assert code == EXIT_ERROR
    assert "Traceback" not in output
    assert "outdir" in output


@pytest.mark.skipif(os.geteuid() == 0, reason="root 无视目录权限")
def test_unwritable_output_directory_is_reported(workdir: Path, capsys) -> None:
    locked = workdir / "locked"
    locked.mkdir()
    os.chmod(locked, 0o500)
    try:
        code, output = _run([str(workdir / "ok.md"), "-o", str(locked / "x.docx")], capsys)
    finally:
        os.chmod(locked, 0o700)

    assert code == EXIT_ERROR
    assert "Traceback" not in output


def test_no_arguments_prints_a_usable_brief(capsys) -> None:
    """无参数不是用法报错，是一页能照着敲的简述（clig.dev 的建议）。"""
    code, output = _run([], capsys)

    assert code == EXIT_USAGE
    assert "md-to-word init" in output and "--guide" in output and "--help" in output


def test_skill_entry_survives_a_broken_manuscript(tmp_path: Path) -> None:
    """技能侧走 `scripts/export.sh`：稿件坏了也要是一句话，不是 traceback。"""
    (tmp_path / "bad.md").write_text("# Heading\n\n---\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "export.sh"), "bad.md"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )

    assert result.returncode == EXIT_ERROR
    assert "Traceback" not in (result.stdout + result.stderr)


@pytest.mark.parametrize(
    "doc",
    [
        "SKILL.md",
        "src/md_to_word/resources/guide.md",
        "src/md_to_word/resources/manual.md",
        "src/md_to_word/resources/manual_en.md",
    ],
)
def test_documented_exit_codes_match_the_code(doc: str) -> None:
    """四份入口文档必须写出 0/1/2/3 —— 少一个，Agent 就会误判一次失败。"""
    raw = (REPO_ROOT / doc).read_text(encoding="utf-8").splitlines()
    lines = [line.replace("**", "") for line in raw]  # 去掉加粗标记再匹配
    paragraph: list[str] = []
    for i, line in enumerate(lines):
        if "退出码：" in line or "Exit codes:" in line:
            for follow in lines[i:]:
                if not follow.strip():
                    break
                paragraph.append(follow)
            break
    joined = " ".join(paragraph)
    assert joined, f"{doc} 没有写退出码"
    for code in (EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_PDF_SKIPPED):
        assert f"`{code}`" in joined, f"{doc} 的退出码缺少 {code}：{joined}"


# ── 门禁分级、聚合与 `--json` 的一致性 ──────────────────────────────────

WRAPPED = "%% 文档标题 题目\n\n# 一\n\n第一行没有标点\n第二行没有标点\n第三行没有标点\n"


def test_warnings_are_grouped_into_one_line(workdir: Path, capsys) -> None:
    """一类提醒只出一条：一稿折行十处不该刷十行，行号照给。"""
    (workdir / "w.md").write_text(WRAPPED, encoding="utf-8")

    code, output = _run([str(workdir / "w.md"), "-o", str(workdir / "w.docx")], capsys)

    assert code == EXIT_OK
    assert output.count("折行段落") == 1, output
    for line_no in ("6", "7"):
        assert line_no in output, output


def test_warnings_reach_the_json_consumer(workdir: Path, capsys) -> None:
    """`--json` 的 `messages` 必须带提醒 —— 技能靠它转述，刮 stderr 是另一种脆弱。"""
    import json

    (workdir / "w.md").write_text(WRAPPED, encoding="utf-8")

    code = main([str(workdir / "w.md"), "-o", str(workdir / "w.docx"), "--json"])
    captured = capsys.readouterr()

    assert code == EXIT_OK
    payload = json.loads(captured.out)
    assert any("折行段落" in message for message in payload["messages"]), payload


def test_named_format_file_wins_over_other_txt(workdir: Path, capsys) -> None:
    """`format.txt` 是本工具的固定名：旁边多一个笔记文件也不该让导出失败。"""
    from md_to_word.pipeline import resolve_preset_path

    preset = resolve_preset_path("zh-academic")
    assert preset is not None
    (workdir / "format.txt").write_text(preset.read_text(encoding="utf-8"), encoding="utf-8")
    (workdir / "笔记.txt").write_text("随手记\n", encoding="utf-8")

    code, output = _run([str(workdir / "ok.md"), "-o", str(workdir / "o.docx")], capsys)

    assert code == EXIT_OK, output


@pytest.mark.parametrize(
    ("line", "expect"),
    [
        ("带 ==高亮== 的正文。", "高亮"),
        ("带 [文字]{.red} 的正文。", "行内属性"),
        ("行内公式 \\(a+b\\) 写法。", "行内公式"),
    ],
)
def test_markdown_leftovers_are_blocked(workdir: Path, capsys, line: str, expect: str) -> None:
    """不会渲染的写法要在导出前拦住 —— 否则连同符号一起印进 Word。"""
    (workdir / "d.md").write_text(f"%% 文档标题 题目\n\n# 一\n\n{line}\n", encoding="utf-8")

    code, output = _run([str(workdir / "d.md"), "-o", str(workdir / "d.docx")], capsys)

    assert code == EXIT_ERROR
    assert expect in output, output


def test_underline_span_is_still_supported(workdir: Path, capsys) -> None:
    """`{.underline}` 是引擎支持的写法，不能被「属性写法」这条门禁误伤。"""
    (workdir / "u.md").write_text(
        "%% 文档标题 题目\n\n# 一\n\n带 [文字]{.underline} 的正文。\n", encoding="utf-8"
    )

    code, output = _run([str(workdir / "u.md"), "-o", str(workdir / "u.docx")], capsys)

    assert code == EXIT_OK, output


# ── 公式：常见 LaTeX 写法与静默丢内容 ──────────────────────────────────

def test_aligned_environment_renders_as_a_real_table(workdir: Path, capsys) -> None:
    """`\\\\begin{aligned}` 是 AI 最常写的多行公式。转换器会漏出一个裸 `&`，产出非法 XML；
    这里断言它被转成 `split`（真正的 mtable），而不是崩掉或者只剩一行。

    产物断言的是 `m:eqArr` + 两行 `m:e`：对齐环境在 OOXML 里是 eqArr（ECMA-376），
    旧断言的 `m:m`/`m:mr` 是把它当普通矩阵——那样 `&` 只剩一列空格子，行间不真对齐。
    """
    import zipfile

    (workdir / "eq.md").write_text(
        "%% 文档标题 题目\n\n# 一\n\n$$ \\begin{aligned} y &= ax + b \\\\ z &= c \\end{aligned} $$\n",
        encoding="utf-8",
    )

    code, output = _run([str(workdir / "eq.md"), "-o", str(workdir / "eq.docx")], capsys)

    assert code == EXIT_OK, output
    xml = zipfile.ZipFile(workdir / "eq.docx").read("word/document.xml").decode("utf-8")
    assert "<m:eqArr>" in xml and xml.count("<m:e>") == 2, "多行公式没落成两行 eqArr"
    assert xml.count("<m:aln />") == 2 or xml.count("<m:aln/>") == 2, "`&` 没落成对齐点"


def test_unbalanced_equation_braces_are_blocked(workdir: Path, capsys) -> None:
    """花括号不配对时转换器不报错，只会静默丢内容（`\\frac{a}{b` 只剩 `ab`）。"""
    (workdir / "bad.md").write_text(
        "%% 文档标题 题目\n\n# 一\n\n$$ \\frac{a}{b $$\n", encoding="utf-8"
    )

    code, output = _run([str(workdir / "bad.md"), "-o", str(workdir / "bad.docx")], capsys)

    assert code == EXIT_ERROR
    assert "花括号" in output and "Traceback" not in output, output
