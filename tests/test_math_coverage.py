"""常见 LaTeX 写法逐条过一遍：要么变成 OMML，要么一句话报错。

这些用例的来源是两次真实缺陷：`\\begin{aligned}` 因 `&` 漏成裸实体而抛 lxml 的 traceback，
`\\frac{a}{b` 因花括号不配对而静默渲染成 `ab`。两次都不是新写法不支持，而是**没人按构造
逐条试过**。

判据只有两条，都不看像素：
1. 能渲染的，产物里必须真有对应的 OMML 元素（不是被当成纯文本印出去）；
2. 不能渲染的，必须是 `UnsupportedMath`（一句话），不许是转换器自己的异常。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from md_to_word.transform.mathml2omml import latex_to_omml

# (名称, LaTeX, 产物里必须出现的 OMML 元素)
RENDERABLE = [
    ("fraction", r"\frac{a}{b}", "f"),
    ("superscript", r"x^{2}", "sSup"),
    ("subscript", r"x_{i}", "sSub"),
    ("sum", r"\sum_{i=1}^{n} x_i", "nary"),
    ("integral", r"\int_0^1 f(x)\,dx", "nary"),
    ("square root", r"\sqrt{x}", "rad"),
    ("greek", r"\alpha + \beta", "t"),
    ("accent", r"\hat{x} + \vec{v}", "acc"),
    ("matrix", r"\begin{matrix} a & b \\ c & d \end{matrix}", "m"),
    ("cases", r"\begin{cases} 1 & x>0 \\ 0 & x \le 0 \end{cases}", "m"),
    ("split", r"\begin{split} y &= ax + b \\ z &= c \end{split}", "m"),
    ("aligned", r"\begin{aligned} y &= ax + b \\ z &= c \end{aligned}", "m"),
    ("text", r"\text{其中 } x>0", "t"),
]


def _local_names(latex: str) -> list[str]:
    return [
        etree.QName(node).localname
        for top in latex_to_omml(latex)
        for node in top.iter()
    ]


@pytest.mark.parametrize(("name", "latex", "element"), RENDERABLE)
def test_common_constructs_render_to_omml(name: str, latex: str, element: str) -> None:
    assert element in _local_names(latex), f"{name} 没有落成 {element}"


def test_aligned_is_translated_not_silently_dropped() -> None:
    """`aligned` 要真的落成两行矩阵，而不是被吞掉或退化成一行。"""
    matrix = latex_to_omml(r"\begin{aligned} y &= ax + b \\ z &= c \end{aligned}")[0]
    rows = [child for child in matrix if etree.QName(child).localname == "mr"]

    assert len(rows) == 2, etree.tostring(matrix, encoding="unicode")[:300]


def test_unknown_mathml_still_fails_loudly() -> None:
    """不认识的 MathML 元素必须是一句话，而不是转换器自己的异常。"""
    from md_to_word.transform.mathml2omml import UnsupportedMath, mathml_to_omml

    unsupported = (
        '<math xmlns="http://www.w3.org/1998/Math/MathML">'
        "<menclose><mi>x</mi></menclose></math>"
    )
    with pytest.raises(UnsupportedMath):
        mathml_to_omml(unsupported)

    malformed = '<math xmlns="http://www.w3.org/1998/Math/MathML"><mi>&</mi></math>'
    with pytest.raises(UnsupportedMath):
        mathml_to_omml(malformed)
