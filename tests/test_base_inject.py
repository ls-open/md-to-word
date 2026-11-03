"""把正文灌进学校模板：拦什么、切哪里、灌完包里不能留下什么。

这些都是不开 Word 就能盯住的确定性判据。真正"长得一样不像"只有渲染才知道，
那份在 `test_base_inject_render.py` 里，没装 Word 的机器直接跳过。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.enum.section import WD_SECTION
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from lxml import etree

from md_to_word.model.reader import read_markdown
from md_to_word.template.base_inject import (
    BaseTemplateError,
    _cut_after_section,
    _merge_styles,
    apply_base_template,
    dropped_head,
    inspect_base,
)
from md_to_word.template.builder import build_template
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")


def _school_base(path: Path, sections: int = 2) -> Path:
    """一份"学校模板"：几节、每节有点内容、带页眉。"""
    doc = Document()
    for i in range(sections):
        section = doc.sections[-1]
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = "某某大学学位论文"
        doc.add_paragraph(f"封面第{i + 1}节")
        if i < sections - 1:
            doc.add_section(WD_SECTION.NEW_PAGE)
    doc.save(path)
    return path


def _rendered(tmp_path: Path, manuscript: str) -> Path:
    template = tmp_path / "tpl.docx"
    build_template(PRESET, template)
    return write_docx(read_markdown(manuscript), template, tmp_path / "rendered.docx")


def test_rejects_a_macro_document(tmp_path: Path) -> None:
    """带宏的文档改不了也不该改——一开始就拒绝。"""
    base = _school_base(tmp_path / "base.docx")
    with zipfile.ZipFile(base, "a") as z:
        z.writestr("word/vbaProject.bin", b"\x00")

    report = inspect_base(base, 1)

    assert not report.ok
    assert any("宏" in msg for msg in report.blocking)


def test_rejects_a_suffix_it_cannot_handle(tmp_path: Path) -> None:
    fake = tmp_path / "base.docm"
    fake.write_bytes(b"not a docx")

    report = inspect_base(fake, 1)

    assert not report.ok
    assert any(".docx" in msg for msg in report.blocking)


def test_rejects_when_there_are_not_enough_sections(tmp_path: Path) -> None:
    """切点比文件里的节还多，说明参数给错了——不猜，直接拒绝。"""
    base = _school_base(tmp_path / "base.docx", sections=2)

    report = inspect_base(base, 5)

    assert not report.ok
    assert any("节" in msg for msg in report.blocking)


def test_cut_keeps_exactly_the_declared_sections(tmp_path: Path) -> None:
    base = _school_base(tmp_path / "base.docx", sections=4)
    doc = Document(base)

    _cut_after_section(doc.element.body, 2, qn)
    # 切完还有"末节 sectPr"，所以节数比保留数多一：写盘前才合并
    assert len(doc.sections) == 3
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert texts == ["封面第1节", "封面第2节"]


def test_dropped_head_names_the_section_after_the_cut(tmp_path: Path) -> None:
    """切早了丢掉的是后面的封面，验真看不出来——所以必须把它摆到人眼前。"""
    base = _school_base(tmp_path / "base.docx", sections=4)

    assert dropped_head(base, 2) == "封面第3节"


def test_collided_style_is_renamed_by_id_and_name(tmp_path: Path) -> None:
    """同名不同义的两条样式会让 Word 挑错那一条，整页行高跟着变——名字也要改。"""
    src = Document()
    src.styles.element.append(parse_xml(
        f'<w:style {nsdecls("w")} w:type="paragraph" w:styleId="BodyText">'
        '<w:name w:val="正文"/><w:pPr><w:spacing w:line="400" w:lineRule="exact"/></w:pPr>'
        "</w:style>"))
    dst = Document()
    dst.styles.element.append(parse_xml(
        f'<w:style {nsdecls("w")} w:type="paragraph" w:styleId="BodyText">'
        '<w:name w:val="正文"/><w:pPr><w:spacing w:line="240" w:lineRule="auto"/></w:pPr>'
        "</w:style>"))

    ids, names = {}, {}
    _merge_styles(src, dst, ids, names, qn)

    assert ids["BodyText"] == "mdw-BodyText"
    assert names["正文"] == "正文（模板）"
    style_names = [s.find(qn("w:name")).get(qn("w:val"))
                   for s in dst.styles.element.findall(qn("w:style"))]
    assert len(style_names) == len(set(style_names)), "两条同名样式会让 Word 挑错定义"


def test_injected_package_keeps_footnote_references_resolvable(tmp_path: Path) -> None:
    """脚注引用指向目标里不存在的 id，Word 直接判文件损坏——这是实测出来的。"""
    base = _school_base(tmp_path / "base.docx", sections=1)
    rendered = _rendered(tmp_path, "# 一\n\n正文[^1]。\n\n[^1]: 脚注内容。\n")

    out = tmp_path / "out.docx"
    with pytest.raises(BaseTemplateError):
        # 没有 Word 的机器上验真会拒绝，但注入本身要先把包做得能自洽
        apply_base_template(base, rendered, 1, out, "正文")

    # 无论验真是否通过，注入口径本身必须把脚注搬过去：
    from md_to_word.template.base_inject import inject_into_base

    inject_into_base(base, rendered, 1, out)
    document = etree.fromstring(zipfile.ZipFile(out).read("word/document.xml"))
    used = {n.get(qn("w:id")) for n in document.iter(qn("w:footnoteReference"))}
    notes = etree.fromstring(zipfile.ZipFile(out).read("word/footnotes.xml"))
    defined = {n.get(qn("w:id")) for n in notes.iter(qn("w:footnote"))}
    assert used and used <= defined


def test_injected_package_has_a_single_default_style_per_type(tmp_path: Path) -> None:
    """一种类型两个默认样式，Word 也判损坏。"""
    base = _school_base(tmp_path / "base.docx", sections=1)
    rendered = _rendered(tmp_path, "# 一\n\n正文。\n")

    out = tmp_path / "out.docx"
    from md_to_word.template.base_inject import inject_into_base

    inject_into_base(base, rendered, 1, out)
    styles = etree.fromstring(zipfile.ZipFile(out).read("word/styles.xml"))
    defaults = [
        s.get(qn("w:type")) for s in styles.iter(qn("w:style")) if s.get(qn("w:default")) == "1"
    ]
    assert len(defaults) == len(set(defaults)), f"默认样式重复：{defaults}"


def test_structure_verification_works_without_word(tmp_path: Path, monkeypatch) -> None:
    """没有 Word 的机器（Windows）也要能产出：结构那一关照跑，版面交给人工核对。"""
    from md_to_word.template import base_inject

    base = _school_base(tmp_path / "base.docx", sections=3)
    rendered = _rendered(tmp_path, "# 第一章 绪论\n\n正文。\n")
    monkeypatch.setattr(base_inject, "can_render_word_pdf", lambda: (False, "not-darwin"))

    notes = base_inject.apply_base_template(base, rendered, 2, tmp_path / "out.docx", "第一章绪论")

    assert (tmp_path / "out.docx").is_file()
    assert any("结构验真" in n for n in notes)


def test_structure_verification_catches_a_touched_cover(tmp_path: Path) -> None:
    """封面的任何一个字节被改动，结构验真就要报出来——这是跨平台也守得住的那一半。"""
    from md_to_word.template.base_inject import inject_into_base, verify_structure

    base = _school_base(tmp_path / "base.docx", sections=3)
    rendered = _rendered(tmp_path, "# 第一章 绪论\n\n正文。\n")
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 2, out)

    ok, _ = verify_structure(base, out, 2)
    assert ok

    doc = Document(out)
    doc.paragraphs[0].runs[0].text = "被改过的封面"
    doc.save(out)
    ok, why = verify_structure(base, out, 2)
    assert not ok and "改动" in why
