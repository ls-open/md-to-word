"""官网样张页（`web/app.py`）的模板目录，必须与真实预设和稿件契约对得上。

`web/` 不在 pip 包里、也没有进过测试，于是它成了预设的**第四份清单**：新增
`zh-tw-academic` 那一轮，CLI 与 MCP 的元数据都跟上了，官网样张页还停在三个模板——
没人报错，因为没有任何东西在检查它。

这里锁三件事：每个模板引用的预设解析得到；样张字段齐全；拼出来的 Markdown 能过预检。
最后一条是关键——样张是给人抄的，它自己都不合规就没有说服力。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from md_to_word.config import resolve_preset_path
from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
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


def _web_app():
    """`web/catalog.py` 只有纯函数（模板目录与稿件拼装），不拉 fastapi 进来。"""
    if str(REPO_ROOT / "web") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "web"))
    return importlib.import_module("catalog")


@pytest.fixture(scope="module")
def webapp():
    return _web_app()


def test_every_template_points_at_a_real_preset(webapp) -> None:
    """模板引用的预设必须真的存在——preset 名字写错时，导出会退回 zh-academic 悄悄跑通。"""
    for tpl_id, tpl in webapp.TEMPLATES.items():
        assert tpl["id"] == tpl_id, f"{tpl_id} 的 id 字段与键不一致"
        path = Path(tpl["preset_file"])
        assert path.is_file(), f"{tpl_id} 指向的预设文件不存在：{path}"
        resolved = resolve_preset_path(tpl["preset_name"])
        assert resolved is not None and resolved.is_file(), (
            f"{tpl_id} 的 preset_name「{tpl['preset_name']}」不是内置预设"
        )


def test_template_metadata_is_complete(webapp) -> None:
    """前端的卡片与表单直接读这些字段，缺一个就是空白框。"""
    for tpl_id, tpl in webapp.TEMPLATES.items():
        for key in ("name", "name_en", "badge", "badge_en", "desc", "desc_en", "header_content"):
            assert str(tpl.get(key, "")).strip(), f"{tpl_id} 缺少 {key}"
        for key in FIELD_KEYS:
            assert str(tpl.get(key, "")).strip(), f"{tpl_id} 缺少样张字段 {key}"
        for lang_key in ("specs_zh", "specs_en"):
            assert tpl.get(lang_key), f"{tpl_id} 缺少 {lang_key}"


@pytest.mark.parametrize(
    "tpl_id",
    ["zh-journal", "zh-tw-journal", "zh-report", "en-paper"],
)
def test_sample_manuscript_passes_preflight(webapp, tpl_id: str, tmp_path: Path) -> None:
    """样张是给人抄的：它拼出来的 Markdown + format 必须自己先过预检。"""
    tpl = webapp.TEMPLATES[tpl_id]
    markdown = webapp._assemble_markdown(
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
    format_text = webapp._build_dynamic_format(tpl_id, tpl["header_content"])

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


def test_frontend_has_a_card_for_every_template(webapp) -> None:
    """首页的卡片是静态 HTML，文字由 `/api/templates` 按 id 回填。

    少一张卡片不会报错——那张模板在页面上就是不存在的，而 API 里明明有它。
    """
    html = (REPO_ROOT / "web" / "static" / "index.html").read_text(encoding="utf-8")
    for tpl_id in webapp.TEMPLATES:
        for prefix in ("card-", "cardTitle-", "cardBadge-", "cardDesc-"):
            assert f'id="{prefix}{tpl_id}"' in html, f"首页缺少 {prefix}{tpl_id}"
