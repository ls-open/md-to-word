"""结构化诊断与给人读的两条出口必须逐条一致，且 `code` / `file` / `line` 稳定可用。

`report.errors` / `report.warnings` 是既有契约，`report.diagnostics` 是程序入口；
同一条问题只产生一次，两个视图不能各说各话。
"""

from __future__ import annotations

from pathlib import Path

from md_to_word.validator.check import validate_manuscript

# 故意写错的稿件，行号按下面的布局固定：
#   6  ![](missing.png)       图片不存在
#   9  | 1 | 2                表格行缺行尾竖线
#   11 见 [[wiki note]]。     Obsidian WikiLink
#   13 脚注[^n1]。            脚注没有定义
#   15 ### 三级标题            标题跳级（提醒）
BAD = (
    "---\n"
    "---\n"
    "\n"
    "# 一 引言\n"
    "\n"
    "![](missing.png)\n"
    "\n"
    "| 甲 | 乙 |\n"
    "| 1 | 2\n"
    "\n"
    "见 [[wiki note]]。\n"
    "\n"
    "脚注[^n1]。\n"
    "\n"
    "### 三级标题\n"
)

CLEAN = "---\n---\n\n# 一 引言\n\n正文一段。\n"


def _report(tmp_path: Path):
    md = tmp_path / "manuscript.md"
    md.write_text(BAD, encoding="utf-8")
    return md, validate_manuscript(md)


def test_diagnostics_mirror_error_and_warning_lists(tmp_path):
    _, report = _report(tmp_path)

    assert report.errors
    assert report.warnings
    assert report.errors == [d.message for d in report.diagnostics if d.severity == "error"]
    assert report.warnings == [d.message for d in report.diagnostics if d.severity == "warning"]


def test_diagnostics_carry_codes_files_and_lines(tmp_path):
    md, report = _report(tmp_path)
    by_code: dict[str, list] = {}
    for diag in report.diagnostics:
        assert diag.code, f"诊断缺少 code: {diag!r}"
        assert diag.file == str(md)
        assert Path(diag.file).is_absolute()
        assert diag.line is None or isinstance(diag.line, int)
        by_code.setdefault(diag.code, []).append(diag)

    assert by_code["gate.image.missing"][0].line == 6
    assert by_code["gate.table.row_unclosed"][0].line == 9
    assert by_code["gate.wikilink"][0].line == 11
    assert by_code["gate.footnote.undefined"][0].line == 13
    assert by_code["gate.heading.level"][0].line == 15


def test_valid_manuscript_has_no_error_diagnostics(tmp_path):
    md = tmp_path / "clean.md"
    md.write_text(CLEAN, encoding="utf-8")
    report = validate_manuscript(md)

    assert report.valid
    assert report.errors == []
    assert [d for d in report.diagnostics if d.severity == "error"] == []
