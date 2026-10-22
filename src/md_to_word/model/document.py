"""md_to_word.model.document — 文档模型（v3 的地基）。

这一层只描述「文档是什么」，不描述「怎么写成 OOXML」，也不描述「格式要求长什么样」。
三层的关系：

    契约 Markdown  --reader-->  文档模型  --writer-->  OOXML
                                  ↑
                          requirements.txt（样式参数）

模型的有意取舍：
- 段落带的是 **Word 样式名**（`Abstract`），不是用户写的语义名（`摘要`）。语义名到样式名的
  映射属于格式契约层，在读取阶段就解掉，写入阶段不再做判断。
- 表题、表注**挂在表格上**，不作为独立段落存在。它们是表格的组成部分，拆成三个平级段落，
  写入时就必须再猜一次谁属于谁。
- 引文与交叉引用分成两种内联节点：`Citation` 走文献库，`CrossRef` 走稿内标签。二者在
  Pandoc 里共用 `@` 语法，但语义完全不同，模型里不合并。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union


# ── 内联层 ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Text:
    """纯文本。"""

    value: str


@dataclass(frozen=True)
class Strong:
    children: tuple["Inline", ...]


@dataclass(frozen=True)
class Emphasis:
    children: tuple["Inline", ...]


@dataclass(frozen=True)
class Strikethrough:
    children: tuple["Inline", ...]


@dataclass(frozen=True)
class Underline:
    children: tuple["Inline", ...]


@dataclass(frozen=True)
class Code:
    """行内代码，落 VerbatimChar。"""

    value: str


@dataclass(frozen=True)
class Superscript:
    children: tuple["Inline", ...]


@dataclass(frozen=True)
class Subscript:
    children: tuple["Inline", ...]


@dataclass(frozen=True)
class Math:
    """行内公式，LaTeX 原文。"""

    latex: str


@dataclass(frozen=True)
class Link:
    children: tuple["Inline", ...]
    url: str


@dataclass(frozen=True)
class CitationItem:
    """一条引文：key 加上可选的页码/前缀/后缀，以及「只出年份」标记。"""

    key: str
    prefix: str = ""
    locator: str = ""
    suffix: str = ""
    suppress_author: bool = False


@dataclass(frozen=True)
class Citation:
    """文献引用。narrative=True 表示 `@key` 叙述式（作者作句子主语）。"""

    items: tuple[CitationItem, ...]
    narrative: bool = False


@dataclass(frozen=True)
class CrossRef:
    """稿内交叉引用（`@eq-x`）。与文献引用是两回事，不合并。"""

    target: str


@dataclass(frozen=True)
class FootnoteRef:
    """脚注引用；正文内容在 Document.footnotes 里。"""

    label: str


Inline = Union[
    Text, Strong, Emphasis, Strikethrough, Underline, Code,
    Superscript, Subscript, Math, Link, Citation, CrossRef, FootnoteRef,
]


# ── 块层 ────────────────────────────────────────────────────────────────

@dataclass
class Heading:
    level: int
    inlines: list[Inline] = field(default_factory=list)


@dataclass
class Paragraph:
    """普通段落。style 为 None 表示走默认正文流（正文/首段由排版阶段决定）。"""

    inlines: list[Inline] = field(default_factory=list)
    style: Optional[str] = None


@dataclass
class ListItem:
    blocks: list["Block"] = field(default_factory=list)


@dataclass
class ListBlock:
    """有序/无序列表。tight 对应 Markdown 的紧凑列表（无空行分隔）。"""

    items: list[ListItem] = field(default_factory=list)
    ordered: bool = False
    start: int = 1
    tight: bool = True


@dataclass
class Table:
    """表格。表题与表注是表格的组成部分，不是平级段落。"""

    header: list[list[Inline]] = field(default_factory=list)
    rows: list[list[list[Inline]]] = field(default_factory=list)
    alignments: list[str] = field(default_factory=list)  # left / center / right
    widths: Optional[list[float]] = None  # 由分隔行短横线长短推出的相对比例
    caption: Optional[list[Inline]] = None
    note: Optional[list[Inline]] = None


@dataclass
class Figure:
    """图片及其题注（题注写作 Markdown 的图片 alt 文本）。"""

    path: str
    caption: list[Inline] = field(default_factory=list)
    width_cm: Optional[float] = None


@dataclass
class Equation:
    """独立成行的公式。label 用于 `@eq-…` 交叉引用。"""

    latex: str
    label: Optional[str] = None


@dataclass
class Quote:
    blocks: list["Block"] = field(default_factory=list)


@dataclass
class CodeBlock:
    value: str
    language: str = ""


@dataclass(frozen=True)
class PageBreak:
    pass


@dataclass(frozen=True)
class Toc:
    depth: int = 3


@dataclass(frozen=True)
class SectionBreak:
    """分节符。page_format 如「罗马」「小写罗马」「阿拉伯」；start 为起始页码。"""

    page_format: str = "阿拉伯"
    start: int = 1


Block = Union[
    Heading, Paragraph, ListBlock, Table, Figure, Equation,
    Quote, CodeBlock, PageBreak, Toc, SectionBreak,
]


# ── 文档 ────────────────────────────────────────────────────────────────

@dataclass
class Metadata:
    """YAML 前置区。只保留与排版有关的部分；内容性信息不在此重复。"""

    title: Optional[str] = None
    subtitle: Optional[str] = None
    author: list[str] = field(default_factory=list)
    date: Optional[str] = None
    bibliography: Optional[str] = None
    csl: Optional[str] = None
    crossref: dict = field(default_factory=dict)
    chapters: bool = False
    link_citations: bool = True


@dataclass
class Footnote:
    label: str
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Document:
    meta: Metadata = field(default_factory=Metadata)
    blocks: list[Block] = field(default_factory=list)
    footnotes: list[Footnote] = field(default_factory=list)

    def headings(self) -> list[Heading]:
        return [b for b in self.blocks if isinstance(b, Heading)]

    def styled(self, style: str) -> list[Paragraph]:
        return [b for b in self.blocks if isinstance(b, Paragraph) and b.style == style]
