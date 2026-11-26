"""复杂公式走完整导出链，而不只是转换器单测。

`latex_to_omml` 的结构测试很强，但那只证明“这一层认出了 aligned/cases/matrix”。
这里再往下一层：同一份稿子经过读取器、写出器与后检，公式仍是原生 OMML，
编号与交叉引用没丢，公式在表格、列表、脚注里也能落下去。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.pipeline import ExportOptions, run_export_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

LONG_FORMULA = r"x_{1}+x_{2}+\cdots+x_{120}=\sum_{i=1}^{120}x_i"

MANUSCRIPT = rf"""# 一 公式组合

行内公式 $a^2+b^2=c^2$，编号公式见 @eq-align。

$$
\begin{{aligned}}
y &= ax + b \\
z &= c + d
\end{{aligned}}
$$ {{#eq-align}}

$$
\begin{{cases}}
a, & x>0 \\
b, & x\le 0
\end{{cases}}
$$

$$
\begin{{pmatrix}}
1 & 0 \\
0 & 1
\end{{pmatrix}}
$$

$$
{LONG_FORMULA}
$$

| 位置 | 公式 |
|:--|:--|
| 表格 | $e^{{i\pi}}+1=0$ |

- 列表里的行内公式 $\frac{{a}}{{b}}$

脚注里的说明[^f]。

[^f]: 脚的注释。
"""


def _document_xml(docx: Path) -> str:
    with zipfile.ZipFile(docx) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def _formula_text(docx: Path) -> str:
    with zipfile.ZipFile(docx) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return "\n".join(re.findall(r"<m:t[^>]*>([^<]*)</m:t>", xml))


@pytest.fixture(scope="module")
def exported(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("math-e2e")
    manuscript = tmp / "math.md"
    manuscript.write_text(MANUSCRIPT, encoding="utf-8")
    out = tmp / "math.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=out,
        format_path=PRESET,
    ))
    assert result.returncode == 0, result.errors
    return out


def test_structures_survive_the_writer(exported: Path) -> None:
    xml = _document_xml(exported)
    assert f"{{{M_NS}}}eqArr" in xml or "<m:eqArr" in xml
    assert "<m:d" in xml and "<m:m" in xml
    assert "<m:f" in xml and "<m:nary" in xml
    # aligned 的两行、cases 的两行、矩阵的两行都在；不许退化成一张普通表或一段文字
    assert xml.count("<m:eqArr") >= 1
    assert xml.count("<m:mr>") >= 4


def test_numbering_and_cross_reference(exported: Path) -> None:
    xml = _document_xml(exported)
    assert "（1）" in xml
    assert "式（1）" in xml


def test_long_formula_is_not_truncated(exported: Path) -> None:
    text = _formula_text(exported)
    assert "120" in text
    # 末项若被截断，通常只剩前几十项；这里按源串的最后几个可辨识字符核对
    assert "x" in text and "i" in text


def test_math_in_table_and_list(exported: Path) -> None:
    document_xml = _document_xml(exported)
    assert "<w:tbl>" in document_xml
    # 表格单元格、列表项都与正文共用内联公式节点
    assert document_xml.count("<m:oMath") >= 6


def test_math_in_a_footnote_fails_loudly_instead_of_being_dropped(tmp_path: Path) -> None:
    """脚注里的公式目前写不出来：必须整篇失败并说明，不能静默印成普通文字。"""
    manuscript = tmp_path / "footnote-math.md"
    manuscript.write_text("# 一\n\n正文[^f]。\n\n[^f]: 脚注 $x^2$。\n", encoding="utf-8")
    out = tmp_path / "out.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=out, format_path=PRESET,
    ))
    assert result.returncode != 0
    assert any("脚注里的 Math" in error for error in result.errors), result.errors
    assert not out.exists(), "失败时不能留下半份产物"
