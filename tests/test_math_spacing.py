"""公式里的间距，以及「转换后对账」。

`~` `\\,` `\\;` `\\quad` 是内容不是噪声：丢了之后 `0.893~1.092` 会在 Word 里粘成
`0.8931.092`，看上去像本来就这么写，导出也不报错。这里钉住两件事——间距真的落进
产物，以及转换器以后再把东西吞掉时会当场报错。
"""

from __future__ import annotations

import pytest

from md_to_word.transform.mathml2omml import UnsupportedMath, _Converter, latex_to_omml

M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def _texts(latex: str) -> list[str]:
    return [t.text or "" for n in latex_to_omml(latex) for t in n.iter(M + "t")]


@pytest.mark.parametrize("latex,space", [
    (r"0.893~1.092", "\u00a0"),   # 不换行空格
    (r"a\ b", "\u00a0"),          # 反斜杠空格，和 `~` 同一个字符
    (r"a\,b", "\u2009"),          # 细空格
    (r"a\:b", "\u2005"),          # 四分之一全角
    (r"a\;b", "\u2005"),
    (r"a\quad b", "\u2001"),      # 全身空格
])
def test_spacing_commands_reach_the_output(latex, space):
    assert _texts(latex)[1] == space


def test_qquad_is_two_em_quads():
    assert _texts(r"a\qquad b")[1] == "\u2001\u2001"


def test_a_literal_space_is_not_invented():
    """LaTeX 的数学模式里空格不排版，MathML 里本来就是没有——不能凭空补一个。"""
    assert _texts("a b") == ["a", "b"]


def test_negative_space_occupies_nothing():
    """`\\!` 是负间距，没有对应字符；它只让排版更紧，不是丢字。"""
    assert _texts(r"a\!b") == ["a", "b"]


@pytest.mark.parametrize("latex", [
    r"\hat{\theta}", r"\vec{v}", r"\overline{AB}",      # 重音落成组合字符
    r"\left( \frac{1}{2} \right)",                      # 括号落成 m:d 的属性
    r"\sum_{i=1}^{n} x_i", r"\begin{cases} 1 & x>0 \\ 0 & x\le 0 \end{cases}",
])
def test_reconciliation_does_not_fire_on_real_transformations(latex):
    """括号、求和号、重音都不是一对一落进 `m:t` 的，对账要认这些改写法。"""
    latex_to_omml(latex)


def test_dropped_characters_are_reported(monkeypatch):
    """以后哪个 handler 再 `return []` 吞掉内容，这里当场报错并点名。"""
    monkeypatch.setattr(_Converter, "_on_mn", lambda self, element: [])
    with pytest.raises(UnsupportedMath) as exc:
        latex_to_omml("1+2")
    assert "12" in str(exc.value)


def test_dropped_spacing_is_reported(monkeypatch):
    monkeypatch.setattr(_Converter, "_on_mspace", lambda self, element: [])
    with pytest.raises(UnsupportedMath) as exc:
        latex_to_omml(r"a\,b")
    assert "间距" in str(exc.value)
