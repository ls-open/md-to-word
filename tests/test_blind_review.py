"""盲审清理：底模带出的身份信息不能跟着成品走。

`--base-template` 灌入的是用户提供的 .docx，其 `docProps/` 会原样保留：作者、单位、
学号（自定义属性）、封面缩略图、批注作者。这里锁住三件事：能识别、能清理、不清理时
至少提醒；同时清理只碰文件属性，不动正文。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.utils.metadata import (
    _neutralize_authors,
    identifying_metadata,
    scrub_metadata,
)

REPO = Path(__file__).resolve().parents[1]
HELLO = REPO / "demo" / "00_quickstart" / "hello.md"

def _base_with_identity(tmp_path: Path) -> Path:
    """两节底模：封面一节 + 待替换正文一节，docProps 里塞满身份信息。"""
    doc = Document()
    doc.add_paragraph("封面：某某大学 张三")
    doc.add_section(WD_SECTION.NEW_PAGE)
    doc.add_paragraph("底模正文占位")
    doc.core_properties.author = "张三"
    doc.core_properties.last_modified_by = "李四"
    doc.core_properties.title = "张三的毕业论文"
    doc.core_properties.comments = "内部批注，含姓名"
    path = tmp_path / "base.docx"
    doc.save(path)

    with zipfile.ZipFile(path) as zin:
        items = [(info, zin.read(info.filename)) for info in zin.infolist()]
    with zipfile.ZipFile(path, "w") as zout:
        for info, data in items:
            if info.filename == "docProps/app.xml":
                text = data.decode("utf-8")
                if "<Company/>" in text:
                    text = text.replace("<Company/>", "<Company>某某大学</Company>")
                elif "<Company>" not in text:
                    text = text.replace("</Properties>", "<Company>某某大学</Company></Properties>")
                data = text.encode("utf-8")
            elif info.filename == "[Content_Types].xml":
                text = data.decode("utf-8")
                if "custom-properties" not in text:
                    text = text.replace(
                        "</Types>",
                        '<Override PartName="/docProps/custom.xml" ContentType='
                        '"application/vnd.openxmlformats-officedocument.custom-properties+xml"/>'
                        "</Types>",
                    )
                data = text.encode("utf-8")
            elif info.filename == "_rels/.rels":
                text = data.decode("utf-8")
                text = text.replace(
                    "</Relationships>",
                    '<Relationship Id="rIdCustom" Type="http://schemas.openxmlformats.org/'
                    'officeDocument/2006/relationships/custom-properties" '
                    'Target="docProps/custom.xml"/></Relationships>',
                )
                data = text.encode("utf-8")
            zout.writestr(info, data)
        zout.writestr(
            "docProps/custom.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
            'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
            '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="学号">'
            "<vt:lpwstr>2023001</vt:lpwstr></property></Properties>",
        )
    return path


def _codes(result) -> list[str]:
    return [d.code for d in result.diagnostics]


def test_identity_is_detected_in_a_base_template(tmp_path: Path) -> None:
    base = _base_with_identity(tmp_path)

    codes = {finding.code for finding in identifying_metadata(base)}

    assert {"creator", "lastModifiedBy", "title", "company", "custom", "thumbnail"} <= codes


def test_base_identity_is_warned_about_without_blind_review(tmp_path: Path) -> None:
    base = _base_with_identity(tmp_path)

    result = run_export_pipeline(ExportOptions(
        input_path=HELLO,
        output_path=tmp_path / "out.docx",
        preset="zh-academic",
        base_template=base,
        cover_sections=1,
    ))

    assert result.ok, result.errors
    assert "pipeline.base_metadata" in _codes(result)
    assert identifying_metadata(tmp_path / "out.docx"), "未开盲审时身份确实会带出，提醒才有意义"


def test_blind_review_strips_base_metadata_and_keeps_content(tmp_path: Path) -> None:
    base = _base_with_identity(tmp_path)
    out = tmp_path / "out.docx"

    result = run_export_pipeline(ExportOptions(
        input_path=HELLO,
        output_path=out,
        preset="zh-academic",
        base_template=base,
        cover_sections=1,
        blind_review=True,
    ))

    assert result.ok, result.errors
    assert identifying_metadata(out) == []
    with zipfile.ZipFile(out) as archive:
        names = set(archive.namelist())
        core = archive.read("docProps/core.xml").decode("utf-8")
        app = archive.read("docProps/app.xml").decode("utf-8")
    assert "docProps/custom.xml" not in names
    assert "docProps/thumbnail.jpeg" not in names
    assert "张三" not in core and "李四" not in core
    assert "某某大学" not in app
    # 正文仍在：清理只碰属性
    xml = ""
    with zipfile.ZipFile(out) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert "封面：某某大学 张三" in xml
    Document(out)  # 仍是可打开的合法 docx
    assert any("清理文档属性" in message for message in result.messages)


def test_blind_review_works_without_a_base_template(tmp_path: Path) -> None:
    out = tmp_path / "out.docx"

    result = run_export_pipeline(ExportOptions(
        input_path=HELLO,
        output_path=out,
        preset="zh-academic",
        blind_review=True,
    ))

    assert result.ok, result.errors
    assert identifying_metadata(out) == []
    # 普通导出本来就没有作者/单位，但来源描述要一起清掉
    with zipfile.ZipFile(out) as archive:
        assert "md-to-word" not in archive.read("docProps/core.xml").decode("utf-8")


def test_scrub_is_atomic_and_neutralizes_revision_authors(tmp_path: Path) -> None:
    base = _base_with_identity(tmp_path)
    before = base.read_bytes()

    scrub_metadata(base)

    assert identifying_metadata(base) == []
    assert base.read_bytes() != before
    # 坏文件不留下半成品：临时文件必须是同目录的隐藏文件，且被原子替换掉
    assert not list(tmp_path.glob(".*blind-review*"))

    xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:ins w:id="1" w:author="张三" w:date="2026-01-01T00:00:00Z"/>'
        '<w:del w:id="2" w:author="李四" w:initials="LS"/></w:document>'
    ).encode("utf-8")
    cleaned = _neutralize_authors(xml)
    assert b"\xe5\xbc\xa0\xe4\xb8\x89" not in cleaned
    assert b"Author" in cleaned and b"initials=\"A\"" in cleaned
