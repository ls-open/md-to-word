"""导前预检的门禁回归。

这四道门禁在 V2 重写校验器时丢过一次（结构样式缺失、图片宽度超过版心、
`\\tag{}` 公式编号、custom-style 与模板比对），而当时两条流水线各走一半，
问题在 CLI 路径上无人察觉。下面每条用例锁住一道门禁的判定，防止再丢。

比对的是「拦不拦」，不是文案——文案可以改，判定必须只有一套。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from md_to_word.template.builder import build_template
from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "presets" / "zh-academic.txt"
FIGURE = REPO_ROOT / "demo" / "01_chinese_thesis" / "figures" / "qa_pipeline.png"

BASE_YAML = '---\n---\n\n# 一 引言\n\n正文一段。\n'
CROSSREF_YAML = (
    '---\ncrossref:\n  eq-prefix: "式"\n  fig-prefix: "图"\n'
    '  tbl-prefix: "表"\n---\n\n# 一 引言\n'
)


def _requirements_without(*rows: str) -> str:
    """内置预设删掉指定前缀的行——模拟「要求文件漏声明某结构」。"""
    kept = [
        line
        for line in PRESET.read_text(encoding="utf-8").splitlines()
        if not any(line.startswith(row) for row in rows)
    ]
    return "\n".join(kept) + "\n"


# name -> (稿件正文, 要删掉的要求文件行；None=不给要求文件, 期望是否拦)
CASES = {
    "clean": (BASE_YAML, None, False),
    "table_without_style_rows": (
        BASE_YAML
        + "\n%% 表题 表 1 测试\n| 甲 | 乙 |\n|:--|:--|\n| 1 | 2 |\n",
        ("表格：", "表头："),
        True,
    ),
    "latex_tag": (BASE_YAML + "\n$$E = mc^2 \\tag{1}$$\n", None, True),
    # 图片宽度超版心只提醒：图还在页内，看得见，不阻断
    "image_wider_than_text_block": (
        BASE_YAML + "\n![](figures/qa_pipeline.png){width=30cm}\n",
        (),  # 版心要从要求文件算，故必须给文件，但不删任何行
        False,
    ),
    "citation_without_bibliography": (BASE_YAML + "\n见 [@smith2024]。\n", None, True),
    "crossref_without_bibliography": (
        CROSSREF_YAML + "\n$$E = mc^2$$ {#eq-a}\n\n见 @eq-a。\n",
        None,
        False,
    ),
    "undefined_crossref": (CROSSREF_YAML + "\n见 @eq-missing。\n", None, True),
    # 引擎只认正文的样式行：YAML 里的摘要/关键词没有任何排版位置，静默丢一段摘要
    # 比报错难查得多，所以这里拦下来并说清该写成什么样。
    "yaml_abstract": (
        '---\nabstract: |\n  摘要正文。\n---\n\n# 一 引言\n\n正文。\n',
        None,
        True,
    ),
    "yaml_keywords": ('---\nkeywords: [甲, 乙]\n---\n\n正文。\n', None, True),
    # 标题、作者、日期同理：位置由作者定（可能排在封面之后），YAML 没有位置
    "yaml_title": ('---\ntitle: "题目"\n---\n\n正文。\n', None, True),
    "yaml_author": ('---\nauthor: [张三]\n---\n\n正文。\n', None, True),
    # 正文写法才是正典
    "title_as_style_line": ('%% 文档标题 题目\n\n# 一 引言\n\n正文。\n', None, False),
    # 题注写在 `![…]` 里：引擎不把它当题注排，等于丢内容
    "caption_in_alt": (
        BASE_YAML + "\n![图 1-1 框架图](figures/qa_pipeline.png){width=10cm}\n",
        None,
        True,
    ),
    # 正规写法：独立题注段 + 只留无障碍文字的图片行
    "caption_as_style_line": (
        BASE_YAML + "\n%% 图片题注 图 1-1 框架图\n\n![](figures/qa_pipeline.png){width=10cm}\n",
        None,
        False,
    ),
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_preflight_verdict(name: str, tmp_path: Path) -> None:
    body, dropped_rows, expected_blocked = CASES[name]
    (tmp_path / "manuscript.md").write_text(body, encoding="utf-8")
    (tmp_path / "figures").mkdir(exist_ok=True)
    if FIGURE.exists():
        shutil.copy(FIGURE, tmp_path / "figures" / "qa_pipeline.png")

    requirements = None
    if dropped_rows is not None:
        requirements = tmp_path / "requirements.txt"
        requirements.write_text(_requirements_without(*dropped_rows), encoding="utf-8")

    report = validate_manuscript(tmp_path / "manuscript.md", spec_path=requirements)

    assert report.valid is not expected_blocked, (
        f"{name}: 期望{'拦' if expected_blocked else '放'}，实际"
        f"{'拦' if not report.valid else '放'}：{report.errors}"
    )


def test_custom_style_must_exist_in_template(tmp_path: Path) -> None:
    """模板里没有该样式，段落只能退回普通段落，格式不生效；不认识的样式名预检直接拦。"""
    template = tmp_path / "template.docx"
    build_template(PRESET.read_text(encoding="utf-8"), template)

    manuscript = tmp_path / "manuscript.md"
    manuscript.write_text(
        BASE_YAML + "\n%% 不存在的样式 正文。\n", encoding="utf-8"
    )

    report = validate_manuscript(manuscript, template_docx=template)
    assert not report.valid
    assert any("不存在的样式" in error for error in report.errors)


def test_visible_issues_warn_instead_of_blocking(tmp_path: Path) -> None:
    """看得见的问题只提醒：多一页、宽度被钳、题注离得远，作者可以自行收尾。"""
    (tmp_path / "figures").mkdir()
    if FIGURE.exists():
        shutil.copy(FIGURE, tmp_path / "figures" / "qa_pipeline.png")
    manuscript = tmp_path / "m.md"
    manuscript.write_text(
        '---\n---\n\n# 一 引言\n\n### 跳级标题\n\n正文。\n\n'
        "%% 表题 表 1 测试\n\n正文隔开了题注和表格。\n\n| 甲 | 乙 |\n|:--|:--|\n| 1 | 2 |\n",
        encoding="utf-8",
    )
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(PRESET.read_text(encoding="utf-8"), encoding="utf-8")

    report = validate_manuscript(manuscript, spec_path=requirements)
    assert report.valid, f"看得见的问题不该阻断：{report.errors}"
    assert any("标题" in w for w in report.warnings)
    assert any("题注" in w for w in report.warnings)


def test_bibliography_without_title_warns(tmp_path: Path) -> None:
    """文献列表是引擎生成的，抬头得稿子自己写——没写只提醒，内容没丢。"""
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{smith2024,\n  author={Smith, J.},\n  title={T},\n  year={2024},\n  journal={J}\n}\n",
        encoding="utf-8",
    )
    manuscript = tmp_path / "m.md"
    manuscript.write_text(
        '---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n# 一 引言\n\n见 [@smith2024]。\n',
        encoding="utf-8",
    )

    report = validate_manuscript(manuscript)
    assert report.valid, report.errors
    assert any("文献区标题" in w for w in report.warnings), report.warnings


def test_reference_section_title_in_yaml_only_warns(tmp_path: Path) -> None:
    """写 YAML 的 reference-section-title 不拦：抬头缺失只影响观感，内容没丢。"""
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{smith2024,\n  author={Smith, J.},\n  title={T},\n  year={2024},\n  journal={J}\n}\n",
        encoding="utf-8",
    )
    manuscript = tmp_path / "m.md"
    manuscript.write_text(
        '---\nbibliography: refs.bib\ncsl: apa.csl\n'
        'reference-section-title: 参考文献\n---\n\n# 一 引言\n\n见 [@smith2024]。\n',
        encoding="utf-8",
    )

    report = validate_manuscript(manuscript)
    assert report.valid, report.errors
    assert any("reference-section-title" in w for w in report.warnings), report.warnings
