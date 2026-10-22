"""新旧校验器的门禁一致性。

V2 把 `scripts/check_md.py` 重写成 `md_to_word.validator.check` 时，漏掉了四道门禁
（结构样式缺失、图片宽度超过版心、`\\tag{}` 公式编号、custom-style 与模板比对），
而两条流水线当时各走一半：`export.sh` 用旧的，`python -m md_to_word` 用新的。

这里用同一批违规稿件喂两个校验器，断言「拦不拦」的结论一致。比对的是判定，
不是文案——文案各有各的写法，判定必须只有一套。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
LEGACY_CHECK = REPO_ROOT / "scripts" / "check_md.py"
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"
FIGURE = REPO_ROOT / "demo" / "01_chinese_thesis" / "figures" / "qa_pipeline.png"

BASE_YAML = '---\ntitle: "门禁对照测试"\n---\n\n# 一 引言\n\n正文一段。\n'


def _requirements_without(*rows: str) -> str:
    """内置预设删掉指定前缀的行——模拟「要求文件漏声明某结构」。"""
    kept = [
        line
        for line in PRESET.read_text(encoding="utf-8").splitlines()
        if not any(line.startswith(row) for row in rows)
    ]
    return "\n".join(kept) + "\n"


# name -> (稿件正文, 要从预设里删掉的行前缀（None=不给要求文件）, 期望是否拦)
CASES = {
    "clean": (BASE_YAML, None, False),
    "table_without_style_rows": (
        BASE_YAML
        + '\n::: {custom-style="Table Caption"}\n表 1 测试\n:::\n\n| 甲 | 乙 |\n|:--|:--|\n| 1 | 2 |\n',
        ("表格：", "表头："),
        True,
    ),
    "latex_tag": (
        BASE_YAML + "\n$$E = mc^2 \\tag{1}$$\n",
        None,
        True,
    ),
    "image_wider_than_text_block": (
        BASE_YAML + "\n![图 1 测试](figures/qa_pipeline.png){width=30cm}\n",
        (),  # 版心要从要求文件算，故必须给文件，但不删任何行
        True,
    ),
    "citation_without_bibliography": (
        BASE_YAML + "\n见 [@smith2024]。\n",
        None,
        True,
    ),
    "crossref_without_bibliography": (
        '---\ntitle: "门禁对照测试"\ncrossref:\n  eq-prefix: "式"\n  fig-prefix: "图"\n'
        '  tbl-prefix: "表"\n---\n\n# 一 引言\n\n$$E = mc^2$$ {#eq-a}\n\n见 @eq-a。\n',
        None,
        False,
    ),
    "undefined_crossref": (
        '---\ntitle: "门禁对照测试"\ncrossref:\n  eq-prefix: "式"\n---\n\n# 一 引言\n\n见 @eq-missing。\n',
        None,
        True,
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_gate_parity(name: str, tmp_path: Path) -> None:
    body, dropped_rows, expected_blocked = CASES[name]
    uses_requirements = dropped_rows is not None
    (tmp_path / "manuscript.md").write_text(body, encoding="utf-8")
    (tmp_path / "figures").mkdir(exist_ok=True)
    if FIGURE.exists():
        shutil.copy(FIGURE, tmp_path / "figures" / "qa_pipeline.png")

    requirements = tmp_path / "requirements.txt"
    if uses_requirements:
        requirements.write_text(_requirements_without(*dropped_rows), encoding="utf-8")

    command = [sys.executable, str(LEGACY_CHECK), str(tmp_path / "manuscript.md")]
    if uses_requirements:
        command += ["-r", str(requirements)]
    legacy = subprocess.run(command, capture_output=True, text=True)
    legacy_blocked = legacy.returncode != 0

    report = validate_manuscript(
        tmp_path / "manuscript.md",
        spec_path=requirements if uses_requirements else None,
    )

    assert legacy_blocked == expected_blocked, (
        f"旧校验器判定与预期不符：{legacy.stdout}\n{legacy.stderr}"
    )
    assert report.valid is not legacy_blocked, (
        f"新旧校验器判定不一致（旧={'拦' if legacy_blocked else '放'}，"
        f"新={'拦' if not report.valid else '放'}）：{report.errors}"
    )
