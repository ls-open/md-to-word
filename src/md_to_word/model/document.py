"""md_to_word.model.document — 文档模型（整个转换的地基）。

这一层只描述「文档是什么」，不描述「怎么写成 OOXML」，也不描述「格式要求长什么样」。
三层的关系：

    契约 Markdown  --reader-->  文档模型  --writer-->  OOXML
                                  ↑
                          requirements.txt（样式参数）

模型的有意取舍：
- 段落带的是 **Word 样式名**（`Abstract`），不是用户写的语义名（`摘要`）。语义名到样式名的
  映射属于格式契约层，在读取阶段就解掉，写入阶段不再做判断。
- 表题、表注是**独立段落**，不挂在表格上。Word 里题注本来就是一个带样式的段落，
  表格是另一个对象；合并会把作者写的两行捏成一行，还会让「表格清单」里那些不依附表格的
  题注无法表达。位置由**顺序**决定，同页由**样式的分页控制**决定，都不需要模型来管。
- 引文与交叉引用分成两种内联节点：`Citation` 走文献库，`CrossRef` 走稿内标签。二者
  共用 `@` 语法，但语义完全不同，模型里不合并。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Union

# 列表最多三级：Word 的编号级别能到九级，但三级之后在 A4 版心里已经没有可读的行宽，
# 多出来的层级只会让「同一份稿件的两种写法」导出成看不出差别的两个结果。
# 读取（判层级）与写出（生成编号定义）共用这一个上限。
MAX_LIST_LEVEL = 2


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
    """列表项。level 是缩进层级（0 起），ordered 为 None 表示跟随所属列表。"""

    blocks: list["Block"] = field(default_factory=list)
    level: int = 0
    ordered: Optional[bool] = None


@dataclass
class ListBlock:
    """有序/无序列表。tight 对应 Markdown 的紧凑列表（无空行分隔）。"""

    items: list[ListItem] = field(default_factory=list)
    ordered: bool = False
    start: int = 1
    tight: bool = True


@dataclass
class Table:
    """表格本体。表题/表注是它前后的独立段落（样式 Table Caption / Table Note）。"""

    header: list[list[Inline]] = field(default_factory=list)
    rows: list[list[list[Inline]]] = field(default_factory=list)
    alignments: list[str] = field(default_factory=list)  # left / center / right
    widths: Optional[list[float]] = None  # 由分隔行短横线长短推出的相对比例


@dataclass
class Figure:
    """图片本体。题注用 `%% 图片题注 …` 单独成段，写在图前或图后由作者决定。

    `alt` 只承担无障碍替代文字，不再兼任题注——一个括号两种语义是上一版的毛病。
    """

    path: str
    alt: str = ""
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
    # None = 不指定：写出器按模板里实际声明的目录条目样式定级数（声明到几级就收几级）
    depth: int | None = None


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
    """YAML 前置区。只放**与位置无关**的配置：文献库、样式、交叉引用约定。

    标题、副标题、作者、日期**不在这里**：它们的位置本身就是排版的一部分（可能在封面
    之后、可能在第二页），YAML 管不住位置。这四项一律写成正文的样式行。
    """

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
