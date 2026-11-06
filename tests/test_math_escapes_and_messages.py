"""行内公式的转义、汉字紧邻标记、以及报错里说不清原因的那几处。

三类失效都在预检之后：内容悄悄丢掉、报错指错原因、或者只剩一对空括号。
"""

from __future__ import annotations

import pytest

from md_to_word.model.document import CrossRef, Math
from md_to_word.model.reader import read_markdown
from md_to_word.transform.mathml2omml import UnsupportedMath, latex_to_omml
from md_to_word.utils.skill_utils import citation_key_issues, undefined_crossref_issues
from md_to_word.writer.docx_writer import _snippet

ESCAPES = (r"\%", r"\&", r"\_", r"\{", r"\}", r"\$", r"\#")


def _first_math(text: str) -> str:
    for block in read_markdown(text).blocks:
        for node in getattr(block, "inlines", ()):
            if isinstance(node, Math):
                return node.latex
    raise AssertionError(f"没解析出公式：{text!r}")


@pytest.mark.parametrize("escape", ESCAPES)
def test_inline_math_keeps_the_backslash(escape):
    """公式段不参与 Markdown 的转义保护：反斜杠原样留给 LaTeX。"""
    assert _first_math(f"行内：$a{escape}b$") == f"a{escape}b"


def _equation_latex(text: str) -> str:
    """独立公式走块级解析，节点类型与行内公式不同。"""
    block = read_markdown(text).blocks[0]
    return block.latex


def _render(latex: str) -> str:
    parts = []
    for element in latex_to_omml(latex):
        parts.extend(node.text for node in element.iter()
                     if node.tag.endswith("}t") and node.text)
    return "".join(parts)


@pytest.mark.parametrize("escape", ESCAPES)
def test_inline_and_display_agree(escape):
    """两条路径的产物必须一致——不一致本身就是这个 bug 最容易漏过的原因。"""
    inline = _render(_first_math(f"行内 $a{escape}b$"))
    display = _render(_equation_latex(f"$$a{escape}b$$"))
    assert inline == display, (escape, inline, display)
    assert not any(0xE000 <= ord(c) <= 0xF8FF for c in inline), f"{escape}: 私有区字符进成稿了"


def test_crossref_needs_no_space_after_cjk():
    """「由@eq-1 可知」是中文里的自然写法，`@` 前不要求空格。"""
    for block in read_markdown("由@eq-1 可知。").blocks:
        targets = [n.target for n in getattr(block, "inlines", ()) if isinstance(n, CrossRef)]
        assert targets == ["eq-1"], targets


def test_cjk_swallowed_into_key_says_why():
    """`@eq-1可知` 会把汉字并进 key：报错要指出是缺了空格，而不是让人去查标签名。"""
    issues = undefined_crossref_issues("由@eq-1可知。\n", lang="zh")
    assert issues, "应当报出缺失的交叉引用"
    assert "空格" in issues[0][1], issues[0][1]


def test_cjk_swallowed_into_citation_key_says_why():
    issues = citation_key_issues("见 @smith2020等 的研究。\n", {"other"}, lang="zh")
    assert issues and "空格" in issues[0][1], issues


def test_empty_exception_message_falls_back_to_class_name():
    """latex2mathml 的异常 `str()` 全是空串：报错不能因此只剩一对空括号。"""
    with pytest.raises(UnsupportedMath) as caught:
        latex_to_omml(r"c s^{*}^{2}/[2(1-T)]=L")
    assert "DoubleSuperscriptsError" in str(caught.value), str(caught.value)


def test_long_formula_snippet_marks_the_cut():
    """硬切会让切口落在 token 中间，看起来像公式本身少了括号。"""
    long = r"c s^{*}^{2}/[2(1-T)]=L+\alpha_{ij}\beta^{2}/\gamma_{k}"
    cut = _snippet(long, 30)
    assert cut.endswith("…"), cut
    assert _snippet(r"E=mc^2", 30) == r"E=mc^2"
