"""`cases` 与 `aligned` 的结构性缺陷：括号要可伸缩，`&` 要落在对齐点上。

两个缺陷都不是"渲染得难看"，而是**OMML 里根本没有那个结构**：

1. `cases` 的左花括号原来是一个普通 `m:r`，字面印一个 `{`；Word 里它不会随两行内容
   长高，也不参与 delimiter 的伸缩。正确表示是 `m:d`（delimiter）包住整张表，
   `m:begChr m:val="{"`、`m:endChr m:val=""`——注意右括号是**空**的，`cases` 只有左括号。
   这也正是 `\\left\\{ … \\right.` 的表示，两者必须走同一条路径，不给 cases 单开一套。
2. `aligned` 里的 `&` 被 latex2mathml 拆成一列空格子（`<mi/>`），转换后变成一个空的
   `<m:r></m:r>`：既没有对齐作用，又在公式里留下一段看不见的垃圾。OOXML 的对齐点是
   `m:eqArr` 里某条 run 的 `m:rPr/m:aln`（ECMA-376：mtable 带对齐分组→eqArr，不带→m），
   所以这一列必须落成对齐点，而不是空 run。
"""

from __future__ import annotations

import pytest
from lxml import etree

from md_to_word.transform.mathml2omml import latex_to_omml

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"

CASES = r"\begin{cases} a & x>0 \\ b & x\le 0 \end{cases}"
ALIGNED = r"\begin{aligned} y &= ax + b \\ z &= c \end{aligned}"
SPLIT = r"\begin{split} y &= ax + b \\ z &= c \end{split}"


def _m(tag: str) -> str:
    return f"{{{M_NS}}}{tag}"


def _local_names(latex: str) -> list[str]:
    return [
        etree.QName(node).localname
        for top in latex_to_omml(latex)
        for node in top.iter()
    ]


def _find(latex: str, tag: str) -> list:
    return [
        node
        for top in latex_to_omml(latex)
        for node in top.iter(_m(tag))
    ]


def _delimiter(latex: str):
    """取公式里唯一的 `m:d`。"""
    found = _find(latex, "d")
    assert len(found) == 1, etree.tostring(found[0], encoding="unicode") if found else "没有 m:d"
    return found[0]


def _delimiter_chars(node) -> tuple[str | None, str | None]:
    beg = node.find(f"{_m('dPr')}/{_m('begChr')}")
    end = node.find(f"{_m('dPr')}/{_m('endChr')}")
    return (
        None if beg is None else beg.get(_m("val")),
        None if end is None else end.get(_m("val")),
    )


# ── 1. cases 的左花括号必须是 delimiter ────────────────────────────────
def test_cases_branch_is_a_delimiter() -> None:
    """cases → `m:d`，左括号 `{`、右括号为空，整张表在 `m:e` 里。"""
    top = latex_to_omml(CASES)
    assert len(top) == 1
    assert etree.QName(top[0]).localname == "d", etree.tostring(top[0], encoding="unicode")[:300]
    assert _delimiter_chars(top[0]) == ("{", "")

    # 两行条件表在 delimiter 的 m:e 里，且仍然是矩阵（列是列，不是对齐点）
    entry = top[0].find(_m("e"))
    assert entry is not None
    assert [etree.QName(node).localname for node in entry] == ["m"]
    rows = entry.findall(f"{_m('m')}/{_m('mr')}")
    assert len(rows) == 2
    # 每个格子是独立的 m:e，否则"条件 / 取值"两列会挤成一列
    for row in rows:
        assert len(row.findall(_m("e"))) == 2, etree.tostring(row, encoding="unicode")


def test_left_right_brace_uses_the_same_shape_as_cases() -> None:
    """`\\left\\{ … \\right.` 与 cases 产物同形——cases 走的就是这条路，没有单开一套。"""
    left_right = latex_to_omml(r"\left\{ a \right.")
    assert _delimiter_chars(left_right[0]) == _delimiter_chars(latex_to_omml(CASES)[0])
    assert _delimiter_chars(left_right[0]) == ("{", "")


def test_left_right_keeps_both_brackets() -> None:
    """有成对括号时两个字符都要留下，并且是同一个 delimiter。"""
    node = _delimiter(r"\left( \frac{a}{b} \right)")
    assert _delimiter_chars(node) == ("(", ")")
    # 括号里包的是分式，不是一个字面印出来的 "(" run
    assert node.find(f"{_m('e')}/{_m('f')}") is not None


def test_one_sided_delimiter_keeps_empty_side() -> None:
    """`\\left.` / `\\right.` 那一侧是空字符，不能变成 `None`（否则 Word 会画默认括号）。"""
    assert _delimiter_chars(_delimiter(r"\left. x \right|")) == ("", "|")
    assert _delimiter_chars(_delimiter(r"\left| x \right.")) == ("|", "")


# ── 2. aligned 的 `&` 是对齐点，不是空 run ─────────────────────────────
@pytest.mark.parametrize("latex", [ALIGNED, SPLIT])
def test_alignment_environment_becomes_eq_arr(latex: str) -> None:
    top = latex_to_omml(latex)
    assert len(top) == 1
    assert etree.QName(top[0]).localname == "eqArr", etree.tostring(top[0], encoding="unicode")[:300]
    assert len(top[0].findall(_m("e"))) == 2


@pytest.mark.parametrize("latex", [ALIGNED, SPLIT])
def test_ampersand_becomes_alignment_point(latex: str) -> None:
    """每一行都要有且只有一个对齐点，且落在 `&` 后面那条 run 上（`=` 开头的 run）。"""
    rows = latex_to_omml(latex)[0].findall(_m("e"))
    for row in rows:
        marks = row.findall(f".//{_m('aln')}")
        assert len(marks) == 1, etree.tostring(row, encoding="unicode")

        marked = [run for run in row.iter(_m("r")) if run.find(f"{_m('rPr')}/{_m('aln')}") is not None]
        assert len(marked) == 1
        assert marked[0].findtext(_m("t")) == "="


# ── 3. 不许留空 run ───────────────────────────────────────────────────
@pytest.mark.parametrize(
    "latex",
    [
        CASES,
        ALIGNED,
        SPLIT,
        r"\left\{ a \right.",
        r"\left. x \right|",
        r"\left( \frac{a}{b} \right)",
        r"\begin{cases} a & x>0 \\ b & \text{otherwise} \end{cases}",
    ],
)
def test_no_empty_math_run(latex: str) -> None:
    """空 `<m:r>` 在 Word 里是一个看不见但占位的框，多行公式里尤其明显。"""
    runs = _find(latex, "r")
    assert runs, "公式里一条 run 都没有"
    for run in runs:
        text = "".join(run.itertext())
        assert text.strip(), etree.tostring(run, encoding="unicode")


def test_multiline_display_math_is_not_reported_as_wrapped_prose() -> None:
    """`$$…$$` 里每行都是公式；多行公式以前会被「折行段落」提醒刷屏。"""
    from md_to_word.utils.skill_utils import soft_wrap_issues

    text = "# 一\n\n$$\n\\begin{cases}\na, & x>0 \\\\\nb, & x\\le 0\n\\end{cases}\n$$\n"
    assert soft_wrap_issues(text) == []
