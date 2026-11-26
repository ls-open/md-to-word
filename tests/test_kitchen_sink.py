"""同一份“全家桶”稿件跑过所有富结构预设。

单点测试各自证明公式、表格、列表、图、脚注、文献能写；这里把它们放进一份稿子，
验证组合起来不会互相踩样式、不会让后检误报，也不会把某一块静默丢掉。
`zh-gb9704` 是纯公文预设，不带摘要/参考文献样式，不在这组里。
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest
from docx import Document

from md_to_word.pipeline import ExportOptions, run_export_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
# APA 学生版按规范不放目录；其余富结构预设都声明了目录样式。
RICH_PRESETS = (
    ("en-apa-student", False),
    ("en-nature", True),
    ("zh-academic", True),
    ("zh-report", True),
    ("zh-tw-academic", True),
)

BIB = """
@article{alpha,
  author = {Alpha, Ann},
  title = {Alpha One},
  journal = {Journal of Tests},
  year = {2020},
  pages = {1--9}
}
"""

MANUSCRIPT = """---
bibliography: refs.bib
---

%% 文档标题 综合测试文档

%% 摘要标题 摘要

%% 摘要 这是一段摘要，包含**加粗**、*斜体*、`代码`、行内公式 $x^2$ 与引用 @alpha。

%% 关键词 排版；测试；公式

{{< toc >}}

# 1 引言

正文引用 @alpha，脚注[^n]，公式见 @eq-a，表格见下。

$$E = mc^2$$ {#eq-a}

%% 表题 **表 1** 数据表

| 名称 | 数值 |
|:--|--:|
| 甲 | 42 |

%% 表注 注：示例。

![](pic.png){width=6cm}

%% 图片题注 图 1 示意图

- 第一项
  - 第二层
- 尾项

> 引用块里的文字。

```text
code line
```

# 参考文献 {{.unlisted}}

[^n]: 脚注里的说明。
"""


@pytest.mark.parametrize(("preset", "with_toc"), RICH_PRESETS)
def test_a_manuscript_with_every_structure_exports(
    preset: str, with_toc: bool, tmp_path: Path,
) -> None:
    shutil.copyfile(REPO_ROOT / "demo" / "00_quickstart" / "page-1.png", tmp_path / "pic.png")
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    manuscript = tmp_path / "m.md"
    body = MANUSCRIPT if with_toc else MANUSCRIPT.replace("{{< toc >}}\n\n", "")
    manuscript.write_text(body, encoding="utf-8")
    out = tmp_path / "out.docx"

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=out, preset=preset,
    ))
    assert result.returncode == 0, (preset, result.errors)

    document = Document(out)
    assert len(document.tables) == 1
    assert len(document.inline_shapes) == 1
    assert any(p.style.name == "Bibliography" for p in document.paragraphs)

    xml = zipfile.ZipFile(out).read("word/document.xml").decode("utf-8")
    assert "<m:oMath" in xml, "公式没有落成原生 OMML"
    assert "<w:drawing" in xml, "图片没有落成 inline drawing"
    if with_toc:
        assert "<w:fldChar" in xml and "TOC" in xml, "目录域缺失"
    assert "<w:footnoteReference" in xml, "脚注引用缺失"

    text = "\n".join(p.text for p in document.paragraphs)
    assert "综合测试文档" in text
    assert "引用块里的文字" in text
    assert "第二层" in text
