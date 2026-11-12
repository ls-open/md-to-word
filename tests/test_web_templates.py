"""官网展示页（`docs/`）必须与真实预设、稿件契约、以及现场导出的成品对得上。

页面是静态的：没有后端，只有 `web/build.py` 生成出来的 html 与四份成品。于是它是预设的
**第四份真相源**（CLI / MCP / 包里 / 展示页）——新增 `zh-tw-academic` 那一轮，CLI 与 MCP
都跟上了，官网样张页还停在三个模板，没人报错，因为没有任何东西在检查它。

这里锁五件事：
1. 每个模板引用的预设真的存在（preset 名字写错时，导出会退回默认预设悄悄跑通）；
2. 样张字段齐全（页面靠它们渲染，缺一个就是空白块）；
3. 样张拼出来的 Markdown 自己能过预检——样张是给人抄的，它自己不合规就没有说服力；
4. 页面里的卡片与下载链接，和模板清单一一对应；
5. **提交进仓库的 .docx 与现场重新导出的逐字节一致**——页面上那四份「真导出」经得起复核，
   一旦谁改了样张正文却忘了重建产物，这条就红。

第 5 条只重导出 docx（不渲染 PDF），所以在没有 Word 的机器上也能跑。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from md_to_word.config import resolve_preset_path
from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS = REPO_ROOT / "docs"
ASSETS = DOCS / "assets"
FIELD_KEYS = (
    "doc_title",
    "abstract",
    "keywords",
    "intro_heading",
    "intro_body",
    "equation",
    "table_caption",
    "table_content",
    "table_note",
    "conclusion_heading",
    "conclusion_body",
    "references",
)


def _load(module: str):
    """`web/` 不是一个包，两个模块都是裸脚本，按路径塞进 sys.path 再导入。"""
    for path in (REPO_ROOT / "web", REPO_ROOT / "src"):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return importlib.import_module(module)


@pytest.fixture(scope="module")
def catalog():
    return _load("catalog")


@pytest.fixture(scope="module")
def build():
    return _load("build")


def test_every_template_points_at_a_real_preset(catalog) -> None:
    """模板引用的预设必须真的存在——preset 名字写错时，导出会退回默认预设悄悄跑通。"""
    for tpl_id, tpl in catalog.TEMPLATES.items():
        assert tpl["id"] == tpl_id, f"{tpl_id} 的 id 字段与键不一致"
        path = Path(tpl["preset_file"])
        assert path.is_file(), f"{tpl_id} 指向的预设文件不存在：{path}"
        resolved = resolve_preset_path(tpl["preset_name"])
        assert resolved is not None and resolved.is_file(), (
            f"{tpl_id} 的 preset_name「{tpl['preset_name']}」不是内置预设"
        )


def test_template_metadata_is_complete(catalog) -> None:
    """页面直接读这些字段，缺一个就是空白块。"""
    for tpl_id, tpl in catalog.TEMPLATES.items():
        for key in ("name", "badge", "desc", "header_content"):
            assert str(tpl.get(key, "")).strip(), f"{tpl_id} 缺少 {key}"
        for key in FIELD_KEYS:
            assert str(tpl.get(key, "")).strip(), f"{tpl_id} 缺少样张字段 {key}"
        assert tpl.get("specs_zh"), f"{tpl_id} 缺少 specs_zh"


@pytest.mark.parametrize("tpl_id", ["zh-journal", "zh-tw-journal", "zh-report", "en-paper"])
def test_sample_manuscript_passes_preflight(catalog, tpl_id: str, tmp_path: Path) -> None:
    """样张是给人抄的：它拼出来的 Markdown + format 必须自己先过预检。"""
    tpl = catalog.TEMPLATES[tpl_id]
    markdown = catalog._assemble_markdown(
        template_id=tpl_id,
        doc_title=tpl["doc_title"],
        abstract=tpl["abstract"],
        keywords=tpl["keywords"],
        intro_heading=tpl["intro_heading"],
        intro_body=tpl["intro_body"],
        equation=tpl["equation"],
        table_caption=tpl["table_caption"],
        table_content=tpl["table_content"],
        table_note=tpl["table_note"],
        conclusion_heading=tpl["conclusion_heading"],
        conclusion_body=tpl["conclusion_body"],
        references=tpl["references"],
    )
    format_text = catalog._build_dynamic_format(tpl_id, tpl["header_content"])

    manuscript = tmp_path / "m.md"
    manuscript.write_text(markdown, encoding="utf-8")
    requirements = tmp_path / "format.txt"
    requirements.write_text(format_text, encoding="utf-8")

    report = validate_manuscript(
        manuscript,
        spec_path=requirements,
        lang="en" if tpl_id == "en-paper" else "zh",
    )
    assert report.valid, f"{tpl_id} 的样张过不了预检：{report.errors}"


def test_page_offers_every_template(catalog) -> None:
    """页面是生成物，少一套不会报错——只是那套模板在页面上根本不存在。"""
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    for tpl_id in catalog.TEMPLATES:
        for needle in (
            f'id="tab-{tpl_id}"',
            f'id="panel-{tpl_id}"',
            f'href="assets/{tpl_id}.docx"',
            f'href="assets/{tpl_id}.pdf"',
        ):
            assert needle in html, f"页面缺少 {needle}"


@pytest.mark.parametrize("tpl_id", ["zh-journal", "zh-tw-journal", "zh-report", "en-paper"])
def test_committed_docx_matches_a_fresh_export(catalog, build, tpl_id: str, tmp_path: Path) -> None:
    """页面上写着「这不是效果图」——那就得能复核。

    提交进仓库的那份 .docx，必须与 `web/build.py` 现场导出的一字不差。样张正文改了却没
    重跑 build.py，这条会红；这也顺带证明了导出本身逐字节可复现。
    """
    committed = ASSETS / f"{tpl_id}.docx"
    assert committed.is_file(), f"缺少 {committed.relative_to(REPO_ROOT)}：先跑 python3 web/build.py"

    tpl = catalog.TEMPLATES[tpl_id]
    out = tmp_path / f"{tpl_id}.docx"
    ok, _ = build._export(
        build._assemble(tpl),
        catalog._build_dynamic_format(tpl_id, tpl["header_content"]),
        out,
        pdf=False,
    )
    assert ok, f"{tpl_id} 重导出失败"
    assert out.read_bytes() == committed.read_bytes(), (
        f"{tpl_id}.docx 与现场导出的不一致：样张改过了？跑 python3 web/build.py 重建"
    )


def test_page_is_up_to_date(catalog, build) -> None:
    """页面是生成的：改了 `catalog.py` 或 `page.html` 而没重建，用户看到的就是旧页面。"""
    templates = catalog.TEMPLATES
    built = {t for t in templates if (ASSETS / f"{t}.docx").exists()}
    expected = build._render_page(templates, built)
    actual = (DOCS / "index.html").read_text(encoding="utf-8")
    assert actual == expected, "docs/index.html 落后了：跑 python3 web/build.py 重建"
