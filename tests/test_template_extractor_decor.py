"""反推参考 .docx 的页眉页脚：按引用解析，不按部件名猜。

多节模板里每节可能各有自己的页眉（学位论文常见：每章一节、页眉写死章名）。
`header1/2/3.xml` 只是打包顺序，把它们当成默认/偶数页/首页就会张冠李戴。
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION

from md_to_word.template.extractor import Ref, read_decor


def _multisection(tmp_path: Path, headers: list[str]) -> Path:
    """每节一个独立页眉部件（不链接上一节），内容各不相同的参考文件。"""
    doc = Document()
    for i, header in enumerate(headers, 1):
        section = doc.sections[-1]
        section.header.is_linked_to_previous = False
        section.header.paragraphs[0].text = header
        doc.add_paragraph(f"正文{i}")
        if i < len(headers):
            doc.add_section(WD_SECTION.NEW_PAGE)
    path = tmp_path / "ref.docx"
    doc.save(path)
    return path


def test_reads_the_body_section_header_not_the_part_number(tmp_path: Path) -> None:
    """三个章名各在自己的节里：只取正文节那一个，不是「默认/偶数页/首页」。"""
    ref = Ref(_multisection(tmp_path, ["第一章 绪论", "第六章 总结", "第七章 展望"]))
    lines, doubt = read_decor(ref)

    assert lines == ["页眉内容：第七章 展望"]
    assert any("各节" in note for note in doubt), "各节不一样要说出来，别让人以为读全了"


def test_single_section_header_is_read_as_the_default(tmp_path: Path) -> None:
    """单节文档照旧：那一份就是默认页眉。"""
    ref = Ref(_multisection(tmp_path, ["某某大学学位论文"]))
    lines, doubt = read_decor(ref)

    assert lines == ["页眉内容：某某大学学位论文"]
    assert doubt == []


def test_even_page_header_keeps_its_slot(tmp_path: Path) -> None:
    """奇偶页不同时，各自的引用各自归位。"""
    path = _multisection(tmp_path, ["奇数页页眉"])
    doc = Document(path)
    section = doc.sections[-1]
    section.even_page_header.is_linked_to_previous = False
    section.even_page_header.paragraphs[0].text = "偶数页页眉"
    doc.save(path)

    lines, _ = read_decor(Ref(path))
    assert "页眉内容：奇数页页眉" in lines
    assert "偶数页页眉内容：偶数页页眉" in lines


def test_a_cached_field_result_is_not_read_as_content(tmp_path: Path) -> None:
    """域里那段文字是上次算出来的缓存结果，不是内容。

    Word 存盘时会把 PAGE 的上一次结果留在 `fldChar begin → separate → end` 中间。照抄进
    草稿就成了「页脚内容：{页码} 18」——照它生成的模板，页脚上永远多印一个 18。
    实测的一份英文论文模板就是这种。
    """
    import zipfile

    document = Document()
    document.add_paragraph("正文。")
    document.sections[0].footer.paragraphs[0].text = ""
    source = tmp_path / "ref.docx"
    document.save(source)

    with zipfile.ZipFile(source) as z:
        names = z.namelist()
        payload = {n: z.read(n) for n in names}
    footer = payload["word/footer1.xml"].decode("utf-8")
    field = (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        '<w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        '<w:r><w:t>18</w:t></w:r>'
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )
    footer = footer.replace("</w:p>", field + "</w:p>", 1)
    payload["word/footer1.xml"] = footer.encode("utf-8")
    patched = tmp_path / "cached.docx"
    with zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, payload[n])

    lines, _ = read_decor(Ref(patched, "zh"))

    footer_line = [line for line in lines if line.startswith("页脚内容")]
    assert footer_line and "{页码}" in footer_line[0], lines
    assert "18" not in footer_line[0], footer_line
