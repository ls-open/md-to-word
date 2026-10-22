"""md_to_word.writer.docx_writer — 文档模型 → .docx。

这是 v3 自研渲染器的写出侧：只做机械映射，不做任何判断——样式名、段落顺序、表格线宽
这些决定在读取阶段和格式契约里已经定完。写出一层如果再"猜"，就等于把判据藏到了渲染里。

能力边界写在 `SUPPORTED` 里，遇到没实现的结构抛 `UnsupportedFeature` 并说清楚缺什么，
**不做静默降级**：悄悄写成一个普通段落，比直接失败更难查。
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Iterable

from docx import Document as open_docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.packuri import PackURI
from docx.opc.part import Part
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm

from md_to_word.preprocessor.markers import PAGE_NUMBER_FMT, section_paragraph_xml, toc_xml
from md_to_word.transform.mathml2omml import UnsupportedMath, latex_to_omml
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


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


class UnsupportedFeature(NotImplementedError):
    """模型里有、但写出器还没实现的结构。"""


class _Writer:
    def __init__(self, document: Document, docx, citations=None) -> None:
        self.model = document
        self.docx = docx
        self.citations = citations
        self._after_heading = False  # 下一段正文若是「标题后的第一段」，落 First Paragraph
        self._compact_style = self._style_name("Compact")
        self._footnote_ids: dict[str, int] = {}
        self._eq_numbers: dict[str, str] = {}

    # ── 入口 ─────────────────────────────────────────────────────────
    def write(self) -> None:
        body = self.docx.element.body
        for paragraph in list(self.docx.paragraphs):  # 模板自带的空段落
            if not paragraph.text.strip():
                body.remove(paragraph._element)

        self._collect_equation_numbers()
        self._title_block()
        for block in self.model.blocks:
            self.block(block)
        self._write_bibliography()
        if self._footnote_ids:
            self._write_footnotes()

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
            self._equation(block)
        elif isinstance(block, Toc):
            self._insert_before_sectpr(parse_xml(toc_xml(block.depth)))
        elif isinstance(block, SectionBreak):
            self._section(block)
        else:
            raise UnsupportedFeature(f"未支持的块类型：{type(block).__name__}")

    def _write_bibliography(self) -> None:
        """文献列表由引擎生成，放在文末；样式由要求文件的「参考文献」行控制。"""
        if self.citations is None:
            return
        entries = self.citations.bibliography()
        if not entries:
            return
        for entry in entries:
            self.docx.add_paragraph(entry, style="Bibliography")

    def _collect_equation_numbers(self) -> None:
        """先扫一遍给带标签的公式编号：写正文时要用它解析 `@eq-x`。

        编号规则与 Quarto 的 crossref 对齐：默认按出现顺序 (1)(2)…；开了 `chapters: true`
        就按「章号.序号」，章号取自一级标题的序号。
        """
        chapter = 0
        index = 0
        for block in self.model.blocks:
            if isinstance(block, Heading) and block.level == 1:
                chapter += 1
                index = 0
            elif isinstance(block, Equation) and block.label:
                index += 1
                self._eq_numbers[block.label] = (
                    f"{chapter}.{index}" if self.model.meta.chapters else str(index)
                )

    def _content_width_twips(self) -> int:
        sect = self._body_sectpr()
        if sect is None:
            return 8306
        size = sect.find(qn("w:pgSz"))
        margins = sect.find(qn("w:pgMar"))
        try:
            width = int(size.get(qn("w:w")))
            return width - int(margins.get(qn("w:left"))) - int(margins.get(qn("w:right")))
        except (AttributeError, TypeError, ValueError):
            return 8306

    def _body_sectpr(self):
        return self.docx.element.body.find(qn("w:sectPr"))

    def _insert_before_sectpr(self, element) -> None:
        """插到文末 sectPr 之前：body 的 sectPr 必须是最后一个子元素。"""
        body = self.docx.element.body
        sectpr = self._body_sectpr()
        if sectpr is not None:
            sectpr.addprevious(element)
        else:
            body.append(element)

    def _section(self, block: SectionBreak) -> None:
        """分节符：它描述的是**上面那一节**（OOXML 里 sectPr 归前一节）。"""
        params: dict = {}
        fmt = PAGE_NUMBER_FMT.get(block.page_format)
        if fmt:
            params["fmt"] = fmt
        if block.start:
            params["start"] = block.start

        template_sect = self._body_sectpr()
        xml = section_paragraph_xml(params, copy.deepcopy(template_sect) if template_sect is not None else None)
        self._insert_before_sectpr(parse_xml(xml))

    def _equation(self, block: Equation) -> None:
        """独立公式：居中，编号靠右。编号用中心制表位 + 右制表位实现，是 Word 里的常规写法。"""
        try:
            maths = latex_to_omml(block.latex)
        except UnsupportedMath as exc:
            raise UnsupportedFeature(f"公式里有尚未支持的结构：{exc}") from exc

        paragraph = self.docx.add_paragraph()
        width = self._content_width_twips()
        pPr = paragraph._p.get_or_add_pPr()
        pPr.append(
            parse_xml(
                f'<w:tabs {nsdecls("w")}><w:tab w:val="center" w:pos="{width // 2}"/>'
                f'<w:tab w:val="right" w:pos="{width}"/></w:tabs>'
            )
        )
        paragraph.add_run().add_tab()
        math_el = self._omath(maths)
        paragraph._p.append(math_el)

        number = self._eq_numbers.get(block.label or "")
        if number:
            paragraph.add_run().add_tab()
            paragraph.add_run(f"({number})")

    @staticmethod
    def _omath(nodes):
        math_el = parse_xml(
            f'<m:oMath {nsdecls("m")} xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>'
        )
        for node in nodes:
            math_el.append(node)
        return math_el

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
        """列表写出：真实编号（numbering.xml），不是字面量序号。

        字面量的代价是：Word 里按退格改不了级别、增删条目不会自动重编号、目录与交叉引用也
        抓不到。既然目标是「导出的文档还能在 Word 里继续改」，编号就得是域。
        """
        num_id = self._numbered_list(block.ordered, block.start)
        for item in block.items:
            for inner in item.blocks:
                if not isinstance(inner, Paragraph):
                    raise UnsupportedFeature("列表项里目前只支持段落")
                paragraph = self.docx.add_paragraph(style=self._compact_style)
                self._apply_numbering(paragraph, num_id)
                self.inlines(paragraph, inner.inlines)

    def _ensure_numbering(self) -> None:
        """模板里的 numbering.xml 是空的：首次用到列表时补两套定义（无序/有序）。"""
        numbering = self.docx.part.numbering_part.element
        if numbering.findall(qn("w:abstractNum")):
            return
        xml = (
            f'<w:numbering {nsdecls("w")}>'
            '<w:abstractNum w:abstractNumId="0"><w:multiLevelType w:val="singleLevel"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/>'
            '<w:lvlText w:val="•"/><w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
            '<w:abstractNum w:abstractNumId="1"><w:multiLevelType w:val="singleLevel"/>'
            '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
            '<w:lvlText w:val="%1."/><w:lvlJc w:val="left"/>'
            '<w:pPr><w:ind w:left="720" w:hanging="360"/></w:pPr></w:lvl></w:abstractNum>'
            '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
            '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>'
            "</w:numbering>"
        )
        for child in parse_xml(xml):
            numbering.append(child)

    def _numbered_list(self, ordered: bool, start: int) -> int:
        """返回该列表要用的 numId；起始编号不是 1 时另建一个带 startOverride 的 num。"""
        self._ensure_numbering()
        base_id = 2 if ordered else 1
        if not ordered or start == 1:
            return base_id

        numbering = self.docx.part.numbering_part.element
        self._override_seq = getattr(self, "_override_seq", 99)
        self._override_seq += 1
        new_id = self._override_seq
        xml = (
            f'<w:num {nsdecls("w")} w:numId="{new_id}">'
            f'<w:abstractNumId w:val="{base_id - 1}"/>'
            f'<w:lvlOverride w:ilvl="0"><w:startOverride w:val="{start}"/></w:lvlOverride>'
            "</w:num>"
        )
        numbering.append(parse_xml(xml))
        return new_id

    @staticmethod
    def _apply_numbering(paragraph, num_id: int) -> None:
        pPr = paragraph._p.get_or_add_pPr()
        numPr = pPr.get_or_add_numPr()
        numPr.get_or_add_ilvl().val = 0
        numPr.get_or_add_numId().val = num_id

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

    def _footnote_reference(self, paragraph, label: str) -> None:
        """脚注引用：run 里挂 `w:footnoteReference`，正文内容稍后统一写进 footnotes.xml。"""
        fids = self._footnote_ids
        if label not in fids:
            fids[label] = len(fids) + 1
        run = paragraph.add_run()
        style = self._style_name("Footnote Reference")
        if style:
            run.style = style
        run._r.append(parse_xml(f'<w:footnoteReference {nsdecls("w")} w:id="{fids[label]}"/>'))

    def _write_footnotes(self) -> None:
        """生成 word/footnotes.xml 并挂上关系。

        python-docx 没有脚注 API，这里直接构造部件。分隔符（id=-1）与续页分隔符（id=0）
        是 Word 的约定，缺了它们脚注区在那条横线上会显示异常。
        """
        body: list[str] = []
        by_label = {f.label: f for f in self.model.footnotes}
        for label, fid in self._footnote_ids.items():
            footnote = by_label.get(label)
            paragraphs = "".join(self._footnote_paragraph(b) for b in (footnote.blocks if footnote else []))
            if not paragraphs:
                paragraphs = self._footnote_paragraph(Paragraph(inlines=[]))
            body.append(f'<w:footnote w:id="{fid}">{paragraphs}</w:footnote>')

        xml = (
            f'<w:footnotes {nsdecls("w")}>'
            '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
            '<w:footnote w:type="continuationSeparator" w:id="0">'
            "<w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>"
            + "".join(body)
            + "</w:footnotes>"
        )
        part = Part(
            PackURI("/word/footnotes.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
            xml.encode("utf-8"),
            self.docx.part.package,
        )
        self.docx.part.relate_to(part, RT.FOOTNOTES)

    def _footnote_paragraph(self, block) -> str:
        if not isinstance(block, Paragraph):
            raise UnsupportedFeature("脚注内容目前只支持段落")
        style = (block.style or "Footnote Text").replace(" ", "")
        runs = "".join(self._run_xml(node) for node in block.inlines)
        return f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{runs}</w:p>'

    def _run_xml(self, node) -> str:
        text = getattr(node, "value", None)
        if text is not None:
            return f'<w:r><w:t xml:space="preserve">{_escape(text)}</w:t></w:r>'
        children = getattr(node, "children", None)
        if children is None:
            raise UnsupportedFeature(f"脚注里的 {type(node).__name__} 尚未支持")
        inner = "".join(self._run_xml(c) for c in children)
        props = ""
        if isinstance(node, Strong):
            props = "<w:b/>"
        elif isinstance(node, Emphasis):
            props = "<w:i/>"
        return inner.replace("<w:r>", f"<w:r><w:rPr>{props}</w:rPr>", 1) if props else inner

    def _resolve_crossref(self, target: str) -> str:
        """`@eq-a` → 「式2.1」：前缀取自稿件 YAML 的 crossref，没有就用中文默认。"""
        prefixes = self.model.meta.crossref or {}
        if target.startswith("eq-"):
            prefix = prefixes.get("eq-prefix", "式")
        elif target.startswith("fig-"):
            prefix = prefixes.get("fig-prefix", "图")
        elif target.startswith("tbl-"):
            prefix = prefixes.get("tbl-prefix", "表")
        else:
            raise UnsupportedFeature(f"交叉引用 {target} 的类型尚未支持")
        number = self._eq_numbers.get(target)
        if number is None:
            raise UnsupportedFeature(f"交叉引用 {target} 指向的标签不存在")
        return f"{prefix}{number}" if prefix else number

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
            try:
                nodes = latex_to_omml(node.latex)
            except UnsupportedMath as exc:
                raise UnsupportedFeature(f"行内公式里有尚未支持的结构：{exc}") from exc
            paragraph._p.append(self._omath(nodes))
        elif isinstance(node, Link):
            self._hyperlink(paragraph, node)
        elif isinstance(node, CrossRef):
            paragraph.add_run(self._resolve_crossref(node.target))
        elif isinstance(node, Citation):
            if self.citations is None:
                raise UnsupportedFeature(
                    "稿件声明了 citation，但未提供文献库或 CSL 样式；请检查 YAML 的 bibliography/csl"
                )
            keys = [(item.key, item.locator) for item in node.items]
            paragraph.add_run(self.citations.cite(keys, narrative=node.narrative))
        elif isinstance(node, FootnoteRef):
            self._footnote_reference(paragraph, node.label)
        else:
            paragraph.add_run(getattr(node, "value", str(node)))

    def _hyperlink(self, paragraph, node: Link) -> None:
        """超链接是关系（r:id）+ `w:hyperlink`，不是普通 run。"""
        from docx.oxml.ns import nsdecls as _nsdecls

        r_id = paragraph.part.relate_to(node.url, RT.HYPERLINK, is_external=True)
        element = parse_xml(
            f'<w:hyperlink {_nsdecls("w", "r")} r:id="{r_id}"/>'
        )
        style = self._style_name("Hyperlink")
        for child in node.children:
            text = getattr(child, "value", None)
            if text is None:
                raise UnsupportedFeature("超链接里目前只支持纯文本")
            run = element.makeelement(qn("w:r"), {})
            if style:
                rpr = run.makeelement(qn("w:rPr"), {})
                rpr.append(run.makeelement(qn("w:rStyle"), {qn("w:val"): style.replace(" ", "")}))
                run.append(rpr)
            t = run.makeelement(qn("w:t"), {})
            t.text = text
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            run.append(t)
            element.append(run)
        paragraph._p.append(element)

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


def write_docx(model: Document, template: Path | str, output: Path | str, citations=None) -> Path:
    """把文档模型写成 .docx。模板提供 styles.xml（由格式要求文件生成）。

    `citations` 是 `transform.citations.CitationEngine`：有文献库时传进来，文献引用与
    文末列表都由它渲染；不传时遇到 citation 会明确失败。
    """
    docx = open_docx(str(template))
    _Writer(model, docx, citations=citations).write()
    out = Path(output)
    docx.save(str(out))
    return out
