"""章级节段标题（如参考文献标题、摘要标题）的显式页眉/目录升级机制。

规则摘要：
1. 不再隐式把 `References Title` 强升为 Heading 1：只有声明了 `加入页眉`（`join-header`）的节段样式，
   才在模板 `/customXml/mdw_meta.xml` 记录并由写出器以 `_adopt_style` 映射为 Heading 1（喂给 STYLEREF）；
2. 写了 `不入页眉`（`no-header`）的样式保持自身独立样式（如 `ReferencesTitle`），不进入 Heading 1；
3. 换结构不能带进 Heading 1 多余属性：若 `Heading 1` 有段前分页/颜色/下边框，而被采用样式没有，直接格式必须显式压掉；
4. 格式文件写了 `{样式标题:Heading 1}` 却省略 `加入页眉`/`不入页眉`，模板生成阶段必须报错拦下；
5. `不入目录` + `加入页眉` 在 Word 原生 `TOC \\o \\u` 下互斥，解析期即拒绝。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

from md_to_word.model.reader import read_markdown
from md_to_word.spec.parser import parse_format
from md_to_word.template.builder import build_template
from md_to_word.template.generator import TemplateError, read_header_styles_meta
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

MANUSCRIPT = "%% 文档标题 测试\n\n# 第一章\n\n正文。\n\n%% 参考文献标题 参 考 文 献\n"


def _replace_style_line(spec_text: str, prefix: str, new_line: str) -> str:
    return "\n".join(
        new_line if line.startswith(prefix) else line
        for line in spec_text.splitlines()
    ) + "\n"


def _references_paragraph(tmp_path: Path, spec_text: str) -> str:
    """导出后取文献标题那一段的 XML。"""
    template = tmp_path / "t.docx"
    build_template(spec_text, template)
    out = write_docx(read_markdown(MANUSCRIPT), template, tmp_path / "o.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    paragraphs = re.findall(r"<w:p>.*?</w:p>", xml, re.S)
    return next(p for p in paragraphs if "参 考 文 献" in p)


def test_explicit_join_header_promotes_and_writes_meta(tmp_path: Path) -> None:
    """显式声明 `加入目录 加入页眉`：段落走 Heading 1 供 STYLEREF 抓取，并在 meta 记录。"""
    paragraph = _references_paragraph(tmp_path, PRESET)
    assert '<w:pStyle w:val="Heading1"/>' in paragraph

    meta = read_header_styles_meta(tmp_path / "o.docx")
    assert meta == {"References Title"}


def test_no_header_stays_on_its_own_style(tmp_path: Path) -> None:
    """声明 `加入目录 不入页眉`：段落保持 `ReferencesTitle` 本身，meta 为空集。"""
    spec = _replace_style_line(
        PRESET,
        "参考文献标题：",
        "参考文献标题：黑体/Times New Roman 三号 加粗 不倾斜 居中 行距1.5倍 "
        "段前18磅 段后12磅 首行缩进0字符 与下段同页 加入目录 不入页眉",
    )
    paragraph = _references_paragraph(tmp_path, spec)
    assert '<w:pStyle w:val="ReferencesTitle"/>' in paragraph
    assert '<w:pStyle w:val="Heading1"/>' not in paragraph

    meta = read_header_styles_meta(tmp_path / "o.docx")
    assert meta == set()


def test_declared_look_is_preserved_and_heading1_extras_suppressed(tmp_path: Path) -> None:
    """Heading 1 带颜色/段前分页/段中不分页/下边框而参考文献标题没有时，必须按参考文献自身声明压掉。"""
    spec = _replace_style_line(
        PRESET,
        "一级标题：",
        "一级标题：黑体/Times New Roman 三号 加粗 不倾斜 左对齐 颜色#1F4E79 行距1.5倍 "
        "段前18磅 段后12磅 首行缩进0字符 段前分页 段中不分页 下边框单线 边框粗1磅",
    )
    spec = _replace_style_line(
        spec,
        "参考文献标题：",
        "参考文献标题：宋体/Times New Roman 四号 不加粗 倾斜 居中 行距1.0倍 "
        "段前24磅 段后6磅 首行缩进0字符 加入目录 加入页眉",
    )
    paragraph = _references_paragraph(tmp_path, spec)

    assert '<w:pStyle w:val="Heading1"/>' in paragraph
    assert '<w:jc w:val="center"/>' in paragraph
    assert 'w:sz w:val="28"' in paragraph  # 四号 = 14pt = 28 半磅
    assert 'w:eastAsia="宋体"' in paragraph
    # Heading 1 的段前分页/与下段同页/段中不分页/下边框/颜色都应被直接格式显式清零，不外泄到参考文献标题
    assert '<w:pageBreakBefore w:val="0"/>' in paragraph
    assert '<w:keepNext w:val="0"/>' in paragraph
    assert '<w:keepLines w:val="0"/>' in paragraph
    assert '<w:bottom w:val="none"/>' in paragraph
    assert '<w:color w:val="000000"/>' in paragraph
    assert "1F4E79" not in paragraph


def test_declared_look_sz_exact_check(tmp_path: Path) -> None:
    """验证参考文献标题自身的三号字体/居中/加粗/与下段同页完整抄成直接格式。"""
    paragraph = _references_paragraph(tmp_path, PRESET)
    assert '<w:jc w:val="center"/>' in paragraph
    assert 'w:sz w:val="32"' in paragraph  # 三号 = 16pt = 32 半磅
    assert 'w:eastAsia="黑体"' in paragraph
    assert '<w:keepNext/>' in paragraph
    assert "outlineLvl" not in paragraph, "加入目录时交由 Heading 1 大纲级别 0 收录"


def test_styleref_requires_join_header_or_no_header_linkage(tmp_path: Path) -> None:
    """格式文件用了 `{样式标题:Heading 1}` 却省略页眉收录声明时，必须报错阻断并指出样式名。"""
    spec = (
        _replace_style_line(
            PRESET,
            "参考文献标题：",
            "参考文献标题：黑体/Times New Roman 三号 加粗 不倾斜 居中 行距1.5倍 "
            "段前18磅 段后12磅 首行缩进0字符 与下段同页 加入目录",
        )
        + "\n页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符\n"
        + "页眉内容：{样式标题:Heading 1}\n"
    )
    with pytest.raises(TemplateError) as exc_info:
        build_template(spec, tmp_path / "fail.docx")
    assert "References Title" in str(exc_info.value)
    assert "加入页眉" in str(exc_info.value)


def test_no_toc_and_join_header_is_rejected_at_parse() -> None:
    """Option 1 硬约束：`不入目录` 与 `加入页眉` 不可同写（中英文皆然）。"""
    zh_bad = _replace_style_line(
        PRESET,
        "摘要标题：",
        "摘要标题：黑体/Times New Roman 四号 加粗 不倾斜 居中 行距1.5倍 段前6磅 段后6磅 首行缩进0字符 不入目录 加入页眉",
    )
    with pytest.raises(ValueError, match="不入目录.*加入页眉"):
        parse_format(zh_bad)

    en_preset = (REPO_ROOT / "presets" / "en-nature.txt").read_text(encoding="utf-8")
    en_bad = _replace_style_line(
        en_preset,
        "Abstract Title:",
        "Abstract Title: Times New Roman 12pt bold not-italic left line-spacing 1.5 "
        "space-before 6pt space-after 6pt indent 0 no-toc join-header",
    )
    with pytest.raises(ValueError, match="no-toc.*join-header"):
        parse_format(en_bad)
