"""把正文灌进学校模板：拦什么、切哪里、灌完包里不能留下什么。

这些都是不开 Word 就能盯住的确定性判据。真正"长得一样不像"只有渲染才知道，
那份在 `test_base_inject_render.py` 里，没装 Word 的机器直接跳过。
"""

from __future__ import annotations

import re
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


def _styleref_args(blob: bytes) -> list[str]:
    """页眉里所有 `STYLEREF "…"` 的样式名。"""
    text = blob.decode("utf-8")
    return [m.group(1) for m in re.finditer(r'STYLEREF\s+"([^"]*)"', text)]


def _chapter_header_format() -> str:
    """章名页眉：`{样式标题:Heading 1}` 会落成一个 STYLEREF 域。"""
    return (
        PRESET
        + "\n页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符\n"
        + "页眉内容：{样式标题:Heading 1}\n"
    )


def test_a_chapter_name_header_mid_document_follows_the_renamed_style(tmp_path: Path) -> None:
    """正文中间那一节的页眉，样式名同样要跟着改。

    这条以前是漏的：`_rehome_rels` 把 `w:headerReference` 当普通关系原样搬走，页眉部件被
    复制一份、`STYLEREF` 里的旧名留在里面；`copy_hf` 随后去 `ours` 里查这个 rId 查不到，
    静默跳过，改写等于没做。结构验真看不出来（封面对得上、包也完整），只有真排过版才
    看得见——页眉上印的是「错误!使用"开始"选项卡将 … 应用于要在此处显示的文字」。
    """
    from md_to_word.template.base_inject import inject_into_base

    manuscript = (
        "---\n---\n\n%% 摘要标题 摘要\n\n%% 摘要 本文提出一种方法。\n\n"
        "{{< section 页码=小写罗马 起始=1 >}}\n\n# 第一章 绪论\n\n正文。\n"
    )
    template = tmp_path / "tpl.docx"
    build_template(_chapter_header_format(), template)
    rendered = write_docx(read_markdown(manuscript), template, tmp_path / "rendered.docx")

    base = _school_base(tmp_path / "base.docx", sections=2)
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)

    with zipfile.ZipFile(base) as zb:
        base_parts = set(zb.namelist())
    with zipfile.ZipFile(out) as z:
        styles = etree.fromstring(z.read("word/styles.xml"))
        names = {
            (s.find(qn("w:name")).get(qn("w:val")) if s.find(qn("w:name")) is not None else "")
            for s in styles.iter(qn("w:style"))
        }
        # 只看**灌进来的**页眉页脚：学校模板自己那几份原样保留，里面写着什么不归我们管
        generated = [
            n for n in z.namelist()
            if re.search(r"word/[^/]*(header|footer)[^/]*\.xml$", n) and n not in base_parts
        ]
        args = [a for n in generated for a in _styleref_args(z.read(n))]

    assert args, "这份稿件应当生成带 STYLEREF 的页眉——没有的话这条测试是空转的"
    dangling = [a for a in args if a not in names]
    assert not dangling, f"页眉指向了不存在的样式：{dangling}（现有样式名 {sorted(names)[:5]}…）"


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
    """学校模板常挂着作者自己电脑上的 .dot（如 `file:///D:/templates/...`）。

    到了别人的机器上这个文件不存在：Word 打开会问「是否更新域」，点「是」去加载失败，
    域更新不成功——目录页码就停在 1，得手动再按 F9。它属于对方的写作环境，不属于交付物。
    """
    from md_to_word.template.base_inject import inject_into_base

    base = _school_base(tmp_path / "base.docx", sections=2)
    # 给底模装一个指向外部路径的挂载模板
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
        '2006/relationships/attachedTemplate" Target="file:///D:/templates/thesis.dot" '
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


def test_a_zero_byte_theme_directory_does_not_fail_verification(tmp_path: Path) -> None:
    """包里带 `word/theme/` 这个零字节目录条目的模板，不能被判成"主题被改动"。

    实测的一份模板就是这样：目录项在原件里有、python-docx 存盘时不写它。照字面比字典，
    一份根本没动过主题的产物会被拒收——用户看到的是「结构验真没通过」，白丢一次。
    """
    from md_to_word.template.base_inject import inject_into_base, verify_structure

    base = _school_base(tmp_path / "base.docx", sections=2)
    # 加一个零字节目录条目，模拟那种模板包
    with zipfile.ZipFile(base, "a") as z:
        z.writestr("word/theme/", b"")
    with zipfile.ZipFile(base) as z:
        assert "word/theme/" in z.namelist()

    rendered = _rendered(tmp_path, "# 第一章 绪论\n\n正文。\n")
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)

    ok, why = verify_structure(base, out, 1)
    assert ok, why


def test_a_relationship_pointing_at_a_missing_part_is_refused(tmp_path: Path) -> None:
    """关系还在、部件被剥掉了：这份文件自己就是坏的，python-docx 打开时直接抛 KeyError。

    学校模板转几道手之后页眉部件丢失是见过的。以前它崩在 `Document()` 里，报出来是一句
    traceback；现在体检就拦住，说清楚是哪条关系断了。
    """
    base = _school_base(tmp_path / "base.docx", sections=2)
    with zipfile.ZipFile(base) as z:
        members = {n: z.read(n) for n in z.namelist()}
    members["word/_rels/document.xml.rels"] = members[
        "word/_rels/document.xml.rels"
    ].replace(
        b"</Relationships>",
        b'<Relationship Id="rIdHdr" Type="http://schemas.openxmlformats.org/officeDocument/'
        b'2006/relationships/header" Target="header99.xml"/></Relationships>',
    )
    with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in members.items():
            z.writestr(name, blob)

    report = inspect_base(base, 1)

    assert not report.ok
    assert any("header99.xml" in msg for msg in report.blocking), report.blocking


def test_a_sound_base_is_not_reported_as_broken(tmp_path: Path) -> None:
    """断了才算坏：正常模板（含图片、超链接这些真有关系表的）不能被这条检查误伤。"""
    base = _school_base(tmp_path / "base.docx", sections=3)

    assert inspect_base(base, 2).ok
    assert inspect_base(base).ok


def test_a_protected_base_says_so_instead_of_producing_a_read_only_file(tmp_path: Path) -> None:
    """底模开着文档保护：产物照样带保护，用户在 Word 里改不了。这不是错，但得说一声。"""
    base = _school_base(tmp_path / "base.docx", sections=2)
    with zipfile.ZipFile(base) as z:
        members = {n: z.read(n) for n in z.namelist()}
    members["word/settings.xml"] = members["word/settings.xml"].replace(
        b"</w:settings>",
        b'<w:documentProtection w:edit="readOnly" w:enforcement="1"/></w:settings>',
    )
    with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in members.items():
            z.writestr(name, blob)

    report = inspect_base(base, 1)

    assert report.ok, report.blocking          # 不是拒绝，是提醒
    assert any("文档保护" in note for note in report.notes), report.notes


_TOC_P = (
    '<w:p {ns}><w:r><w:fldChar w:fldCharType="begin"/></w:r>'
    '<w:r><w:instrText {ns} xml:space="preserve">TOC \\o "1-3" \\h \\z \\u</w:instrText></w:r>'
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
    '<w:r><w:t>第一章 绪论</w:t></w:r>'
    '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
)


def _base_with_toc(path: Path, toc_paragraph: str) -> Path:
    """封面 | 目录 | 正文占位：三节，目录在第 2 节。"""
    doc = Document()
    doc.add_paragraph("某某大学")
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.paragraphs[-1]._p.addnext(parse_xml(toc_paragraph.format(ns=nsdecls("w"))))
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_paragraph("正文占位")
    doc.save(path)
    return path


def test_a_toc_in_the_front_matter_must_not_be_kept(tmp_path: Path) -> None:
    """模板里的目录不能留：它是作者照着自己的正文排的，还是域，Word 会按我们的新标题重算。

    留着不但印出对不上的条目，还让逐页验真永远比不平——两份的目录本来就该不一样。
    所以切点必须停在目录之前，切深了直接拒绝，并告诉人最多能留几节。
    """
    base = _base_with_toc(tmp_path / "base.docx", _TOC_P)

    report = inspect_base(base, 2)

    assert not report.ok
    assert any("第 2 节是目录" in msg for msg in report.blocking), report.blocking
    assert any("最多保留前 1 节" in msg for msg in report.blocking), report.blocking
    assert inspect_base(base, 1).ok


def test_a_hand_typed_toc_is_caught_by_its_style(tmp_path: Path) -> None:
    """手工一条条排的目录没有域代码，但用的是目录样式——同样不能留。"""
    base = _base_with_toc(
        tmp_path / "base.docx",
        '<w:p {ns}><w:pPr><w:pStyle w:val="TOC1"/></w:pPr>'
        "<w:r><w:t>第一章 绪论 …… 1</w:t></w:r></w:p>",
    )

    assert not inspect_base(base, 2).ok
    assert inspect_base(base, 1).ok


def test_a_toc_in_the_body_does_not_block_the_cover(tmp_path: Path) -> None:
    """目录在切点之后（正文里）就不归我们管——那是要被替换掉的部分，不能因此拒收。"""
    doc = Document()
    doc.add_paragraph("某某大学")
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.paragraphs[-1]._p.addnext(parse_xml(_TOC_P.format(ns=nsdecls("w"))))
    path = tmp_path / "base.docx"
    doc.save(path)

    assert inspect_base(path, 1).ok


def test_a_renamed_style_takes_its_next_and_link_with_it() -> None:
    """改名要改全：`basedOn`、`next`、`link` 三处都得跟着走。

    以前只改了 `basedOn`。`next` 还指着学校那条 `Normal`——在 Word 里标题后按回车，接上来的是
    学校的正文样式，不是我们的。
    """
    src = Document()
    src.styles.element.append(parse_xml(
        f'<w:style {nsdecls("w")} w:type="paragraph" w:styleId="BodyText">'
        '<w:name w:val="正文"/><w:pPr><w:spacing w:line="400" w:lineRule="exact"/></w:pPr>'
        "</w:style>"))
    src.styles.element.append(parse_xml(
        f'<w:style {nsdecls("w")} w:type="paragraph" w:styleId="HeadingX">'
        '<w:name w:val="标题"/><w:basedOn w:val="BodyText"/><w:next w:val="BodyText"/>'
        '<w:link w:val="HeadingXChar"/></w:style>'))
    dst = Document()
    dst.styles.element.append(parse_xml(
        f'<w:style {nsdecls("w")} w:type="paragraph" w:styleId="BodyText">'
        '<w:name w:val="正文"/><w:pPr><w:spacing w:line="240" w:lineRule="auto"/></w:pPr>'
        "</w:style>"))

    ids, names = {}, {}
    _merge_styles(src, dst, ids, names, qn)

    merged = next(s for s in dst.styles.element.findall(qn("w:style"))
                  if s.get(qn("w:styleId")) == "HeadingX")
    assert merged.find(qn("w:basedOn")).get(qn("w:val")) == "mdw-BodyText"
    assert merged.find(qn("w:next")).get(qn("w:val")) == "mdw-BodyText"
    assert merged.find(qn("w:link")).get(qn("w:val")) == "HeadingXChar"


def test_a_style_reference_left_dangling_is_caught(tmp_path: Path) -> None:
    """正文引用了 styles.xml 里没有的样式：Word 悄悄退回普通段落，字体行距全丢。

    包是完整的、结构验真本来一路放行——所以这条必须自己查一遍。
    """
    from md_to_word.template.base_inject import inject_into_base, verify_structure

    base = _school_base(tmp_path / "base.docx", sections=2)
    rendered = _rendered(tmp_path, "# 第一章 绪论\n\n正文。\n")
    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)
    assert verify_structure(base, out, 1)[0]

    with zipfile.ZipFile(out) as z:
        members = {n: z.read(n) for n in z.namelist()}
    members["word/document.xml"] = members["word/document.xml"].replace(
        b'w:val="mdw-', b'w:val="gone-', 1)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, blob in members.items():
            z.writestr(name, blob)

    ok, why = verify_structure(base, out, 1)
    assert not ok and "样式" in why, why


def test_header_styles_metadata_survives_injection(tmp_path: Path) -> None:
    """灌入后产物要带着自己的 `customXml/mdw_meta.xml`。

    不搬这个部件的话，产物丢掉「哪些样式加入了页眉」——再拿它去反推时，
    只能保守地说「有 STYLEREF 但不知道谁进页眉」。自描述信息不该在合并时丢掉。
    """
    from md_to_word.template.generator import read_header_styles_meta

    base = _school_base(tmp_path / "base.docx", sections=3)
    template = tmp_path / "t.docx"
    build_template(PRESET, template)
    rendered = write_docx(
        read_markdown("# 第一章\n\n正文。\n\n%% 参考文献标题 参 考 文 献\n\n文献。\n"),
        template,
        tmp_path / "r.docx",
        header_styles={"References Title"},
    )
    out = tmp_path / "o.docx"
    apply_base_template(base, rendered, 2, out, "第一章")

    assert read_header_styles_meta(out) == {"References Title"}


def test_injected_package_keeps_the_doc_level_settings_we_declare(tmp_path: Path) -> None:
    """校对语言与标点压缩不属于任何一条样式，只搬 `w:style` 的话它们会被底模顶掉。

    这两项恰恰是生成器专门写进去的：不写中文校对语言，Word 就拿英文词典查中文，
    整篇标成拼写错误。灌完底模它们没了，等于 `format.txt` 里那两行白写。
    """
    from md_to_word.template.base_inject import inject_into_base

    base = _school_base(tmp_path / "base.docx", sections=1)

    # 底模里先把这两项写成恩「别的值」，才能看出注入有没有搬过去
    with zipfile.ZipFile(base) as z:
        styles = z.read("word/styles.xml")
    assert b"docDefaults" in styles

    rendered = _rendered(
        tmp_path,
        '---\n---\n\n# 一 引言\n\n正文一段。\n\n%% 正文 宋体 小四\n',
    )
    with zipfile.ZipFile(rendered) as z:
        want_lang = etree.fromstring(z.read("word/styles.xml"))
        want_settings = etree.fromstring(z.read("word/settings.xml"))
    w = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    wanted = want_lang.find(f"{w}docDefaults/{w}rPrDefault/{w}rPr/{w}lang")
    expected_lang = None if wanted is None else wanted.get(f"{w}eastAsia")
    wanted_cs = want_settings.find(f"{w}characterSpacingControl")
    expected_cs = None if wanted_cs is None else wanted_cs.get(f"{w}val")
    assert expected_lang, "生成器本该写中文校对语言"

    out = tmp_path / "out.docx"
    inject_into_base(base, rendered, 1, out)

    with zipfile.ZipFile(out) as z:
        got_styles = etree.fromstring(z.read("word/styles.xml"))
        got_settings = etree.fromstring(z.read("word/settings.xml"))
    got = got_styles.find(f"{w}docDefaults/{w}rPrDefault/{w}rPr/{w}lang")
    assert got is not None and got.get(f"{w}eastAsia") == expected_lang, (
        "校对语言没搬过去：灌底模之后 Word 会用英文词典查中文"
    )
    if expected_cs:
        got_cs = got_settings.find(f"{w}characterSpacingControl")
        assert got_cs is not None and got_cs.get(f"{w}val") == expected_cs, (
            "标点压缩没搬过去"
        )
