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
    from md_to_word.visual_qa import word_pdf

    monkeypatch.setattr(word_pdf, "can_render_word_pdf", lambda: (False, "not-darwin"))

    outcome = base_inject.apply_base_template(base, rendered, 2, tmp_path / "out.docx", "第一章绪论")

    assert (tmp_path / "out.docx").is_file()
    assert not outcome.layout_verified, "没有 Word 就不能声称验过版面"
    assert any("结构验真" in n for n in outcome.notes)


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


def test_styleref_field_follows_the_renamed_style() -> None:
    """域里的样式名要跟着改：`STYLEREF` 后面是两个空格，样式名在 styles.xml 里还是小写的——
    按字面替换一次也命中不了，页眉会指向一个已经不用的样式。"""
    from md_to_word.template.base_inject import _rewrite_part

    blob = (b'<w:p><w:r><w:instrText xml:space="preserve">'
            b'STYLEREF  "Heading 1"   \\* MERGEFORMAT </w:instrText></w:r></w:p>')

    out = _rewrite_part(blob, {}, {"heading 1": "heading 1（模板）"}).decode("utf-8")

    assert "heading 1（模板）" in out
    assert '"Heading 1"' not in out


def test_sentinel_reads_through_inline_wrappers() -> None:
    """正文以加粗开头时，哨兵不能跳过整段——跳了就会拿后面某一段去定位封面页数。"""
    from md_to_word.pipeline import _first_text

    doc = read_markdown("**绪论**与背景\n\n第二段。\n")

    assert _first_text(doc.blocks) == "绪论与背景"


def _rels_of(result: Path, member: str) -> dict[str, tuple[str, str]]:
    return {
        r.get("Id"): (r.get("Type").rsplit("/", 1)[-1], r.get("Target"))
        for r in etree.fromstring(zipfile.ZipFile(result).read(member))
    }


def test_a_link_in_the_body_still_points_at_its_url(tmp_path: Path) -> None:
    """关系属于**包**，不属于内容流：正文搬了家，源包里的 `rId8` 就换成别人的编号了。

    以前只给图片重挂过关系，超链接没管，于是正文链接指到了主题部件上——Word 打不开，
    而没装 Word 的机器上结构验真一路放行。
    """
    from md_to_word.template.base_inject import inject_into_base

    base = _school_base(tmp_path / "base.docx", sections=2)
    rendered = _rendered(tmp_path, "# 一\n\n参见[说明](https://example.com/a)。\n")
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)

    doc = etree.fromstring(zipfile.ZipFile(out).read("word/document.xml"))
    rels = _rels_of(out, "word/_rels/document.xml.rels")
    link = next(n for n in doc.iter() if n.tag.endswith("}hyperlink"))

    assert rels[link.get(qn("r:id"))] == ("hyperlink", "https://example.com/a")


def test_a_link_inside_a_footnote_resolves_in_its_own_part(tmp_path: Path) -> None:
    """脚注有自己的一张关系表，正文那张管不到它。"""
    from md_to_word.template.base_inject import inject_into_base

    base = _school_base(tmp_path / "base.docx", sections=2)
    rendered = _rendered(
        tmp_path, "# 一\n\n正文[^1]。\n\n[^1]: 见[说明](https://example.com/b)。\n"
    )
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)

    notes = etree.fromstring(zipfile.ZipFile(out).read("word/footnotes.xml"))
    link = next((n for n in notes.iter() if n.tag.endswith("}hyperlink")), None)
    assert link is not None, "脚注里的链接没搬过来"
    rels = _rels_of(out, "word/_rels/footnotes.xml.rels")
    assert rels[link.get(qn("r:id"))] == ("hyperlink", "https://example.com/b")


def test_structure_check_catches_a_link_pointing_at_the_wrong_relationship(
    tmp_path: Path,
) -> None:
    """验真得能抓住「关系还在、类型不对」——那正是 Word 打不开、结构检查却看不出来的样子。"""
    from md_to_word.template.base_inject import inject_into_base, verify_structure

    base = _school_base(tmp_path / "base.docx", sections=2)
    rendered = _rendered(tmp_path, "# 一\n\n参见[说明](https://example.com/a)。\n")
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)
    assert verify_structure(base, out, 1)[0]

    rels_member = "word/_rels/document.xml.rels"
    with zipfile.ZipFile(out) as z:
        members = {n: z.read(n) for n in z.namelist()}
    rels = etree.fromstring(members[rels_member])
    for rel in rels:
        if rel.get("Type", "").endswith("/hyperlink"):
            rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/"
                            "relationships/theme")
    members[rels_member] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8",
                                          standalone=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in members.items():
            z.writestr(name, blob)

    ok, why = verify_structure(base, out, 1)
    assert not ok and "关系" in why


def test_the_attached_dot_template_is_dropped(tmp_path: Path) -> None:
    """学校模板常挂着作者自己电脑上的 .dot（`file:///E:\\...`）。

    到了别人的机器上这个文件不存在：Word 打开会问「是否更新域」，点「是」去加载失败，
    域更新不成功——目录页码就停在 1，得手动再按 F9。它属于对方的写作环境，不属于交付物。
    """
    from md_to_word.template.base_inject import inject_into_base

    base = _school_base(tmp_path / "base.docx", sections=2)
    # 给底模装一个指向 Windows 本机路径的挂载模板
    with zipfile.ZipFile(base) as z:
        members = {n: z.read(n) for n in z.namelist()}
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    ns_r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    root = etree.fromstring(members["word/settings.xml"])
    node = etree.SubElement(root, f"{{{ns_w}}}attachedTemplate")
    node.set(f"{{{ns_r}}}id", "rIdX")
    members["word/settings.xml"] = etree.tostring(
        root, xml_declaration=True, encoding="UTF-8", standalone=True)
    members["word/_rels/settings.xml.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rIdX" Type="http://schemas.openxmlformats.org/officeDocument/'
        '2006/relationships/attachedTemplate" Target="file:///E:/work/模板.dot" '
        'TargetMode="External"/></Relationships>'
    ).encode("utf-8")
    with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in members.items():
            z.writestr(name, blob)

    rendered = _rendered(tmp_path, "# 第一章 绪论\n\n正文。\n")
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)

    left = zipfile.ZipFile(out).read("word/settings.xml").decode("utf-8")
    assert "attachedTemplate" not in left


def test_find_the_section_by_its_text(tmp_path: Path) -> None:
    """人说的是内容，机器要的是节数——这一步只看 XML，Windows 上也走得通。"""
    from md_to_word.template.base_inject import section_outline, sections_until_text

    base = _school_base(tmp_path / "base.docx", sections=3)
    doc = Document(base)
    doc.paragraphs[-1].runs[0].text = "版权使用授权书 本人同意……"
    doc.save(base)

    assert sections_until_text(base, "版权使用授权书") == [3]
    assert sections_until_text(base, "根本不存在的句子") == []
    assert len(section_outline(base)) == 3


def test_ambiguous_anchor_is_refused_not_guessed(tmp_path: Path) -> None:
    """同一段文字在两节里都有，停在哪就不确定了——报出来，别挑一个。"""
    from md_to_word.template.base_inject import sections_until_text

    base = _school_base(tmp_path / "base.docx", sections=3)
    doc = Document(base)
    for paragraph in doc.paragraphs:
        if paragraph.runs:
            paragraph.runs[0].text = "版权使用授权书"
    doc.save(base)

    assert len(sections_until_text(base, "版权使用授权书")) > 1
