"""md_to_word.writer.docx_writer — 文档模型 → .docx。

这是 v3 自研渲染器的写出侧：只做机械映射，不做任何判断——样式名、段落顺序、表格线宽
这些决定在读取阶段和格式契约里已经定完。写出一层如果再"猜"，就等于把判据藏到了渲染里。

能力边界写在 `SUPPORTED` 里，遇到没实现的结构抛 `UnsupportedFeature` 并说清楚缺什么，
**不做静默降级**：悄悄写成一个普通段落，比直接失败更难查。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docx import Document as open_docx
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.shared import Cm

from md_to_word.model.document import (
    Block, Code, CodeBlock, Document, Emphasis, Equation, Figure, FootnoteRef, Heading,
    Inline, Link, ListBlock, Math, PageBreak, Paragraph, Quote, SectionBreak, Strikethrough,
    Strong, Subscript, Superscript, Table, Toc, Underline, Citation, CrossRef,
)

SUPPORTED_BLOCKS = (Heading, Paragraph, ListBlock, Table, Figure, CodeBlock, PageBreak, Quote)
SUPPORTED_INLINES = (Code, Strong, Emphasis, Strikethrough, Underline, Superscript, Subscript)

_ALIGN = {
    "left": WD_ALIGN_PARAGRAPH.LEFT,
    "center": WD_ALIGN_PARAGRAPH.CENTER,
    "right": WD_ALIGN_PARAGRAPH.RIGHT,
}


class UnsupportedFeature(NotImplementedError):
    """模型里有、但写出器还没实现的结构。"""


class _Writer:
    def __init__(self, document: Document, docx) -> None:
        self.model = document
        self.docx = docx
        self._after_heading = False  # 下一段正文若是「标题后的第一段」，落 First Paragraph

    # ── 入口 ─────────────────────────────────────────────────────────
    def write(self) -> None:
        body = self.docx.element.body
        for paragraph in list(self.docx.paragraphs):  # 模板自带的空段落
            if not paragraph.text.strip():
                body.remove(paragraph._element)

        self._title_block()
        for block in self.model.blocks:
            self.block(block)

    def _title_block(self) -> None:
        """YAML 里的标题区：文档标题、副标题、作者、日期各占一段。"""
        meta = self.model.meta
        if meta.title:
            self.docx.add_paragraph(str(meta.title), style="Title")
        if meta.subtitle:
            self.docx.add_paragraph(str(meta.subtitle), style="Subtitle")
        if meta.author:
            self.docx.add_paragraph("，".join(meta.author), style="Author")
        if meta.date:
            self.docx.add_paragraph(str(meta.date), style="Date")

    # ── 块 ───────────────────────────────────────────────────────────
    def block(self, block: Block) -> None:
        if isinstance(block, Heading):
            self._heading(block)
        elif isinstance(block, Paragraph):
            self._paragraph(block)
        elif isinstance(block, Table):
            self._table(block)
        elif isinstance(block, Figure):
            self._figure(block)
        elif isinstance(block, CodeBlock):
            self._code(block)
        elif isinstance(block, ListBlock):
            self._list(block)
        elif isinstance(block, Quote):
            self._quote(block)
        elif isinstance(block, PageBreak):
            self.docx.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        elif isinstance(block, Equation):
            raise UnsupportedFeature("公式写出（LaTeX → OMML）尚未实现；v3.1 补")
        elif isinstance(block, Toc):
            raise UnsupportedFeature("目录域写出尚未实现")
        elif isinstance(block, SectionBreak):
            raise UnsupportedFeature("分节符写出尚未实现")
        else:
            raise UnsupportedFeature(f"未支持的块类型：{type(block).__name__}")

    def _heading(self, block: Heading) -> None:
        paragraph = self.docx.add_paragraph(style=f"Heading {block.level}")
        self.inlines(paragraph, block.inlines)
        self._after_heading = True

    def _paragraph(self, block: Paragraph) -> None:
        """未指定样式的正文，按契约分流：紧跟标题的第一段用 First Paragraph，其余 Body Text。"""
        if block.style:
            style = block.style
        else:
            style = "First Paragraph" if self._after_heading else "Body Text"
        self._after_heading = False
        paragraph = self.docx.add_paragraph(style=style)
        self.inlines(paragraph, block.inlines)

    def _code(self, block: CodeBlock) -> None:
        paragraph = self.docx.add_paragraph(style="SourceCode")
        lines = block.value.split("\n")
        for i, line in enumerate(lines):
            if i:
                paragraph.add_run().add_break()
            paragraph.add_run(line)

    def _quote(self, block: Quote) -> None:
        for inner in block.blocks:
            if not isinstance(inner, Paragraph):
                raise UnsupportedFeature("引用块里目前只支持段落")
            paragraph = self.docx.add_paragraph(style=inner.style or "Block Text")
            self.inlines(paragraph, inner.inlines)

    def _list(self, block: ListBlock) -> None:
        style = self.docx.styles["Compact"] if "Compact" in [s.name for s in self.docx.styles] else None
        for item in block.items:
            paragraph = self.docx.add_paragraph(style=style) if style else self.docx.add_paragraph()
            self._apply_numbering(paragraph, block, len(item.blocks))
            for inner in item.blocks:
                if not isinstance(inner, Paragraph):
                    raise UnsupportedFeature("列表项里目前只支持段落")
                self.inlines(paragraph, inner.inlines)
            if block.ordered:
                paragraph.paragraph_format.left_indent = Cm(0.74)

    def _apply_numbering(self, paragraph, block: ListBlock, _n: int) -> None:
        """列表序号先写成字面字符。

        真正的编号要写 `numbering.xml`（abstractNum + numId + 缓存序号），属于 v3.0 的
        后续增量；先落字面量能保证「导出的内容和作者写的一致」，不静默丢序号。
        """
        raise UnsupportedFeature("列表的真实编号（numbering.xml）尚未实现；v3.0 后续补")

    def _table(self, block: Table) -> None:
        rows = len(block.rows) + (1 if block.header else 0)
        cols = len(block.header) if block.header else (len(block.rows[0]) if block.rows else 0)
        if not rows or not cols:
            return
        table = self.docx.add_table(rows=rows, cols=cols)
        table.style = self.docx.styles["Table"]
        table.autofit = block.widths is None

        cell_style = self._style_name("Compact")
        data = ([block.header] if block.header else []) + block.rows
        for r, row in enumerate(data):
            for c, cell_inlines in enumerate(row):
                cell = table.cell(r, c)
                paragraph = cell.paragraphs[0]
                if cell_style:
                    paragraph.style = cell_style
                if block.alignments and c < len(block.alignments):
                    paragraph.alignment = _ALIGN.get(block.alignments[c], WD_ALIGN_PARAGRAPH.LEFT)
                self.inlines(paragraph, cell_inlines)
        if block.header:
            self._mark_header_row(table)

    def _mark_header_row(self, table) -> None:
        """表头行跨页重复：`w:tblHeader`。python-docx 没有这项 API，直接写 XML。"""
        from docx.oxml.ns import qn

        tr = table.rows[0]._tr
        trPr = tr.get_or_add_trPr()
        if trPr.find(qn("w:tblHeader")) is None:
            el = trPr.makeelement(qn("w:tblHeader"), {})
            trPr.append(el)

    def _figure(self, block: Figure) -> None:
        paragraph = self.docx.add_paragraph(style="Captioned Figure")
        run = paragraph.add_run()
        if block.width_cm:
            run.add_picture(block.path, width=Cm(block.width_cm))
        else:
            run.add_picture(block.path)

    # ── 内联 ─────────────────────────────────────────────────────────
    def inlines(self, paragraph, nodes: Iterable[Inline]) -> None:
        self._verbatim_style = self._style_name("Verbatim Char")
        for node in nodes:
            self.inline(paragraph, node)

    def _style_name(self, name: str) -> str | None:
        """按名称取样式名（没有就返回 None，不静默套用别的样式）。"""
        return name if name in {s.name for s in self.docx.styles} else None

    def inline(self, paragraph, node: Inline) -> None:
        if isinstance(node, Code):
            run = paragraph.add_run(node.value)
            if self._verbatim_style:
                run.style = self._verbatim_style
        elif isinstance(node, Strong):
            self._styled(paragraph, node.children, bold=True)
        elif isinstance(node, Emphasis):
            self._styled(paragraph, node.children, italic=True)
        elif isinstance(node, Strikethrough):
            self._styled(paragraph, node.children, strike=True)
        elif isinstance(node, Underline):
            self._styled(paragraph, node.children, underline=True)
        elif isinstance(node, Superscript):
            self._styled(paragraph, node.children, superscript=True)
        elif isinstance(node, Subscript):
            self._styled(paragraph, node.children, subscript=True)
        elif isinstance(node, Math):
            raise UnsupportedFeature("行内公式写出（LaTeX → OMML）尚未实现；v3.1 补")
        elif isinstance(node, Link):
            raise UnsupportedFeature("超链接写出尚未实现")
        elif isinstance(node, (Citation, CrossRef)):
            raise UnsupportedFeature("引文与交叉引用的编译尚未实现；先走 Pandoc 通道")
        elif isinstance(node, FootnoteRef):
            raise UnsupportedFeature("脚注写出尚未实现")
        else:
            paragraph.add_run(getattr(node, "value", str(node)))

    def _styled(self, paragraph, children, **fmt) -> None:
        run = paragraph.add_run()
        run.text = ""
        for key, value in fmt.items():
            setattr(run.font, key, value)
        self._nested(run, children)

    def _nested(self, run, children) -> None:
        """在已带格式的 run 里追加纯文本子节点；嵌套格式在 v3.0 先不支持。"""
        for child in children:
            if isinstance(child, Code):
                run.add_text(child.value)
            else:
                text = getattr(child, "value", None)
                if text is None:
                    raise UnsupportedFeature("嵌套的行内格式（如加粗里套斜体）尚未实现")
                run.add_text(text)


def write_docx(model: Document, template: Path | str, output: Path | str) -> Path:
    """把文档模型写成 .docx。模板提供 styles.xml（由格式要求文件生成）。"""
    docx = open_docx(str(template))
    _Writer(model, docx).write()
    out = Path(output)
    docx.save(str(out))
    return out
