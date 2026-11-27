"""灌完必须和原件长得一样——这条只能用真 Word 验，没装 Word 的机器整文件跳过。

判据就是坐标：Word 排过版才知道分页有没有变、空白页有没有丢，这些从 OOXML 里看不出来。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_BREAK
from lxml import etree

from md_to_word.model.reader import read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.template.base_inject import _page_texts, apply_base_template
from md_to_word.template.builder import build_template
from md_to_word.visual_qa.word_pdf import can_render_word_pdf
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

pytestmark = [
    pytest.mark.word,
    pytest.mark.skipif(not can_render_word_pdf()[0], reason="需要本机 Microsoft Word 才能验真"),
]


def _compat15(path: Path) -> Path:
    """python-docx 默认是兼容模式 14 + doNotCompress；对齐成中文正文的设置。"""
    from tests.docx_helpers import set_character_spacing, set_compat_mode

    set_compat_mode(path, "15")
    set_character_spacing(path, "compressPunctuation")
    return path


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
    _compat15(base)

    template = tmp_path / "tpl.docx"
    build_template(PRESET, template)
    rendered = write_docx(
        read_markdown("# 第一章 绪论\n\n正文第一段。\n"), template, tmp_path / "r.docx"
    )

    out = tmp_path / "out.docx"
    apply_base_template(base, rendered, 2, out, "第一章绪论")

    assert out.is_file()


def test_single_section_cut_starts_the_body_on_a_new_page(tmp_path: Path) -> None:
    """单节模板切在半页时，正文从下一页开始——不能挤回同一页，也不能多出空白页。

    结构上分节符是 nextPage；这条用 Word 排一次版，直接看 PDF 的页边界。
    底模和格式都开了对称页边距（文档级设置必须一致才能灌入）；前置件正好两页，
    正文从第 3 页开始，不能因为重新编号再插一张空白页。
    """
    base = tmp_path / "base.docx"
    doc = Document()
    doc.add_paragraph("某某大学硕士学位论文")
    doc.add_paragraph("作者：张三")
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    doc.add_paragraph("版权使用授权书")
    doc.add_paragraph("本人郑重声明，本论文是在导师指导下独立完成的研究成果。")
    signature = doc.add_paragraph("作者签名：________    导师签名：________")
    # 真实模板里 Ctrl+Enter 往往就落在这一段的末尾，而不是单独一段；
    # 分页符和切点同段时最容易多出空白页，所以这里按这种写法验。
    signature.add_run().add_break(WD_BREAK.PAGE)
    doc.add_paragraph("这里是被丢弃的旧正文。")
    doc.save(base)

    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(base) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    settings = etree.fromstring(parts["word/settings.xml"])
    etree.SubElement(settings, w + "mirrorMargins")
    # python-docx 建出来是兼容模式 14；和本工具的正文（15）一致才能一起验。
    for el in settings.iter(w + "compatSetting"):
        if el.get(w + "name") == "compatibilityMode":
            el.set(w + "val", "15")
    parts["word/settings.xml"] = etree.tostring(
        settings, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in parts.items():
            z.writestr(name, blob)
    from tests.docx_helpers import set_character_spacing

    set_character_spacing(base, "compressPunctuation")

    md = tmp_path / "m.md"
    md.write_text("# 第一章 引言\n\n正文第一段。\n", encoding="utf-8")
    fmt = tmp_path / "f.txt"
    fmt.write_text(PRESET.rstrip() + "\n对称页边距：开\n", encoding="utf-8")

    result = run_export_pipeline(ExportOptions(
        input_path=md, output_path=tmp_path / "out.docx", format_path=fmt,
        base_template=base, keep_until="作者签名", make_pdf=True,
    ))

    assert result.ok, result.errors
    pages = _page_texts(result.output_pdf)
    assert len(pages) == 3, [p[:30] for p in pages]
    assert "作者签名" in pages[1]
    assert "第一章" not in pages[1], "正文不能挤回授权书的半页"
    assert "第一章" in pages[2]
    assert "旧正文" not in "".join(pages), "切点之后的内容不应保留"


def test_mirror_on_with_a_one_page_front_refuses_the_blank_page(tmp_path: Path) -> None:
    """镜像 + 1 页前置件 + 正文从第 1 页重新编号，Word 会插一张空白页。

    派生底模自己也可能带同一张空白页，所以验真必须拿原始底模同页做基准；这里直接
    断言导出被拒，而不是把空白页当成交付物。
    """
    from tests.docx_helpers import align_base

    base = tmp_path / "base.docx"
    doc = Document()
    doc.add_paragraph("封面第一页：某某大学")
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
    doc.add_paragraph("版权使用授权书")
    doc.add_paragraph("作者签名：________")
    doc.save(base)
    align_base(base, punctuation="compressPunctuation", mirror=True)

    md = tmp_path / "m.md"
    md.write_text("# 第一章 引言\n\n正文第一段。\n", encoding="utf-8")
    fmt = tmp_path / "f.txt"
    fmt.write_text(PRESET.rstrip() + "\n对称页边距：开\n", encoding="utf-8")

    result = run_export_pipeline(ExportOptions(
        input_path=md, output_path=tmp_path / "out.docx", format_path=fmt,
        base_template=base, keep_until="封面第一页", make_pdf=True,
    ))

    assert not result.ok
    assert not (tmp_path / "out.docx").exists()
    joined = " ".join(result.errors)
    assert "空白页" in joined or "多插了一页" in joined, joined


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
    _compat15(base)

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

