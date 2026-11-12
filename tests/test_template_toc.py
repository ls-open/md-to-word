"""目录条目样式必须是 Word 的**内置**样式。

Word 的内置目录样式是 `styleId="TOC1"`、`name="toc 1"`、**不带** `w:customStyle`。
用 python-docx 新建同名样式会写成自建样式，Word 更新目录域时按内置定义重建，
字体/字号/加粗全部丢失——作者会以为"设置没生效"。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.template.builder import build_template

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"


def _styles_xml(tmp_path: Path) -> str:
    out = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), out)
    with zipfile.ZipFile(out) as archive:
        return archive.read("word/styles.xml").decode("utf-8")


@pytest.mark.parametrize("level", [1, 2, 3])
def test_toc_styles_are_builtin(level: int, tmp_path: Path) -> None:
    xml = _styles_xml(tmp_path)
    match = re.search(rf'<w:style [^>]*w:styleId="TOC{level}"[^>]*>.*?</w:style>', xml, re.S)
    assert match, f"模板里没有 TOC{level} 样式"
    style = match.group(0)
    assert 'w:customStyle' not in style, "带 customStyle 会被 Word 当成自建样式并重置"
    assert f'<w:name w:val="toc {level}"/>' in style, "内置样式名是小写 toc N"


def test_fourth_level_is_opt_in_and_contiguous(tmp_path: Path) -> None:
    """四级目录不是默认：不写就没有；写了四级就必须连着写到三级。"""
    from md_to_word.template.generator import TemplateError

    preset = PRESET.read_text(encoding="utf-8")
    assert "TOC 4" not in _styles_xml(tmp_path), "预设只到三级，模板里不该凭空多出四级"

    four = preset + "目录四级：宋体/Times New Roman 小四 不加粗 不倾斜 左对齐 行距1.5倍 段前0磅 段后0磅 首行缩进0字符\n"
    out = tmp_path / "four.docx"
    build_template(four, out)
    with zipfile.ZipFile(out) as archive:
        xml = archive.read("word/styles.xml").decode("utf-8")
    match = re.search(r'<w:style [^>]*w:styleId="TOC4"[^>]*>.*?</w:style>', xml, re.S)
    assert match and 'w:customStyle' not in match.group(0)

    # 只写三级以上的部分（跳过二级）应报错，而不是静默退回 Word 默认
    gap = "\n".join(
        line for line in preset.split("\n") if not line.startswith("目录二级：")
    )
    with pytest.raises(TemplateError):
        build_template(gap, tmp_path / "gap.docx")


def test_toc_field_covers_every_declared_level(tmp_path: Path) -> None:
    """声明到四级，`{{< toc >}}` 就要收到四级——声明与收录不能各说各话。"""
    from md_to_word.model.reader import read_markdown
    from md_to_word.writer.docx_writer import write_docx

    req = PRESET.read_text(encoding="utf-8") + (
        "目录四级：宋体/Times New Roman 小四 不加粗 不倾斜 左对齐 行距1.5倍 "
        "段前0磅 段后0磅 首行缩进0字符\n"
    )
    tpl = tmp_path / "t4.docx"
    build_template(req, tpl)

    model = read_markdown('---\ntitle: "t"\n---\n\n{{< toc >}}\n\n# 一 引言\n\n正文。\n')
    out = write_docx(model, tpl, tmp_path / "o.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert 'TOC \\o "1-4"' in xml


def test_toc_heading_stays_builtin(tmp_path: Path) -> None:
    xml = _styles_xml(tmp_path)
    match = re.search(r'<w:style [^>]*w:styleId="TOCHeading"[^>]*>.*?</w:style>', xml, re.S)
    assert match and "<w:name w:val=\"TOC Heading\"/>" in match.group(0)


def test_audit_rejects_body_level_outline_on_join_toc_style(tmp_path: Path) -> None:
    """`加入目录` / `不入目录` 声明后，对账必须核查产物 `outlineLvl` 与之匹配。"""
    from lxml import etree

    from md_to_word.audit.inspector import audit
    from md_to_word.model.reader import read_markdown
    from md_to_word.writer.docx_writer import write_docx

    fmt_lines = [
        line.replace("不入目录", "加入目录") if line.startswith("摘要标题：") else line
        for line in PRESET.read_text(encoding="utf-8").splitlines()
    ]
    fmt_text = "\n".join(fmt_lines) + "\n"
    fmt_path = tmp_path / "format.txt"
    fmt_path.write_text(fmt_text, encoding="utf-8")
    tpl_path = tmp_path / "tpl.docx"
    build_template(fmt_text, tpl_path)
    out_path = write_docx(
        read_markdown("---\n---\n\n%% 摘要标题 摘 要\n\n正文。\n"),
        tpl_path,
        tmp_path / "out.docx",
    )
    assert audit(out_path, fmt_path, lang="zh") == []

    # 1) 将要求「加入目录」的 AbstractTitle 篡改为 outlineLvl=9（正文级别）
    bad_path = tmp_path / "bad_ol9.docx"
    ns_w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    w = f"{{{ns_w}}}"
    with zipfile.ZipFile(out_path, "r") as zin, zipfile.ZipFile(bad_path, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                root = etree.fromstring(data)
                for st in root.findall(f"{w}style"):
                    if st.get(f"{w}styleId") == "AbstractTitle":
                        ol = st.find(f"{w}pPr/{w}outlineLvl")
                        assert ol is not None
                        ol.set(f"{w}val", "9")
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            zout.writestr(item, data)

    problems = audit(bad_path, fmt_path, lang="zh")
    assert any(cat == "目录" and "outlineLvl=9" in msg for cat, msg in problems), problems

    # 2) 默认预设要求 AbstractTitle 为「不入目录」(outlineLvl=9)，若产物落成 outlineLvl=0 也应报错
    no_toc_fmt = tmp_path / "no_toc_format.txt"
    no_toc_fmt.write_text(PRESET.read_text(encoding="utf-8"), encoding="utf-8")
    problems_no_toc = audit(out_path, no_toc_fmt, lang="zh")
    assert any(cat == "目录" and "outlineLvl=0" in msg for cat, msg in problems_no_toc), problems_no_toc
