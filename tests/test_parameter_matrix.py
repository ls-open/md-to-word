"""参数组合的冒烟矩阵：单点测试各自过，不代表组合也过。

这里只放最容易互相影响的几组：行距 × 公式结构 × 表格形状 × CSL × 图片宽度 ×
纸张/装订线/镜像。每组都走完整的预检、模板生成、写出与防丢检查；任何一组报错，
都说明某个组合下的契约、几何或内容检查出了问题。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from md_to_word.pipeline import ExportOptions, run_export_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")
IMAGE = REPO_ROOT / "tests" / "fixtures" / "images" / "tiny.png"

BIB = """@article{ref1,
  author = {张三 and 李四},
  title = {组合测试文献},
  journal = {测试学报},
  year = {2024},
}
"""

FORMULAS = {
    "single": "$$a=b$$ {#eq-x}",
    "cases": "$$\n\\begin{cases}\na=b+c \\\\\nd=e+f \\\\\ng=h+i\n\\end{cases}\n$$ {#eq-x}",
    "matrix": "$$\n\\begin{pmatrix}\n1 & 2 & 3 \\\\\n4 & 5 & 6 \\\\\n7 & 8 & 9\n\\end{pmatrix}\n$$ {#eq-x}",
    "long": "$$a_1+b_2+c_3+d_4+e_5+f_6+g_7+h_8+i_9+j_{10}+k_{11}+l_{12}+m_{13}+n_{14}+o_{15}+p_{16}+q_{17}+r_{18}+s_{19}+t_{20}=0$$ {#eq-x}",
}

TABLES = {
    "2col": "| 名称 | 数值 |\n|:--|--:|\n| 甲 | 1 |\n| 乙 | 2 |",
    "8col": (
        "| 一 | 二 | 三 | 四 | 五 | 六 | 七 | 八 |\n"
        "|:--|--:|:--|--:|:--|--:|:--|--:|\n"
        "| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |"
    ),
    "narrow": (
        "| 一 | 二 | 三 | 四 | 五 | 六 | 七 | 八 |\n"
        "|:-|--:|:-|--:|:-|--:|:-|--:|\n"
        "| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |"
    ),
}

CASES = [
    ("exact-cases-8col-numeric", "行距20磅", "cases", "8col", "numeric", "width=50%", "A4", None, None),
    ("single-matrix-narrow-author", "行距1.0倍", "matrix", "narrow", "author-date", None, "Letter", "1cm", "on"),
    ("1.3-long-2col-numeric-overwide", "行距1.3倍", "long", "2col", "numeric", "width=25cm", "A4", None, None),
    ("min20-cases-8col-author", "行距最小值20磅", "cases", "8col", "author-date", "width=8cm", "A4", "1cm", None),
    ("1.5-single-narrow-numeric", "行距1.5倍", "single", "narrow", "numeric", "width=50%", "Letter", None, "on"),
    ("exact-matrix-2col-author", "行距20磅", "matrix", "2col", "author-date", None, "A4", "1cm", "on"),
]


def _format(spacing: str, page: str, gutter: str | None, mirror: str | None) -> str:
    lines: list[str] = []
    for line in PRESET.splitlines():
        if line.startswith("正文："):
            line = re.sub(r"行距\S+", spacing, line, count=1)
        if line.startswith("纸张："):
            lines.append(f"纸张：{page}")
            if gutter:
                lines.append(f"装订线：{gutter}")
            if mirror:
                lines.append("对称页边距：开")
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


@pytest.mark.parametrize(
    ("name", "spacing", "formula", "table", "csl", "width", "page", "gutter", "mirror"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_parameter_combinations_export(
    tmp_path: Path,
    name: str,
    spacing: str,
    formula: str,
    table: str,
    csl: str,
    width: str | None,
    page: str,
    gutter: str | None,
    mirror: str | None,
) -> None:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    (tmp_path / "format.txt").write_text(
        _format(spacing, page, gutter, mirror), encoding="utf-8"
    )
    width_attr = f"{{{width}}}" if width else ""
    manuscript = (
        "---\n"
        "bibliography: refs.bib\n"
        f"csl: chinese-gb7714-2015-{csl}.csl\n"
        "crossref:\n  chapters: true\n"
        "---\n\n"
        "# 一 组合\n\n"
        "正文引用 [@ref1]，公式见 @eq-x。脚注[^1]。\n\n"
        f"{FORMULAS[formula]}\n\n"
        "%% 表题 **表 1** 组合表\n\n"
        f"{TABLES[table]}\n\n"
        "%% 表注 注：组合测试。\n\n"
        f"![图]({IMAGE}){width_attr}\n\n"
        "[^1]: 脚注引文 [@ref1]。\n\n"
        "## 1.1 小节\n\n"
        "结尾。\n"
    )
    (tmp_path / "m.md").write_text(manuscript, encoding="utf-8")

    out = tmp_path / "out.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=tmp_path / "m.md",
        output_path=out,
        format_path=tmp_path / "format.txt",
        check_md=True,
    ))
    assert result.returncode == 0, (name, result.errors, result.diagnostics)
    assert out.is_file()
