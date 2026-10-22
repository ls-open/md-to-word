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


def test_table_caption_and_note_attach_to_table() -> None:
    """表题/表注是表格的组成部分，不是平级段落——否则写出阶段还要再猜一次归属。"""
    doc = read_markdown(
        "%% 表题 表 1 数据\n\n| 甲 | 乙 |\n|:--|:--:|\n| 1 | 2 |\n\n%% 表注 注：示例\n"
    )
    tables = [b for b in doc.blocks if isinstance(b, Table)]
    assert len(tables) == 1
    assert tables[0].caption is not None
    assert tables[0].note is not None
    assert not [b for b in doc.blocks if isinstance(b, Paragraph)]


def test_table_alignments_and_widths() -> None:
    doc = read_markdown("| 甲 | 乙 | 丙 |\n|:--|:--:|------:|\n| 1 | 2 | 3 |\n")
    table = doc.blocks[0]
    assert table.alignments == ["left", "center", "right"]
    assert table.widths == [3.0, 4.0, 7.0]  # 分隔行短横线长短 → 相对列宽


def test_figure_carries_caption_and_width() -> None:
    doc = read_markdown("![图 1 架构](a.png){width=12cm}\n")
    fig = doc.blocks[0]
    assert isinstance(fig, Figure)
    assert fig.path == "a.png"
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
