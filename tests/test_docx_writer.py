"""模型 → OOXML 的写出器。

验收方式是**双后端对拍**：同一份稿件分别走 Pandoc（现有通道）与自研写出器，比对
样式序列与全文文本。样式序列一致，说明「哪一段用什么样式」这层判断没有跑偏；
文本一致，说明内容一个字没丢。

能力边界单独测：没实现的结构必须抛 `UnsupportedFeature`，不许静默降级成普通段落。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from md_to_word.model.reader import read_markdown
from md_to_word.template.builder import build_template
from md_to_word.writer import UnsupportedFeature, write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"
DEMO = REPO_ROOT / "demo" / "00_quickstart"


def _facts(path: Path) -> tuple[list[str], str]:
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    styles = re.findall(r'<w:pStyle w:val="([^"]+)"', xml)
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    return styles, text


@pytest.fixture()
def template(tmp_path: Path) -> Path:
    out = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), out)
    return out


def test_writes_title_block_and_blocks(template: Path, tmp_path: Path) -> None:
    model = read_markdown(
        '---\ntitle: "题目"\nauthor: [张三]\n---\n\n# 一 引言\n\n正文。\n\n## 1.1 小节\n\n更多正文。\n'
    )
    out = write_docx(model, template, tmp_path / "a.docx")
    styles, text = _facts(out)
    assert styles[:2] == ["Title", "Author"]
    assert "Heading1" in styles
    assert "First Paragraph" in text or "FirstParagraph" in styles


def test_first_paragraph_after_heading_uses_first_paragraph_style(template: Path, tmp_path: Path) -> None:
    model = read_markdown("# 一 引言\n\n第一段。\n\n第二段。\n")
    styles, _ = _facts(write_docx(model, template, tmp_path / "b.docx"))
    assert styles == ["Heading1", "FirstParagraph", "BodyText"]


def test_table_header_is_marked_and_cells_use_compact(template: Path, tmp_path: Path) -> None:
    model = read_markdown("| 甲 | 乙 |\n|:--|--:|\n| 1 | 2 |\n")
    out = write_docx(model, template, tmp_path / "c.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert "<w:tbl>" in xml
    assert "tblHeader" in xml, "表头行要标记跨页重复"
    assert xml.count('w:val="Compact"') == 4  # 表头两格 + 数据两格


def test_code_block_keeps_line_breaks(template: Path, tmp_path: Path) -> None:
    model = read_markdown("```\nline1\nline2\n```\n")
    out = write_docx(model, template, tmp_path / "d.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert "line1" in xml and "line2" in xml


@pytest.mark.parametrize(
    ("source", "fragment"),
    [
        ("见 [@smith2024]。\n", "文献"),
    ],
)
def test_unsupported_features_fail_loudly(source: str, fragment: str, template: Path, tmp_path: Path) -> None:
    model = read_markdown(source)
    with pytest.raises(UnsupportedFeature, match=fragment):
        write_docx(model, template, tmp_path / "x.docx")


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
def test_matches_pandoc_output_on_quickstart(template: Path, tmp_path: Path) -> None:
    """双后端对拍：样式序列与全文文本必须一致。"""
    for name in ("hello.md", "requirements.txt"):
        shutil.copy(DEMO / name, tmp_path / name)

    ours = write_docx(
        read_markdown((DEMO / "hello.md").read_text(encoding="utf-8")),
        template,
        tmp_path / "ours.docx",
    )

    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "export.sh"), "hello.md", "-o", "theirs.docx"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )

    our_styles, our_text = _facts(ours)
    their_styles, their_text = _facts(tmp_path / "theirs.docx")
    assert our_styles == their_styles
    assert our_text == their_text


def test_lists_use_real_numbering(template: Path, tmp_path: Path) -> None:
    """编号必须是域而不是字面量，否则 Word 里按退格改不了级别、增删条目不会重编号。"""
    model = read_markdown("- 甲\n- 乙\n\n1. 一\n2. 二\n")
    out = write_docx(model, template, tmp_path / "list.docx")
    package = zipfile.ZipFile(out)
    document = package.read("word/document.xml").decode("utf-8")
    numbering = package.read("word/numbering.xml").decode("utf-8")

    assert document.count("<w:numPr>") == 4
    assert "<w:abstractNum " in numbering and "<w:num " in numbering
    assert 'w:numFmt w:val="bullet"' in numbering
    assert 'w:numFmt w:val="decimal"' in numbering


def test_ordered_list_start_override(template: Path, tmp_path: Path) -> None:
    model = read_markdown("3. 第三\n4. 第四\n")
    out = write_docx(model, template, tmp_path / "start.docx")
    numbering = zipfile.ZipFile(out).read("word/numbering.xml").decode("utf-8")
    assert 'w:startOverride w:val="3"' in numbering


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
def test_matches_pandoc_output_on_lists(template: Path, tmp_path: Path) -> None:
    source = '---\ntitle: "列表测试"\n---\n\n# 一 章节\n\n正文。\n\n- 甲\n- 乙\n\n1. 一\n2. 二\n'
    (tmp_path / "m.md").write_text(source, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(PRESET.read_text(encoding="utf-8"), encoding="utf-8")

    ours = write_docx(read_markdown(source), template, tmp_path / "ours.docx")
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "export.sh"), "m.md", "-o", "theirs.docx"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    our_styles, our_text = _facts(ours)
    their_styles, their_text = _facts(tmp_path / "theirs.docx")
    assert our_styles == their_styles
    assert our_text == their_text, "列表的文本与编号级联应与 Pandoc 一致"


def test_footnotes_are_written_as_a_real_part(template: Path, tmp_path: Path) -> None:
    """脚注不是正文里的上标文字，而是独立的 footnotes.xml 部件。"""
    model = read_markdown("# 一 章节\n\n正文有脚注[^1]。\n\n[^1]: 注释文字。\n")
    out = write_docx(model, template, tmp_path / "fn.docx")
    package = zipfile.ZipFile(out)
    assert "word/footnotes.xml" in package.namelist()

    footnotes = package.read("word/footnotes.xml").decode("utf-8")
    assert 'w:type="separator"' in footnotes, "缺分隔符，脚注区的横线会显示异常"
    assert 'w:type="continuationSeparator"' in footnotes
    assert "注释文字" in footnotes

    document = package.read("word/document.xml").decode("utf-8")
    assert 'w:id="1"' in document and "footnoteReference" in document

    # 能重新打开，说明关系与内容类型都写对了
    from docx import Document as open_docx
    open_docx(str(out))


def test_toc_field_and_section_break(template: Path, tmp_path: Path) -> None:
    """目录是 Word 域，分节是挂在 pPr 里的 sectPr——都不是普通段落。"""
    model = read_markdown(
        "{{< toc 2 >}}\n\n{{< section 页码=小写罗马 起始=1 >}}\n\n# 一 引言\n\n正文。\n"
    )
    out = write_docx(model, template, tmp_path / "sec.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")

    assert "instrText" in xml and "TOC" in xml, "目录必须是域，否则页码不会更新"
    assert xml.count("<w:sectPr") == 2, "分节段落一个 + 文末一个"
    assert '<w:pgNumType w:fmt="lowerRoman" w:start="1"/>' in xml


@pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")
def test_matches_pandoc_output_on_toc_and_section(template: Path, tmp_path: Path) -> None:
    source = (
        '---\ntitle: "结构测试"\n---\n\n%% 目录标题 目录\n\n{{< toc 2 >}}\n\n'
        "{{< section 页码=小写罗马 起始=1 >}}\n\n# 一 引言\n\n正文。\n"
    )
    (tmp_path / "m.md").write_text(source, encoding="utf-8")
    (tmp_path / "requirements.txt").write_text(PRESET.read_text(encoding="utf-8"), encoding="utf-8")

    ours = write_docx(read_markdown(source), template, tmp_path / "ours.docx")
    subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "export.sh"), "m.md", "-o", "theirs.docx"],
        cwd=tmp_path, capture_output=True, text=True, check=True,
    )
    our_styles, our_text = _facts(ours)
    their_styles, their_text = _facts(tmp_path / "theirs.docx")
    assert our_styles == their_styles
    assert our_text.replace("（打开文档后目录会自动生成）", "") == their_text.replace("（打开文档后目录会自动生成）", "")


def test_equations_become_omml_with_numbers(template: Path, tmp_path: Path) -> None:
    """公式要写成原生 OMML（Word 里可编辑），编号按出现顺序，交叉引用解析成「式N」。"""
    model = read_markdown(
        '---\ntitle: "t"\ncrossref:\n  eq-prefix: "式"\n---\n\n# 一 引言\n\n'
        "行内 $x+y$。\n\n$$E = mc^2$$ {#eq-a}\n\n由 @eq-a 可知。\n"
    )
    out = write_docx(model, template, tmp_path / "eq.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")

    assert xml.count("<m:oMath") == 2, "行内一条 + 显示一条"
    assert "(1)" in xml, "带标签的公式要编号"
    assert "式1" in xml, "交叉引用要解析成前缀 + 编号"


def test_equation_numbering_follows_chapters(template: Path, tmp_path: Path) -> None:
    model = read_markdown(
        '---\ntitle: "t"\ncrossref:\n  chapters: true\n---\n\n'
        "# 第一章\n\n$$a$$ {#eq-a}\n\n# 第二章\n\n$$b$$ {#eq-b}\n"
    )
    model.meta.chapters = True
    out = write_docx(model, template, tmp_path / "ch.docx")
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert "(1.1)" in xml and "(2.1)" in xml


def test_unsupported_mathml_fails_loudly() -> None:
    """转换器遇到没覆盖的 MathML 结构要当场报错，不能悄悄变成空白或纯文本。

    注意：`latex2mathml` 本身对不认识的命令很宽容（原样转成文本），所以这条边界只能
    在 MathML 这一层测——那也正是我们自己的代码所在的位置。
    """
    from md_to_word.transform.mathml2omml import UnsupportedMath, mathml_to_omml

    unsupported = (
        '<math xmlns="http://www.w3.org/1998/Math/MathML">'
        "<menclose><mi>x</mi></menclose></math>"
    )
    with pytest.raises(UnsupportedMath, match="menclose"):
        mathml_to_omml(unsupported)


def test_native_pipeline_needs_no_quarto(tmp_path: Path, monkeypatch) -> None:
    """自研后端不碰 Quarto：把 quarto 从 PATH 上抹掉，导出照样成功。

    这是「内化」的判据——不是"我们也能渲染"，而是"没有那个外部二进制也能渲染"。
    """
    from unittest.mock import patch

    from md_to_word.pipeline import ExportOptions, run_export_pipeline

    for name in ("hello.md", "requirements.txt"):
        shutil.copy(DEMO / name, tmp_path / name)
    if (DEMO / "figures").is_dir():
        shutil.copytree(DEMO / "figures", tmp_path / "figures")

    with patch("md_to_word.renderer.quarto.shutil.which", return_value=None):
        result = run_export_pipeline(
            ExportOptions(
                input_path=tmp_path / "hello.md",
                output_path=tmp_path / "out.docx",
                writer="native",
            )
        )

    assert result.returncode == 0, result.errors
    assert (tmp_path / "out.docx").exists()
    styles, text = _facts(tmp_path / "out.docx")
    assert "Title" in styles and text


def test_citations_render_and_bibliography_is_appended(template: Path, tmp_path: Path) -> None:
    """引文由 CSL 引擎渲染，文末列表自动生成——作者一个字都不用写。"""
    from md_to_word.transform.citations import CitationEngine

    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{smith2024,\n  author = {Smith, John},\n  title = {A Study},\n"
        "  journal = {Nature},\n  year = {2024},\n}\n",
        encoding="utf-8",
    )
    csl = REPO_ROOT / "src" / "md_to_word" / "resources" / "csl" / "chinese-gb7714-2015-numeric.csl"
    engine = CitationEngine(bib.read_text(encoding="utf-8"), csl)

    model = read_markdown('---\ntitle: "t"\n---\n\n# 一 引言\n\n见 [@smith2024]。\n')
    out = write_docx(model, template, tmp_path / "cite.docx", citations=engine)
    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))

    assert "[1]" in text, "正文里的引用要渲染成编号"
    assert "SMITH" in text.upper(), "文末要自动生成文献列表"
    assert 'w:val="Bibliography"' in xml, "文献条目要用 Bibliography 样式"


def test_bibtex_to_csl_json_maps_core_fields() -> None:
    from md_to_word.transform.bibtex import parse_bibtex

    entries = parse_bibtex(
        "@article{key1,\n  author = {Zhang, San and Li, Si},\n  title = {T},\n"
        "  journal = {J},\n  year = {2020},\n  pages = {1--9},\n}\n"
    )
    assert entries[0]["type"] == "article-journal"
    assert entries[0]["container-title"] == "J"
    assert entries[0]["issued"] == {"date-parts": [[2020]]}
    assert [a.get("family") for a in entries[0]["author"]] == ["Zhang", "Li"]


# ── 前置区与题注：存量稿件的写法必须照样出字 ────────────────────────────

def test_yaml_abstract_and_keywords_are_rendered(template: Path, tmp_path: Path) -> None:
    model = read_markdown(
        '---\ntitle: "题目"\nabstract: |\n  第一段摘要。\n\n  第二段摘要。\n'
        'keywords: [智能座舱, 满意度]\n---\n\n# 一 引言\n\n正文。\n'
    )
    out = write_docx(model, template, tmp_path / "a.docx")
    styles, text = _facts(out)
    assert "摘要" in text
    assert styles.count("Abstract") == 2
    assert "Keywords" in styles
    assert "智能座舱；满意度" in text


def test_body_abstract_wins_over_yaml(template: Path, tmp_path: Path) -> None:
    """两处都写了摘要时只排正文那份，否则同一段摘要会出现两次。"""
    model = read_markdown(
        '---\ntitle: "题目"\nabstract: YAML 里的摘要\n---\n\n'
        "%% 摘要标题 摘要\n\n%% 摘要 正文里的摘要\n"
    )
    out = write_docx(model, template, tmp_path / "a.docx")
    _, text = _facts(out)
    assert text.count("正文里的摘要") == 1
    assert "YAML 里的摘要" not in text


def test_figure_alt_text_becomes_caption(template: Path, tmp_path: Path) -> None:
    """`![图1-1 框架图](x.png)` 是 Pandoc 时代的题注写法，丢掉就是丢内容。"""
    png = tmp_path / "x.png"
    shutil.copy(REPO_ROOT / "demo" / "01_chinese_thesis" / "figures" / "qa_pipeline.png", png)
    model = read_markdown(f"![图1-1 框架图]({png}){{width=10cm}}\n")
    out = write_docx(model, template, tmp_path / "a.docx")
    styles, text = _facts(out)
    assert "ImageCaption" in styles or "Image Caption" in styles
    assert "图1-1 框架图" in text


def test_bibliography_gets_title(template: Path, tmp_path: Path) -> None:
    """文献区没有标题在正式稿件里不合格，而标题是读者一眼能看见的。"""
    bib = tmp_path / "r.bib"
    bib.write_text(
        "@article{smith2024,\n  author={Smith, J.},\n  title={T},\n  year={2024},\n  journal={J}\n}\n",
        encoding="utf-8",
    )
    from md_to_word.transform.citations import CitationEngine

    from md_to_word.config import get_csl_dir

    engine = CitationEngine(
        bib.read_text(encoding="utf-8"), get_csl_dir() / "chinese-gb7714-2015-numeric.csl"
    )
    model = read_markdown('---\ntitle: "题"\nreference-section-title: 参考文献\n---\n\n见 [@smith2024]。\n')
    out = write_docx(model, template, tmp_path / "a.docx", citations=engine)
    styles, text = _facts(out)
    assert "ReferencesTitle" in styles or "References Title" in styles
    assert "参考文献" in text
