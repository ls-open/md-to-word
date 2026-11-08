"""读不出来就必须**说出来**。

这套实现的底线是"不确定的列进需人工确认，不猜值填空"。但还有一类更坏的失败：参考文件
里明明有、草稿里没有，**而且一个字都不提** —— 用户照草稿排完版才发现学校模板上的方框、
表头灰底、页眉 logo 全不见了。下面每一条都是那种"静默丢"，判据是**草稿的需确认清单里
必须出现它**（或表格行本身读得出来）。
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from docx import Document

from md_to_word.template.extractor import (Ref, q, read_decor, read_limitations, read_table)


def _style_of(document, style_id: str):
    for style in document.styles.element.findall(q("style")):
        if style.get(q("styleId")) == style_id:
            return style
    raise AssertionError(f"没有 {style_id}")


def _paragraph_properties(document, style_id: str):
    """样式上已有的 `pPr`，没有就补一个（只在测试里造属性用）。"""
    style = _style_of(document, style_id)
    existing = style.find(q("pPr"))
    if existing is not None:
        return existing
    created = style.makeelement(q("pPr"), {})
    style.append(created)
    return created


def test_table_style_actually_used_is_read(tmp_path):
    """表格用的是 Table Grid：按文档自己写的 tblStyle 去读，别只认叫 table 的那个。"""
    document = Document()
    document.add_table(rows=2, cols=2, style="Table Grid")
    path = tmp_path / "reference.docx"
    document.save(path)

    lines, doubt = read_table(Ref(path, "zh"))
    # 断言具体取值：只断"读出了一行"的话，读错样式也一样通过
    assert lines == ["表格：居中 全网格线 线宽上0.5磅 线宽底0.5磅"], (lines, doubt)


def test_table_without_style_is_reported(tmp_path):
    """表格没挂样式（边框靠直接格式）：读不出来，但要说出来。"""
    document = Document()
    document.add_table(rows=2, cols=2)
    path = tmp_path / "reference.docx"
    document.save(path)

    lines, doubt = read_table(Ref(path, "zh"))
    assert lines == [], lines
    assert any("没有挂样式" in note for note in doubt), doubt


def test_table_style_without_definition_is_reported(tmp_path):
    """表格引用的样式在参考文件里没有定义：要说出来，不能当作"没有表格"。"""
    document = Document()
    document.add_table(rows=2, cols=2)
    table_style = document.styles.element.makeelement(q("style"), {})
    table_style.set(q("type"), "table")
    table_style.set(q("styleId"), "GhostTable")
    table_style.append(table_style.makeelement(q("name"), {q("val"): "Ghost Table"}))
    document.styles.element.append(table_style)
    document.tables[0].style = document.styles["Ghost Table"]
    # 把定义撤掉，只留引用：真实模板里"样式被删但表格还挂着它"就是这样
    for style in list(document.styles.element.findall(q("style"))):
        if style.get(q("styleId")) == "GhostTable":
            document.styles.element.remove(style)
    path = tmp_path / "reference.docx"
    document.save(path)

    lines, doubt = read_table(Ref(path, "zh"))
    assert lines == [], lines
    assert any("没有它的定义" in note for note in doubt), doubt


def test_paragraph_side_borders_are_reported(tmp_path):
    """样式用了左边框 / 上边框：格式文件只能写下边框，其余几边必须进需确认清单。"""
    document = Document()
    properties = _paragraph_properties(document, "Normal")
    borders = properties.makeelement(q("pBdr"), {})
    for side in ("top", "left"):
        borders.append(borders.makeelement(q(side), {q("val"): "single", q("sz"): "8"}))
    properties.append(borders)
    path = tmp_path / "reference.docx"
    document.save(path)

    _, doubt = read_limitations(Ref(path, "zh"))
    assert any("上边框" in note and "左边框" in note for note in doubt), doubt


def test_shading_is_reported(tmp_path):
    """段落底纹表达不了：要说出来，且一条写在基部样式上的底纹只报一次。"""
    document = Document()
    properties = _paragraph_properties(document, "Normal")
    properties.append(properties.makeelement(q("shd"), {q("fill"): "D9D9D9"}))
    # 造几个派生样式并在正文里真的用上：夹具里没有派生样式的话，"只报一次"对任何实现
    # 都成立（沿链遍历只会刷出更多条），这条断言就抓不到它想抓的回归
    for level in (1, 2, 3):
        paragraph = document.add_paragraph(f"标题 {level}")
        paragraph._p.get_or_add_pPr().append(
            paragraph._p.pPr.makeelement(q("pStyle"), {q("val"): f"Heading{level}"}))
    path = tmp_path / "reference.docx"
    document.save(path)

    _, doubt = read_limitations(Ref(path, "zh"))
    shading_notes = [note for note in doubt if "底纹" in note]
    assert len(shading_notes) == 1, doubt      # 基部样式上的底纹不能顺着 basedOn 刷屏
    assert "Normal" in shading_notes[0], shading_notes
    assert "Heading" not in shading_notes[0], shading_notes


def test_only_bottom_border_is_not_reported(tmp_path):
    """只写下边框（本工具表达得了）时不能进清单，否则每份参考文件都会多一条噪音。"""
    document = Document()
    properties = _paragraph_properties(document, "Normal")
    borders = properties.makeelement(q("pBdr"), {})
    borders.append(borders.makeelement(q("bottom"), {q("val"): "single", q("sz"): "8"}))
    properties.append(borders)
    path = tmp_path / "reference.docx"
    document.save(path)

    _, doubt = read_limitations(Ref(path, "zh"))
    assert not any("边框" in note for note in doubt), doubt


def test_header_drawing_is_reported(tmp_path):
    """页眉里有图片（学校 logo、横线）：读不出来，必须进需确认清单。"""
    document = Document()
    document.add_paragraph("正文。")
    document.sections[0].header.paragraphs[0].text = "页眉文字"
    source = tmp_path / "reference.docx"
    document.save(source)

    target = tmp_path / "with-drawing.docx"
    _rewrite(source=source, target=target, part="word/header1.xml",
             transform=lambda text: text.replace(
                 "</w:p>", '<w:r><w:drawing/></w:r></w:p>', 1))
    lines, doubt = read_decor(Ref(target, "zh"))

    assert any("页眉文字" in line for line in lines), lines
    assert any("图片或图形" in note for note in doubt), doubt


def _rewrite(*, source: Path, target: Path, part: str, transform) -> None:
    shutil.copy(source, target)
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        payload = {name: archive.read(name) for name in names}
    payload[part] = transform(payload[part].decode("utf-8")).encode("utf-8")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, payload[name])


def test_border_declared_on_base_style_is_reported(tmp_path):
    """属性写在基部样式上、派生样式在用 —— 这是最常见的形态，不能因为"派生样式自己没写"就漏。"""
    document = Document()
    styles = document.styles.element
    base = styles.makeelement(q("style"), {})
    base.set(q("type"), "paragraph")
    base.set(q("styleId"), "BaseBox")
    base.append(base.makeelement(q("name"), {q("val"): "Base Box"}))
    properties = base.makeelement(q("pPr"), {})
    borders = properties.makeelement(q("pBdr"), {})
    borders.append(borders.makeelement(q("top"), {q("val"): "single", q("sz"): "8"}))
    properties.append(borders)
    base.append(properties)
    styles.append(base)

    derived = styles.makeelement(q("style"), {})
    derived.set(q("type"), "paragraph")
    derived.set(q("styleId"), "QuoteBox")
    derived.append(derived.makeelement(q("name"), {q("val"): "Quote Box"}))
    derived.append(derived.makeelement(q("basedOn"), {q("val"): "BaseBox"}))
    styles.append(derived)

    paragraph = document.add_paragraph("引用块")
    paragraph._p.get_or_add_pPr().append(
        paragraph._p.pPr.makeelement(q("pStyle"), {q("val"): "QuoteBox"}))
    path = tmp_path / "reference.docx"
    document.save(path)

    _, doubt = read_limitations(Ref(path, "zh"))
    assert any("上边框" in note and "Base Box" in note for note in doubt), doubt


def test_header_style_limitation_is_reported(tmp_path):
    """页眉样式只在 header1.xml 里被引用：只看正文 XML 的话它永远进不了清单。"""
    document = Document()
    header = document.sections[0].header
    paragraph = header.paragraphs[0]
    paragraph.text = "页眉文字"
    style = paragraph.style
    properties = style.element.find(q("pPr"))
    if properties is None:
        properties = style.element.makeelement(q("pPr"), {})
        style.element.append(properties)
    properties.append(properties.makeelement(q("shd"), {q("fill"): "D9D9D9"}))
    document.add_paragraph("正文。")
    path = tmp_path / "reference.docx"
    document.save(path)

    _, doubt = read_limitations(Ref(path, "zh"))
    assert any("底纹" in note for note in doubt), doubt


def test_table_header_shading_is_reported(tmp_path):
    """表头灰底写在 tblStylePr[firstRow]/tcPr/shd 里 —— Word 就是这么存「表头灰底」的。"""
    document = Document()
    styles = document.styles.element
    table_style = styles.makeelement(q("style"), {})
    table_style.set(q("type"), "table")
    table_style.set(q("styleId"), "GreyHeader")
    table_style.append(table_style.makeelement(q("name"), {q("val"): "Grey Header"}))
    conditional = table_style.makeelement(q("tblStylePr"), {q("type"): "firstRow"})
    cells = conditional.makeelement(q("tcPr"), {})
    cells.append(cells.makeelement(q("shd"), {q("fill"): "D9D9D9"}))
    conditional.append(cells)
    table_style.append(conditional)
    styles.append(table_style)

    table = document.add_table(rows=2, cols=2)
    table._tbl.tblPr.append(
        table._tbl.tblPr.makeelement(q("tblStyle"), {q("val"): "GreyHeader"}))
    path = tmp_path / "reference.docx"
    document.save(path)

    _, doubt = read_limitations(Ref(path, "zh"))
    assert any("底纹" in note and "Grey Header" in note for note in doubt), doubt


def test_negative_decor_distance_is_reported_not_written(tmp_path):
    """页眉距边界是负值：格式文件表达不了，不能写进草稿把它变成一份生成器拒收的文件。"""
    from md_to_word.template.extractor import read_page

    document = Document()
    document.add_paragraph("正文。")
    path = tmp_path / "reference.docx"
    document.save(path)

    tweaked = tmp_path / "negative.docx"
    _rewrite(source=path, target=tweaked, part="word/document.xml",
             transform=lambda text: text.replace(
                 'w:header="851"', 'w:header="-720"').replace(
                 'w:header="720"', 'w:header="-720"'))
    lines, doubt = read_page(Ref(tweaked, "zh"))
    if any("页眉距边界" in line for line in lines):
        raise AssertionError(f"负值不该写成格式行：{lines}")
    assert any("负值" in note for note in doubt), doubt


def test_decor_note_follows_language(tmp_path):
    """英文模式下提示不能是中英混排。"""
    document = Document()
    document.add_paragraph("正文。")
    document.sections[0].header.paragraphs[0].text = "header text"
    source = tmp_path / "reference.docx"
    document.save(source)
    target = tmp_path / "with-drawing.docx"
    _rewrite(source=source, target=target, part="word/header1.xml",
             transform=lambda text: text.replace(
                 "</w:p>", '<w:r><w:drawing/></w:r></w:p>', 1))

    _, doubt = read_decor(Ref(target, "en"))
    drawing_notes = [note for note in doubt if "picture" in note]
    assert drawing_notes and "the default header" in drawing_notes[0], doubt
    assert "页眉" not in drawing_notes[0], drawing_notes


def test_a_style_whose_id_is_machine_generated_is_still_found(tmp_path):
    """`styleId` 是 Word 自动生成的那种（`a17` 之类）、名字才是 `Table Caption`，也要认出来。

    以前 `by_id` 只按 `styleId` 建索引，这条样式会**静默消失**：草稿里既没有「表题」那一行，
    也不在任何一份"需确认"清单里。Word 里改过样式的模板经常长这样——样式 ID 一旦被 Word
    重排过就不再等于名字。
    """
    from md_to_word.template.builder import build_template
    from md_to_word.template.extractor import _build_draft

    preset = (Path(__file__).resolve().parents[1] / "presets" / "zh-academic.txt").read_text(
        encoding="utf-8")
    source = tmp_path / "generated.docx"
    build_template(preset, source)

    tweaked = tmp_path / "weird.docx"
    _rewrite(
        source=source, target=tweaked, part="word/styles.xml",
        transform=lambda text: text.replace(
            'w:styleId="TableCaption"', 'w:styleId="a17"'),
    )

    text, _, _ = _build_draft(Ref(tweaked, "zh"), "zh")

    assert any(line.startswith("表题：") for line in text.splitlines()), text


def test_a_mapped_style_is_not_reported_as_unmapped(tmp_path):
    """认出来的样式不能再报"没映射到本工具词汇"——草稿不能自己打自己的脸。"""
    from md_to_word.template.builder import build_template
    from md_to_word.template.extractor import _build_draft

    preset = (Path(__file__).resolve().parents[1] / "presets" / "zh-academic.txt").read_text(
        encoding="utf-8")
    source = tmp_path / "generated.docx"
    build_template(preset, source)

    # 样式 ID 改成机器生成的样子，同时让正文真的引用它（"用到了"才进得了那条清单）
    tweaked = tmp_path / "weird.docx"
    _rewrite(
        source=source, target=tweaked, part="word/styles.xml",
        transform=lambda text: text.replace(
            'w:styleId="TableCaption"', 'w:styleId="a17"'),
    )
    referenced = tmp_path / "used.docx"
    _rewrite(
        source=tweaked, target=referenced, part="word/document.xml",
        transform=lambda text: text.replace(
            "</w:body>",
            '<w:p><w:pPr><w:pStyle w:val="a17"/></w:pPr><w:r><w:t>表 1</w:t></w:r></w:p></w:body>'),
    )

    text, _, _ = _build_draft(Ref(referenced, "zh"), "zh")

    unmapped = [line for line in text.splitlines() if "没映射到本工具词汇" in line]
    assert not unmapped, unmapped
