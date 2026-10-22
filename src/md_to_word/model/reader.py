"""md_to_word.model.reader — 契约 Markdown → 文档模型。

只认本技能定义的语法子集（标题、段落样式行、列表、表格、图片、公式、引用块、代码块、
脚注、短代码），不追求 CommonMark 全兼容：语法由我们定义，解析器自然也只认这一套。

当前版本是行级状态机 + 内联扫描，够表达现有全部样例。v3 的写出器接上之后，若发现模型
表达不了的写法，补在这里，而不是在输出端打补丁。
"""

from __future__ import annotations

import re
from typing import Optional

import yaml

from md_to_word.model.document import (
    Block, Citation, CitationItem, Code, CodeBlock, CrossRef, Document, Emphasis, Equation,
    Figure, Footnote, FootnoteRef, Heading, Link, ListBlock, ListItem, Math, Metadata,
    PageBreak, Paragraph, Quote, SectionBreak, Strikethrough, Strong, Subscript,
    Superscript, Table, Text, Toc, Underline,
)
from md_to_word.preprocessor.blocks import resolve_style_name, split_style_line

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE_RE = re.compile(r"^(```|~~~)(.*)$")
_SHORTCODE_RE = re.compile(r"^\{\{<\s*([a-z]+)(.*?)>\}\}\s*$")
_IMAGE_ONLY_RE = re.compile(r"^!\[(?P<alt>[^\]]*)\]\((?P<path>[^)\s]+)\)\s*(?P<attrs>\{[^}]*\})?\s*$")
_WIDTH_RE = re.compile(r"width\s*=\s*([\d.]+)\s*(cm|mm|in|pt|%)?")
_EQ_OPEN_RE = re.compile(r"^\$\$(?P<body>.*)")
_LABEL_RE = re.compile(r"\{#(?P<label>[\w:.\-]+)\}\s*$")
_BULLET_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+(?P<text>.*)$")
_ORDERED_RE = re.compile(r"^(?P<indent>\s*)(?P<num>\d+)[.)]\s+(?P<text>.*)$")
_FOOTNOTE_DEF_RE = re.compile(r"^\[\^(?P<label>[^\]]+)\]:\s*(?P<text>.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(?P<body>.*)\|\s*$")
_TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

_SECTION_PARAM_RE = re.compile(r"(\S+?)=(\S+)")
_SECTION_ALIAS = {"页码": "page_format", "page_number": "page_format", "format": "page_format",
                  "起始": "start", "start": "start"}


# ── 内联 ────────────────────────────────────────────────────────────────

_INLINE_RE = re.compile(
    r"(?P<code>`[^`]+`)"
    r"|(?P<math>\$[^$\n]+\$)"
    r"|(?P<strong>\*\*.+?\*\*)"
    r"|(?P<del>~~.+?~~)"
    r"|(?P<underline>\[[^\]]+\]\{\.underline\})"
    r"|(?P<link>\[[^\]]*\]\([^)\s]+\))"
    r"|(?P<footnote>\[\^[^\]]+\])"
    r"|(?P<citation>\[[^\]]*@[^\]]*\])"
    r"|(?P<crossref>(?<![\w@])@[\w:.\-]+)"
    r"|(?P<sup>\^[^^\n]+\^)"
    r"|(?P<sub>~[^~\n]+~)"
    r"|(?P<em>\*[^*\n]+\*)"
)

_CITE_TOKEN_RE = re.compile(
    r"(?P<suppress>-)?@(?P<key>[\w:.\-]+)(?P<rest>(?:,\s*(?:p|pp)\.?\s*[^;,]+)?)"
)


def _parse_citation_body(body: str, narrative: bool) -> Citation:
    inner = body.strip()
    if inner.startswith("[") and inner.endswith("]"):
        inner = inner[1:-1]
    items: list[CitationItem] = []
    for chunk in re.split(r";", inner):
        chunk = chunk.strip()
        m = _CITE_TOKEN_RE.search(chunk)
        if not m:
            continue
        prefix = chunk[: m.start()].strip()
        locator = (m.group("rest") or "").lstrip(", ").strip()
        items.append(
            CitationItem(
                key=m.group("key"),
                prefix=prefix,
                locator=locator,
                suppress_author=bool(m.group("suppress")),
            )
        )
    return Citation(items=tuple(items), narrative=narrative)


def parse_inlines(text: str, citation_keys: Optional[set[str]] = None) -> list:
    """把一行内联 Markdown 切成节点序列。

    `citation_keys` 是文献库里已知的 key 集合。`@key` 在 Pandoc 里既是叙述式文献引用、
    又是稿内交叉引用，语义靠 key 是否存在于 .bib 区分——不传这个集合时一律当交叉引用，
    由调用方稍后归类。
    """
    nodes: list = []
    pos = 0
    for m in _INLINE_RE.finditer(text or ""):
        if m.start() > pos:
            nodes.append(Text(text[pos : m.start()]))
        kind = m.lastgroup
        raw = m.group(0)
        if kind == "code":
            nodes.append(Code(raw[1:-1]))
        elif kind == "math":
            nodes.append(Math(raw[1:-1]))
        elif kind == "strong":
            nodes.append(Strong(children=tuple(parse_inlines(raw[2:-2]))))
        elif kind == "em":
            nodes.append(Emphasis(children=tuple(parse_inlines(raw[1:-1]))))
        elif kind == "del":
            nodes.append(Strikethrough(children=tuple(parse_inlines(raw[2:-2]))))
        elif kind == "underline":
            nodes.append(Underline(children=tuple(parse_inlines(raw[1 : raw.index("]")]))))
        elif kind == "link":
            label, url = raw[1:-1].split("](", 1)
            nodes.append(Link(children=tuple(parse_inlines(label)), url=url))
        elif kind == "footnote":
            nodes.append(FootnoteRef(label=raw[2:-1]))
        elif kind == "citation":
            nodes.append(_parse_citation_body(raw, narrative=False))
        elif kind == "crossref":
            key = raw[1:]
            if citation_keys and key in citation_keys:
                nodes.append(Citation(items=(CitationItem(key=key),), narrative=True))
            else:
                nodes.append(CrossRef(target=key))
        elif kind == "sup":
            nodes.append(Superscript(children=tuple(parse_inlines(raw[1:-1]))))
        elif kind == "sub":
            nodes.append(Subscript(children=tuple(parse_inlines(raw[1:-1]))))
        pos = m.end()
    if pos < len(text or ""):
        nodes.append(Text(text[pos:]))
    return nodes


# ── 块级 ────────────────────────────────────────────────────────────────

def _split_frontmatter(text: str) -> tuple[str, str]:
    if not text.startswith("---\n"):
        return "", text
    end = text.find("\n---", 4)
    if end == -1:
        return "", text
    after = text.find("\n", end + 4)
    return text[4:end], text[after + 1 :] if after != -1 else ""


def _metadata(raw: str) -> Metadata:
    try:
        data = yaml.safe_load(raw) if raw.strip() else {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    authors = data.get("author") or []
    if isinstance(authors, str):
        authors = [authors]
    crossref = data.get("crossref") if isinstance(data.get("crossref"), dict) else {}
    return Metadata(
        title=data.get("title"),
        subtitle=data.get("subtitle"),
        author=list(authors),
        date=str(data["date"]) if data.get("date") is not None else None,
        bibliography=data.get("bibliography"),
        csl=data.get("csl"),
        crossref=crossref,
        chapters=bool(crossref.get("chapters")),
        link_citations=data.get("link-citations", True) is not False,
    )


def _table_cells(line: str) -> list[str]:
    body = _TABLE_ROW_RE.match(line).group("body")
    return [c.strip() for c in body.split("|")]


def _column_widths(separator: str) -> Optional[list[float]]:
    """分隔行短横线长短 → 相对列宽。全等或缺失时返回 None（表示「按内容排」）。"""
    dashes = [len(c) for c in _table_cells(separator)]
    if not dashes or len(set(dashes)) == 1:
        return None
    return [float(d) for d in dashes]


def _alignments(separator: str) -> list[str]:
    out = []
    for cell in _table_cells(separator):
        left, right = cell.startswith(":"), cell.endswith(":")
        out.append("center" if left and right else "right" if right else "left")
    return out


def _parse_section_params(rest: str) -> SectionBreak:
    kwargs: dict = {}
    for key, value in _SECTION_PARAM_RE.findall(rest or ""):
        field = _SECTION_ALIAS.get(key)
        if field == "start":
            kwargs["start"] = int(value) if value.isdigit() else 1
        elif field == "page_format":
            kwargs["page_format"] = value
    return SectionBreak(**kwargs)


def _parse_shortcode(name: str, rest: str) -> Optional[Block]:
    if name == "pagebreak":
        return PageBreak()
    if name == "toc":
        arg = rest.strip()
        return Toc(depth=int(arg) if arg.isdigit() else 3)
    if name == "section":
        return _parse_section_params(rest)
    return None


class _Reader:
    def __init__(self, body: str) -> None:
        self.lines = body.split("\n")
        self.doc = Document()
        self.pending_style: Optional[tuple[str, str]] = None  # (样式名, 内容)

    # -- 小工具 --------------------------------------------------------
    def _flush_pending(self) -> None:
        """把待定的样式段落落盘。"""
        if self.pending_style is None:
            return
        style, content = self.pending_style
        self.pending_style = None
        self.doc.blocks.append(Paragraph(inlines=parse_inlines(content), style=style))

    def _append(self, block: Block) -> None:
        """统一入口：入块之前先把待定的样式段落落盘，顺序即位置。"""
        self._flush_pending()
        self.doc.blocks.append(block)

    def _make_style_paragraph(self, name: str, content: str) -> None:
        resolved = resolve_style_name(name)
        if resolved is None:
            return
        self._flush_pending()
        self.pending_style = (resolved, content)

    # -- 主循环 --------------------------------------------------------
    def read(self) -> Document:
        i, n = 0, len(self.lines)
        while i < n:
            line = self.lines[i]
            stripped = line.strip()

            if not stripped:
                self._flush_pending()
                i += 1
                continue

            # 代码块
            fence = _FENCE_RE.match(stripped)
            if fence:
                i = self._read_code_block(i, fence)
                continue

            # 段落样式行
            split = split_style_line(line)
            if split is not None:
                self._make_style_paragraph(split[0], split[1])
                i += 1
                continue

            # 脚注定义
            fn = _FOOTNOTE_DEF_RE.match(stripped)
            if fn:
                self._flush_pending()
                self.doc.footnotes.append(
                    Footnote(label=fn.group("label"),
                             blocks=[Paragraph(inlines=parse_inlines(fn.group("text")))])
                )
                i += 1
                continue

            # 标题
            heading = _HEADING_RE.match(stripped)
            if heading:
                self._flush_pending()
                self._append(
                    Heading(level=len(heading.group(1)), inlines=parse_inlines(heading.group(2)))
                )
                i += 1
                continue

            # 短代码
            shortcode = _SHORTCODE_RE.match(stripped)
            if shortcode:
                block = _parse_shortcode(shortcode.group(1), shortcode.group(2))
                if block is not None:
                    self._flush_pending()
                    self._append(block)
                    i += 1
                    continue

            # 独立公式
            if stripped.startswith("$$"):
                i = self._read_equation(i)

                continue

            # 表格
            if _TABLE_ROW_RE.match(stripped) and i + 1 < n and _TABLE_SEP_RE.match(self.lines[i + 1]):
                i = self._read_table(i)
                continue

            # 图片
            image = _IMAGE_ONLY_RE.match(stripped)
            if image:
                self._flush_pending()
                self._append(self._make_figure(image))
                i += 1
                continue

            # 引用块
            if stripped.startswith(">"):
                i = self._read_quote(i)
                continue

            # 列表
            if _BULLET_RE.match(line) or _ORDERED_RE.match(line):
                i = self._read_list(i)
                continue

            # 普通段落
            self._flush_pending()
            self._append(Paragraph(inlines=parse_inlines(stripped)))
            i += 1

        self._flush_pending()
        return self.doc

    # -- 各块读取 ------------------------------------------------------
    def _read_code_block(self, start: int, fence: re.Match) -> int:
        marker, language = fence.group(1), fence.group(2).strip()
        body: list[str] = []
        i = start + 1
        while i < len(self.lines) and not self.lines[i].strip().startswith(marker):
            body.append(self.lines[i])
            i += 1
        self._flush_pending()
        self._append(CodeBlock(value="\n".join(body), language=language))
        return i + 1

    def _read_equation(self, start: int) -> int:
        """读一条独立公式，支持跨行与 `{#eq-x}` 标签。

        标签要**先剥掉**再判断收尾的 `$$`：`$$E=mc^2$$ {#eq-a}` 去掉标签才以 `$$` 结尾。
        不剥就会误判成跨行公式，一路扫到下一个 `$$`，把中间内容整段吞掉。
        """
        parts: list[str] = []
        label = None
        i = start
        while i < len(self.lines):
            text = self.lines[i].strip()
            if i == start:
                text = text[2:]  # 去掉开头的 $$
            candidate, label_candidate = text, None
            m = _LABEL_RE.search(text)
            if m:
                candidate, label_candidate = text[: m.start()], m.group("label")
            if candidate.rstrip().endswith("$$"):
                parts.append(candidate.rstrip()[:-2])
                label = label_candidate
                break
            parts.append(text)
            i += 1

        self._append(Equation(latex="\n".join(parts).strip(), label=label))
        return i + 1

    def _read_table(self, start: int) -> int:
        header = [parse_inlines(c) for c in _table_cells(self.lines[start])]
        separator = self.lines[start + 1]
        alignments = _alignments(separator)
        widths = _column_widths(separator)
        rows: list[list] = []
        i = start + 2
        while i < len(self.lines) and _TABLE_ROW_RE.match(self.lines[i].strip()):
            rows.append([parse_inlines(c) for c in _table_cells(self.lines[i])])
            i += 1

        self._append(Table(header=header, rows=rows, alignments=alignments, widths=widths))
        return i

    def _make_figure(self, match: re.Match) -> Figure:
        width_cm = None
        attrs = match.group("attrs") or ""
        m = _WIDTH_RE.search(attrs)
        if m:
            value, unit = float(m.group(1)), m.group(2) or "cm"
            width_cm = {"cm": value, "mm": value / 10, "in": value * 2.54, "pt": value * 2.54 / 72}.get(unit)
        return Figure(path=match.group("path"), alt=match.group("alt"), width_cm=width_cm)

    def _read_quote(self, start: int) -> int:
        body: list[str] = []
        i = start
        while i < len(self.lines) and self.lines[i].strip().startswith(">"):
            body.append(self.lines[i].strip().lstrip(">").strip())
            i += 1
        self._flush_pending()
        self._append(
            Quote(blocks=[Paragraph(inlines=parse_inlines(line)) for line in body if line])
        )
        return i

    def _read_list(self, start: int) -> int:
        items: list[ListItem] = []
        ordered = bool(_ORDERED_RE.match(self.lines[start]))
        first = _ORDERED_RE.match(self.lines[start])
        start_no = int(first.group("num")) if first else 1
        i = start
        while i < len(self.lines):
            line = self.lines[i]
            bullet = _BULLET_RE.match(line)
            number = _ORDERED_RE.match(line)
            if bullet and not ordered:
                items.append(ListItem(blocks=[Paragraph(inlines=parse_inlines(bullet.group("text")))]))
            elif number and ordered:
                items.append(ListItem(blocks=[Paragraph(inlines=parse_inlines(number.group("text")))]))
            else:
                break
            i += 1
        self._flush_pending()
        self._append(ListBlock(items=items, ordered=ordered, start=start_no))
        return i


def read_markdown(text: str, citation_keys: Optional[set[str]] = None) -> Document:
    """契约 Markdown 全文 → Document。

    `citation_keys` 传入文献库 key 时，`@key` 能正确区分「叙述式文献引用」与「稿内交叉引用」。
    """
    front, body = _split_frontmatter(text)
    reader = _Reader(body)
    doc = reader.read()
    doc.meta = _metadata(front)
    return doc
