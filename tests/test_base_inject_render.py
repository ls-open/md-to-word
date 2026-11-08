"""灌完必须和原件长得一样——这条只能用真 Word 验，没装 Word 的机器整文件跳过。

判据就是坐标：Word 排过版才知道分页有没有变、空白页有没有丢，这些从 OOXML 里看不出来。
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from docx.enum.section import WD_SECTION

from md_to_word.model.reader import read_markdown
from md_to_word.template.base_inject import apply_base_template
from md_to_word.template.builder import build_template
from md_to_word.visual_qa.word_pdf import can_render_word_pdf
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

pytestmark = pytest.mark.skipif(
    not can_render_word_pdf()[0], reason="需要本机 Microsoft Word 才能验真"
)


def test_cover_pages_survive_page_by_page(tmp_path: Path) -> None:
    base = tmp_path / "base.docx"
    doc = Document()
    for i in range(3):
        section = doc.sections[-1]
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = "某某大学学位论文"
        doc.add_paragraph(f"封面第 {i + 1} 节")
        if i < 2:
            doc.add_section(WD_SECTION.NEW_PAGE)
    doc.save(base)

    template = tmp_path / "tpl.docx"
    build_template(PRESET, template)
    rendered = write_docx(
        read_markdown("# 第一章 绪论\n\n正文第一段。\n"), template, tmp_path / "r.docx"
    )

    out = tmp_path / "out.docx"
    apply_base_template(base, rendered, 2, out, "第一章绪论")

    assert out.is_file()


def test_word_opens_a_body_with_links_and_footnote_links(tmp_path: Path) -> None:
    """这条只有 Word 能证：关系没搬对时，产物结构上看着齐全，Word 却打不开。

    以前的坏法是正文超链接还带着源包的 rId，在目标包里指到了主题部件上。
    """
    base = tmp_path / "base.docx"
    doc = Document()
    for i in range(2):
        section = doc.sections[-1]
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = "某某大学学位论文"
        doc.add_paragraph(f"封面第 {i + 1} 节")
        if i == 0:
            doc.add_section(WD_SECTION.NEW_PAGE)
    doc.save(base)

    template = tmp_path / "tpl.docx"
    build_template(PRESET, template)
    rendered = write_docx(
        read_markdown(
            "# 第一章 绪论\n\n正文含[超链接](https://example.com/a)，还有脚注[^1]。\n\n"
            "$$E=mc^2$$ {#eq-1}\n\n[^1]: 脚注里的[链接](https://example.com/b)。\n"
        ),
        template,
        tmp_path / "r.docx",
    )

    out = tmp_path / "out.docx"
    # apply 内部会拿 Word 打开产物；打不开就抛 BaseTemplateError，这里就失败
    outcome = apply_base_template(base, rendered, 1, out, ["第一章绪论"])

    assert out.is_file() and outcome.layout_verified


_TOC_FIELD = (
    '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText xml:space="preserve">TOC \\o "1-3" \\h \\z \\u</w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:t>第一章 绪论</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
)


def test_a_toc_in_the_kept_front_matter_is_recomputed_not_called_a_mismatch(
    tmp_path: Path,
) -> None:
    """前置件里的目录是域，Word 排版时按产物的新标题重算——两份的字本来就该不一样。

    以前这一页被当成「封面被改了」：两份真模板的前置件里都有目录域，只要
    `--cover-sections` 把目录留在里面，装了 Word 的机器上一律拒收，用户看到的是「第 9 页
    对不上：原件 173 个词，产物 7 个」——那恰恰是目录被正确重算了。
    """
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    base = tmp_path / "base.docx"
    doc = Document()
    doc.add_paragraph("某某大学")
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_paragraph("")._p.addnext(parse_xml(f"<w:p {nsdecls('w')}/>"))
    doc.paragraphs[-1]._p.addnext(parse_xml(
        _TOC_FIELD.replace("<w:p>", f"<w:p {nsdecls('w')}>").replace(
            '<w:instrText xml:space="preserve">',
            f'<w:instrText {nsdecls("w")} xml:space="preserve">')))
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_paragraph("正文占位")
    doc.save(base)

    template = tmp_path / "tpl.docx"
    build_template(PRESET, template)
    rendered = write_docx(
        read_markdown("# 第三章 实验\n\n这一段只在我们的正文里出现。\n"),
        template, tmp_path / "r.docx",
    )

    outcome = apply_base_template(base, rendered, 2, tmp_path / "out.docx", "这一段只在我们的正文里出现")

    assert (tmp_path / "out.docx").is_file()
    assert any("目录" in note for note in outcome.notes), outcome.notes
