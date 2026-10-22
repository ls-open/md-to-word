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


def test_bad_template_is_a_sentence_not_a_traceback(workdir: Path, capsys) -> None:
    (workdir / "fake.docx").write_text("not a zip", encoding="utf-8")

    code, output = _run([str(workdir / "ok.md"), "-t", str(workdir / "fake.docx")], capsys)

    assert code == EXIT_ERROR
    assert "Traceback" not in output
    assert "fake.docx" in output


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
    (tmp_path / "bad.md").write_text("# Heading\n\nOpen **bold across\nlines**.\n", encoding="utf-8")

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
