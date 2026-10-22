"""文档模型与「契约 Markdown → 模型」的读取器。

v3 的地基：模型定下来，写出器与读取器才能各自推进。这里锁住两件事——
模型能表达现有语法，且读取结果与源稿一一对应。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from md_to_word.model.document import (
    Citation, CodeBlock, CrossRef, Equation, Figure, FootnoteRef, Heading, ListBlock, Math,
    PageBreak, Paragraph, Quote, SectionBreak, Table, Text, Toc,
)
from md_to_word.model.reader import parse_inlines, read_markdown

DEMOS = Path(__file__).resolve().parents[1] / "demo"


def test_frontmatter_becomes_metadata() -> None:
    doc = read_markdown(
        '---\ntitle: "题目"\nauthor: [张三, 李四]\nbibliography: refs.bib\n'
        'csl: apa.csl\ncrossref:\n  eq-prefix: "式"\n  chapters: true\n---\n\n正文\n'
    )
    assert doc.meta.title == "题目"
    assert doc.meta.author == ["张三", "李四"]
    assert doc.meta.bibliography == "refs.bib"
    assert doc.meta.chapters is True
    assert doc.meta.crossref["eq-prefix"] == "式"


def test_heading_levels() -> None:
    doc = read_markdown("# 一\n\n## 1.1\n\n### 1.1.1\n")
    assert [b.level for b in doc.headings()] == [1, 2, 3]


def test_style_line_becomes_styled_paragraph() -> None:
    doc = read_markdown("%% 摘要 本文提出一种方法。\n")
    block = doc.blocks[0]
    assert isinstance(block, Paragraph)
    assert block.style == "Abstract"


def test_caption_is_a_sibling_paragraph_not_a_table_field() -> None:
    """题注是独立段落：Word 里它就是一个带样式的段落，合并会把作者写的两行捏成一行。"""
    doc = read_markdown(
        "%% 表题 表 1 数据\n\n| 甲 | 乙 |\n|:--|:--|\n| 1 | 2 |\n\n%% 表注 注：示例\n"
    )
    kinds = [type(b).__name__ for b in doc.blocks]
    assert kinds == ["Paragraph", "Table", "Paragraph"]
    assert doc.blocks[0].style == "Table Caption"
    assert doc.blocks[2].style == "Table Note"


def test_figure_caption_is_a_sibling_paragraph() -> None:
    """图片来源写法里只有路径、宽高与 alt；题注用 `%% 图片题注` 单独成段。"""
    doc = read_markdown("![](a.png){width=12cm}\n%% 图片题注 图 1 架构\n")
    assert [type(b).__name__ for b in doc.blocks] == ["Figure", "Paragraph"]
    figure = doc.blocks[0]
    assert figure.path == "a.png" and figure.width_cm == 12.0 and figure.alt == ""
    assert doc.blocks[1].style == "Image Caption"


def test_table_alignments_and_widths() -> None:
    doc = read_markdown("| 甲 | 乙 | 丙 |\n|:--|:--:|------:|\n| 1 | 2 | 3 |\n")
    table = doc.blocks[0]
    assert table.alignments == ["left", "center", "right"]
    assert table.widths == [3.0, 4.0, 7.0]  # 分隔行短横线长短 → 相对列宽


def test_figure_keeps_alt_text_separate() -> None:
    doc = read_markdown("![架构示意图](a.png){width=12cm}\n")
    fig = doc.blocks[0]
    assert isinstance(fig, Figure)
    assert fig.alt == "架构示意图"  # alt 只做无障碍替代文字，不再兼任题注
    assert fig.width_cm == 12.0


def test_equation_with_label() -> None:
    doc = read_markdown("$$E = mc^2$$ {#eq-a}\n")
    eq = doc.blocks[0]
    assert isinstance(eq, Equation)
    assert eq.label == "eq-a"
    assert "mc^2" in eq.latex


def test_lists_quote_and_code() -> None:
    doc = read_markdown("- 甲\n- 乙\n\n1. 一\n2. 二\n\n> 引用\n\n```python\nprint(1)\n```\n")
    kinds = [type(b).__name__ for b in doc.blocks]
    assert kinds == ["ListBlock", "ListBlock", "Quote", "CodeBlock"]
    assert doc.blocks[0].ordered is False
    assert doc.blocks[1].ordered is True
    assert isinstance(doc.blocks[3], CodeBlock)


def test_shortcodes() -> None:
    doc = read_markdown("{{< pagebreak >}}\n\n{{< toc 2 >}}\n\n{{< section 页码=小写罗马 起始=1 >}}\n")
    assert isinstance(doc.blocks[0], PageBreak)
    assert isinstance(doc.blocks[1], Toc) and doc.blocks[1].depth == 2
    assert isinstance(doc.blocks[2], SectionBreak) and doc.blocks[2].start == 1


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("**粗**", "Strong"),
        ("*斜*", "Emphasis"),
        ("`code`", "Code"),
        ("$x^2$", "Math"),
        ("~~删~~", "Strikethrough"),
        ("[下划线]{.underline}", "Underline"),
        ("^2^", "Superscript"),
        ("~2~", "Subscript"),
        ("[链接](https://a.b)", "Link"),
        ("[^1]", "FootnoteRef"),
        ("@eq-a", "CrossRef"),
        ("[@smith2024]", "Citation"),
    ],
)
def test_inline_kinds(text: str, kind: str) -> None:
    nodes = parse_inlines(text)
    assert [type(n).__name__ for n in nodes] == [kind]


def test_citation_details() -> None:
    [node] = parse_inlines("[@a2024; @b2023]")
    assert isinstance(node, Citation)
    assert [i.key for i in node.items] == ["a2024", "b2023"]


def test_narrative_reference_needs_bibliography_to_disambiguate() -> None:
    """`@key` 在 Pandoc 里既是叙述式文献引用又是交叉引用，只能靠 .bib 里的 key 区分。"""
    [unknown] = parse_inlines("@smith2024")
    assert isinstance(unknown, CrossRef)

    [known] = parse_inlines("@smith2024", citation_keys={"smith2024"})
    assert isinstance(known, Citation) and known.narrative is True


def test_footnote_definitions_are_collected() -> None:
    doc = read_markdown("正文[^1]\n\n[^1]: 注释文字\n")
    assert doc.footnotes and doc.footnotes[0].label == "1"


@pytest.mark.parametrize("demo", ["00_quickstart/hello", "01_chinese_thesis/thesis_sample", "02_modern_report/report_sample"])
def test_demo_documents_are_fully_expressible(demo: str) -> None:
    """模型必须能完整装下现有样例：不能有「读进来就丢」的内容。"""
    path = DEMOS / f"{demo}.md"
    doc = read_markdown(path.read_text(encoding="utf-8"))
    assert doc.blocks, "样例外没有解析出任何块"
    assert doc.headings(), f"{path.name} 没有解析出标题"
    assert not [b for b in doc.blocks if isinstance(b, Paragraph) and not b.inlines and b.style is None]


# ── 内联：星号与转义 ─────────────────────────────────────────────────────
# 学位论文的表格注里到处是 `注：* P<0.05，** P<0.01，*** P<0.001。`，这些星号是**字面内容**。
# 早期版本把它们当强调标记配对，导出的 Word 里星号整段消失——内容丢了，却没有任何报错。

def _text_of(nodes) -> str:
    def walk(node):
        if isinstance(node, Text):
            return node.value
        children = getattr(node, "children", ())
        return "".join(walk(c) for c in children)

    return "".join(walk(n) for n in nodes)


def test_significance_asterisks_stay_literal() -> None:
    line = "注：* P<0.05，** P<0.01，*** P<0.001。"
    nodes = parse_inlines(line)
    assert _text_of(nodes) == line
    assert all(isinstance(n, Text) for n in nodes), "星号不该被配对成强调"


def test_asterisk_runs_after_number_stay_literal() -> None:
    nodes = parse_inlines("（+0.054* 与 +0.079**；K=9）")
    assert "+0.079**；" in _text_of(nodes)


def test_backslash_escape_keeps_literal_asterisk() -> None:
    nodes = parse_inlines(r"−0.171\*\*\*")
    assert _text_of(nodes) == "−0.171***"
    assert all(isinstance(n, Text) for n in nodes)


def test_real_emphasis_still_works() -> None:
    nodes = parse_inlines("**创新点一：** 说明")
    assert type(nodes[0]).__name__ == "Strong"
    assert _text_of([nodes[0]]) == "创新点一："


def test_triple_asterisk_is_bold_italic() -> None:
    node = parse_inlines("***粗斜体***")[0]
    assert type(node).__name__ == "Strong"
    assert type(node.children[0]).__name__ == "Emphasis"


def test_code_span_keeps_backslashes() -> None:
    node = parse_inlines(r"`a\*b`")[0]
    assert node.value == r"a\*b"


# ── 前置区里的摘要与关键词 ──────────────────────────────────────────────
# 正规写法在正文（`%% 摘要`，位置可管），但存量 Pandoc 稿件都写在 YAML 里。
# 读取器不接这两项，整段摘要会静默消失——这是最贵的一种丢失。

def test_yaml_abstract_and_keywords() -> None:
    doc = read_markdown(
        '---\ntitle: "题目"\nabstract: |\n  第一段。\n\n  第二段。\n'
        'keywords:\n  - 甲\n  - 乙\nreference-section-title: 参考文献\n---\n\n正文\n'
    )
    assert doc.meta.abstract == ["第一段。", "第二段。"]
    assert doc.meta.keywords == ["甲", "乙"]
    assert doc.meta.reference_section_title == "参考文献"


def test_yaml_keywords_as_string_are_split() -> None:
    doc = read_markdown('---\nkeywords: "甲；乙，丙"\n---\n\n正文\n')
    assert doc.meta.keywords == ["甲", "乙", "丙"]
