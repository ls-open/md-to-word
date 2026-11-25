"""分节：标记给**下面那一节**命名，外观来自格式文件的节角色。

OOXML 里没写引用等于「沿用上一节」。所以每一节都要带显式引用，「这一节不要页眉」
必须挂一个**空部件**——删引用会让中间节继承前一节的页眉。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from lxml import etree

from md_to_word.model.reader import MarkdownError, read_markdown
from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.spec.parser import parse_format
from md_to_word.template.builder import build_template
from md_to_word.writer import write_docx

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")
# 预置自带的角色块去掉，测试里自己声明，才能给不同角色不同的页眉
BASE = PRESET.split("\n分节：封面")[0]

ROLES = """
分节：封面
封面页眉内容：封面专用
封面页脚内容：无

分节：前置
前置页码：小写罗马 起始1
前置页眉内容：无
前置页脚内容：{页码}

分节：正文
正文页码：阿拉伯 起始1

分节：附录
附录页码：阿拉伯
附录页眉内容：附录专用
附录页脚内容：{页码}
"""

DECOR = (
    "页眉内容：某某大学学位论文 {样式标题:Heading 1}\n"
    "页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符\n"
)

_FORMAT = BASE + ROLES + DECOR


def _docx(tmp_path: Path, manuscript: str, fmt: str = _FORMAT) -> Path:
    spec = parse_format(fmt)
    template = tmp_path / "t.docx"
    build_template(fmt, template)
    out = tmp_path / "o.docx"
    write_docx(
        read_markdown(manuscript), template, out, section_roles=spec.section_roles,
    )
    return out


def _sections(docx: Path) -> list[str]:
    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    return re.findall(r"<w:sectPr>.*?</w:sectPr>", xml, re.S)


def _decor_texts(docx: Path, kind: str = "header") -> list[list[tuple[str, str]]]:
    """每一节每一类页眉/页脚的文字：[(类型, 文字)]，按 document.xml 里的节顺序。"""
    z = zipfile.ZipFile(docx)
    doc = z.read("word/document.xml").decode("utf-8")
    rels = etree.fromstring(z.read("word/_rels/document.xml.rels"))
    targets = {}
    for rel in rels:
        targets[rel.get("Id")] = rel.get("Target")
    tag = "headerReference" if kind == "header" else "footerReference"
    out: list[list[tuple[str, str]]] = []
    for sect in re.findall(r"<w:sectPr>.*?</w:sectPr>", doc, re.S):
        refs = []
        for ref in re.findall(rf"<w:{tag}[^>]*/>", sect):
            which = re.search(r'w:type="(\w+)"', ref)
            rid = re.search(r'r:id="(rId\d+)"', ref)
            part = "word/" + targets[rid.group(1)].lstrip("/")
            blob = z.read(part).decode("utf-8")
            text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", blob))
            refs.append((which.group(1) if which else "default", text))
        out.append(refs)
    return out


def test_every_section_keeps_explicit_references(tmp_path: Path) -> None:
    """普通分节每节都带显式引用，不靠「沿用上一节」。"""
    sections = _sections(_docx(tmp_path, "# 一\n\n正文。\n\n{{< section >}}\n\n# 二\n\n正文。\n"))

    assert len(sections) == 2
    assert all("headerReference" in s and "footerReference" in s for s in sections)


def test_a_role_can_have_an_empty_header_without_inheriting(tmp_path: Path) -> None:
    """封面/前置不要页眉：挂空部件，中间节也不会继承前一节。"""
    out = _docx(
        tmp_path,
        "{{< section 封面 >}}\n\n%% 文档标题 封面标题\n\n"
        "{{< section 前置 >}}\n\n%% 摘要标题 摘要\n\n{{< section 正文 >}}\n\n# 一\n\n正文。\n",
    )
    headers = _decor_texts(out)
    footers = _decor_texts(out, "footer")

    assert [text for _, text in headers[0]] == ["封面专用"], "封面用角色自己的页眉"
    assert [text for _, text in headers[1]] == [""], "前置要的是空页眉，不是上一节的"
    assert "某某大学" in headers[2][0][1], "正文没声明页眉，沿用格式文件的全局页眉"
    assert [text for _, text in footers[0]] == [""], "封面页脚显式为空"
    assert headers[0][0][1] != headers[1][0][1], "两个节不能引用同一个页眉部件"


def test_page_number_format_and_start_follow_the_role(tmp_path: Path) -> None:
    sections = _sections(
        _docx(
            tmp_path,
            "{{< section 前置 >}}\n\n%% 摘要标题 摘要\n\n{{< section 正文 >}}\n\n# 一\n\n正文。\n",
        )
    )

    assert '<w:pgNumType w:fmt="lowerRoman" w:start="1"/>' in sections[0]
    assert '<w:pgNumType w:fmt="decimal" w:start="1"/>' in sections[-1]


def test_a_role_without_start_continues_numbering(tmp_path: Path) -> None:
    sections = _sections(
        _docx(
            tmp_path,
            "{{< section 正文 >}}\n\n# 一\n\n正文。\n\n{{< section 附录 >}}\n\n# 附录 A\n\n正文。\n",
        )
    )

    assert 'w:start' not in sections[-1], "附录声明了格式但没声明起始：接着正文编"


def test_trailing_section_does_not_restart_page_numbers(tmp_path: Path) -> None:
    sections = _sections(
        _docx(tmp_path, "# 一\n\n正文。\n\n{{< section >}}\n\n# 二\n\n正文。\n")
    )

    assert 'w:start' not in sections[-1], "普通分节接着上一节编"


def test_body_starts_at_one_after_roman_front_matter(tmp_path: Path) -> None:
    sections = _sections(
        _docx(
            tmp_path,
            "{{< section 前置 >}}\n\n{{< toc 2 >}}\n\n{{< section 正文 >}}\n\n# 一\n\n正文。\n",
        )
    )

    assert "lowerRoman" in sections[0]
    assert 'w:start="1"' in sections[-1], "正文角色声明了起始 1"


def test_cover_counts_but_shows_no_number(tmp_path: Path) -> None:
    out = _docx(
        tmp_path,
        "{{< section 封面 >}}\n\n%% 文档标题 封面\n\n{{< section 正文 >}}\n\n# 一\n\n正文。\n",
    )
    footers = _decor_texts(out, "footer")

    assert [text for _, text in footers[0]] == [""], "封面不显示页码"
    assert 'w:start="1"' in _sections(out)[-1], "封面不显示页码，正文仍从 1 起"


def test_single_section_keeps_the_start_from_the_format_file(tmp_path: Path) -> None:
    sections = _sections(_docx(tmp_path, "# 一\n\n正文。\n"))

    assert len(sections) == 1 and 'w:start="1"' in sections[0]


def test_a_leading_marker_names_the_first_section_without_an_extra_break(tmp_path: Path) -> None:
    """文档开头的标记只命名第一节，不落 sectPr——否则封面会多出一页空白。"""
    sections = _sections(_docx(tmp_path, "{{< section 前置 >}}\n\n# 一\n\n正文。\n"))

    assert len(sections) == 1
    assert "lowerRoman" in sections[0]


def test_the_old_parameter_syntax_is_a_plain_syntax_error(tmp_path: Path) -> None:
    fmt = tmp_path / "f.txt"
    fmt.write_text(_FORMAT, encoding="utf-8")
    md = tmp_path / "m.md"
    md.write_text("# 封面\n\n{{< section 页码=小写罗马 起始=1 >}}\n\n# 一\n\n正文。\n", encoding="utf-8")

    result = run_export_pipeline(ExportOptions(
        input_path=md, output_path=tmp_path / "m.docx", format_path=fmt,
    ))

    assert not result.ok
    assert any("只接受一个节名" in e for e in result.errors), result.errors
    assert any(d.code == "gate.section.argument" for d in result.diagnostics), result.diagnostics


def test_unknown_role_lists_the_declared_ones(tmp_path: Path) -> None:
    fmt = tmp_path / "f.txt"
    fmt.write_text(_FORMAT, encoding="utf-8")
    md = tmp_path / "m.md"
    md.write_text("# 一\n\n{{< section 附录二 >}}\n\n正文。\n", encoding="utf-8")

    result = run_export_pipeline(ExportOptions(
        input_path=md, output_path=tmp_path / "m.docx", format_path=fmt,
    ))

    assert not result.ok
    message = "\n".join(result.errors)
    assert "附录二" in message and "封面" in message and "正文" in message, message
    assert any(d.code == "gate.section.role_unknown" for d in result.diagnostics)


def test_reader_rejects_parameters_itself(tmp_path: Path) -> None:
    """读取器是公开入口：不能等预检才拦。"""
    try:
        read_markdown("{{< section 页眉=无 >}}\n")
    except MarkdownError as exc:
        assert exc.code == "gate.section.argument"
    else:  # pragma: no cover
        raise AssertionError("应当拒绝带参数的分节标记")
