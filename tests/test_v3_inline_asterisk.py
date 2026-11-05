"""tests/test_v3_inline_asterisk.py — 词内星号：立体化学记法、回归式与乘号（issue #15）。

两条相反的要求钉在同一个文件里：`(1*S*,2*R*)`、`4054.1*x*` 要出斜体；`2*3*4`、`a*b*c`
是乘号，星号原样印出，并且预检要提醒一句——落成字面星号不能是无声的。
"""

from __future__ import annotations

from pathlib import Path

from md_to_word.model.reader import read_markdown, unparsed_stars
from md_to_word.validator.check import literal_asterisk_issues, validate_manuscript


def _render(text: str) -> str:
    """把一行的行内节点渲染成 `<em>…</em>` 形态，便于整段比对。"""
    lines = []
    for block in read_markdown(text).blocks:
        parts = []
        for node in block.inlines:
            value = getattr(node, "value", None)
            if value is not None:
                parts.append(value)
            else:
                name = {"Emphasis": "em", "Strong": "strong"}[type(node).__name__]
                parts.append(f"<{name}>{_render_inner(node.children)}</{name}>")
        lines.append("".join(parts))
    return "\n".join(lines)


def _render_inner(nodes) -> str:
    out = []
    for node in nodes:
        value = getattr(node, "value", None)
        if value is not None:
            out.append(value)
        else:
            name = {"Emphasis": "em", "Strong": "strong"}[type(node).__name__]
            out.append(f"<{name}>{_render_inner(node.children)}</{name}>")
    return "".join(out)


def test_stereo_descriptors_and_coefficients_are_italic() -> None:
    """开符左边是数字不能再让整段强调作废：化学描述符与回归式都得出斜体。"""
    md = (
        "Dns-(1*S*,2*S*)-4 and Dns-(1*S*,2*R*)-4 are diastereomers.\n\n"
        "The calibration line was y = 4054.1*x* + 6499.2.\n\n"
        "Control: *S*-adenosylmethionine renders fine, and (4″*R*)-form also renders fine.\n"
    )
    assert _render(md).split("\n") == [
        "Dns-(1<em>S</em>,2<em>S</em>)-4 and Dns-(1<em>S</em>,2<em>R</em>)-4 are diastereomers.",
        "The calibration line was y = 4054.1<em>x</em> + 6499.2.",
        "Control: <em>S</em>-adenosylmethionine renders fine, and (4″<em>R</em>)-form also renders fine.",
    ]


def test_multiplication_asterisks_stay_literal() -> None:
    """两头都紧挨字母数字的是乘号：不许被吃成斜体（吃成斜体是产物上看不出来的静默错）。"""
    for expr in ("2*3*4", "a*b*c", "5*6*78", "(2*3)*4", "2*3*4*5"):
        assert _render(expr + "\n") == expr, expr


def test_significance_stars_and_escapes_stay_literal() -> None:
    """符号注的星号靠「开符后不能是空白」天然放过；`\\*` 明确要字面星号，也别多事。"""
    assert _render("注：* P<0.05，** P<0.01，*** P<0.001。\n") == "注：* P<0.05，** P<0.01，*** P<0.001。"
    assert _render(r"乘号写 2\*3\*4，立体写 (1\*S\*,2\*R\*)。" + "\n") == "乘号写 2*3*4，立体写 (1*S*,2*R*)。"


def test_code_and_math_are_not_residue() -> None:
    """代码与公式里的星号是逐字内容，残符判据不该把它们捞出来。"""
    assert not literal_asterisk_issues("见 `a*b*c` 与 $x*y*z$ 两处。")


def test_bold_run_is_never_read_as_italics() -> None:
    """`**` 里的星号是加粗的语法：从第二个星号起配对会「星号照印 + 中间变斜体」，两头都错。"""
    line = "x**B**y，a**b**c，word**bold**word"
    assert _render(line + "\n") == line
    issues = literal_asterisk_issues(line)
    assert len(issues) == 1 and "**B**" in issues[0][1]


def test_residue_reminder_fires_on_multiplication() -> None:
    """落成字面星号的乘号要提醒：行号 + 片段，且不阻断。"""
    issues = literal_asterisk_issues("正文 y = 2*3*4 到此。")
    assert len(issues) == 1
    line_no, snippet = issues[0]
    assert line_no == 1 and "2*3*4" in snippet


def test_residue_reminder_stays_quiet_where_it_should(tmp_path: Path) -> None:
    """解析掉的不报、符号注不报、转义不报、单独的星号也不报。"""
    for quiet in (
        "y = 4054.1*x* 与 (1*S*,2*R*)-体。",
        "注：* P<0.05，** P<0.01，*** P<0.001。",
        r"写成 2\*3\*4 就是字面星号。",
        "| 3*4 | 5*6 |",
    ):
        assert literal_asterisk_issues(quiet) == [], quiet

    md = tmp_path / "m.md"
    md.write_text("# 标题\n\n正文 y = 2*3*4 到此。\n", encoding="utf-8")
    report = validate_manuscript(md)
    assert report.valid, "词内乘号是合法写法，不能阻断导出"
    assert any("[星号未解析]" in w for w in report.warnings)


def test_emphasis_and_bold_nest() -> None:
    """斜体里可以含加粗，加粗里也可以含斜体（斜体的正文允许出现星号）。"""
    assert _render("*a **b** c*\n") == "<em>a <strong>b</strong> c</em>"
    assert _render("**a *b* c**\n") == "<strong>a <em>b</em> c</strong>"


def test_triple_star_boundary_is_loud() -> None:
    """加粗与斜体共用一段 `***` 仍切不开（要按 delimiter run 重写才行），但不能无声。"""
    for line in ("*a **b***", "**a *b***"):
        assert literal_asterisk_issues(line), line


def test_unparsed_stars_keeps_offsets() -> None:
    """残符串与原行等长：调用方要按同一组下标回原行取片段。"""
    for line in ("y = 2*3*4", r"写 2\*3\*4 与 `a*b`", "注：* P<0.05"):
        assert len(unparsed_stars(line)) == len(line)
