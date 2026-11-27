"""每一种内置 CSL 都要能走完整的导出链，而不只是引擎层能渲染。

引擎层矩阵（`test_citation_matrix.py`）证明样式能产出文本；这里再往下一层：
引文出现在正文、列表、表格、引用块与脚注里，参考文献表要真的落进 .docx，
且原稿里的 `@key` 不能被当字面文字印出来。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest
from docx import Document

from md_to_word.audit.postflight import docx_text
from md_to_word.config import get_csl_dir
from md_to_word.pipeline import ExportOptions, run_export_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt"
CSL_DIR = get_csl_dir()
STYLES = sorted(path.name for path in CSL_DIR.glob("*.csl"))
assert STYLES, "内置 CSL 目录为空：整组导出矩阵测试会静默消失"

BIB = r"""
@article{alpha,
  author = {Alpha, Ann and Beta, Bob},
  title = {Alpha One},
  journal = {Journal of Tests},
  year = {2020},
  volume = {1},
  pages = {1--10}
}

@article{beta,
  author = {Gamma, Gail},
  title = {Beta Two},
  journal = {Journal of Tests},
  year = {2021},
  volume = {2},
  pages = {11--20}
}
"""

MANUSCRIPT = """---
bibliography: refs.bib
csl: "{csl}"
---

# Introduction

A paragraph cites @alpha, then @alpha and @beta together.

- A list item cites @beta.
- A plain list item stays put.

| Column | Reference |
|:--|:--|
| First | @alpha |
| Second | @beta |

> A quotation cites @alpha.

A footnote carries another citation.[^note]

[^note]: The note cites @beta.

# 参考文献 {{.unlisted}}
"""


@pytest.mark.parametrize("style", STYLES)
def test_every_csl_survives_all_citation_contexts(style: str, tmp_path: Path) -> None:
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    md = tmp_path / "paper.md"
    md.write_text(MANUSCRIPT.format(csl=CSL_DIR / style), encoding="utf-8")
    out = tmp_path / "paper.docx"

    result = run_export_pipeline(ExportOptions(
        input_path=md,
        output_path=out,
        format_path=PRESET,
        audit=False,
    ))

    assert result.returncode == 0, (style, result.errors)
    document = Document(out)
    bibliography = [p for p in document.paragraphs if p.style.name == "Bibliography"]
    assert len(bibliography) == 2, (style, [p.text for p in bibliography])

    text = docx_text(out)
    assert "@alpha" not in text and "@beta" not in text, style
    assert "Alpha One" in text and "Beta Two" in text, style

    # 五类上下文都要真的出现过引文，而不是“整篇导出成功”就算数。
    # 数字制是 [1]/[2]，作者-年份制会出现 Alpha/Beta/Gamma 或年份；只要整段
    # 引文被安静丢掉，下面这些上下文里就只剩原文的普通单词。
    def has_citation(value: str) -> bool:
        return bool(re.search(r"Alpha|Beta|Gamma|\[\d+\]|\(\d{4}\)|\b\d{1,3}\b", value))

    table_cells = [
        cell.text for table in document.tables for row in table.rows for cell in row.cells
    ]
    assert any(has_citation(cell) for cell in table_cells), (style, table_cells)

    list_items = [p.text for p in document.paragraphs if p.text.startswith("A list item cites")]
    assert len(list_items) == 1 and has_citation(list_items[0]), (style, list_items)

    quote_text = "\n".join(p.text for p in document.paragraphs if p.text.startswith("A quotation cites"))
    assert has_citation(quote_text), (style, quote_text)

    with zipfile.ZipFile(out) as archive:
        footnotes = archive.read("word/footnotes.xml").decode("utf-8")
    foot_text = " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", footnotes))
    assert has_citation(foot_text), (style, foot_text)


def test_a_citation_only_in_a_footnote_reaches_the_bibliography(tmp_path: Path) -> None:
    """脚注里的引文也必须进文献表；否则正文脚注 [9] 在文献表里没有对应条目。"""
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    md = tmp_path / "note.md"
    md.write_text(
        "---\nbibliography: refs.bib\n---\n\n# 一\n\n正文[^n]。\n\n"
        "[^n]: 只在脚注里引用 [@alpha]。\n\n%% 参考文献标题 参 考 文 献\n",
        encoding="utf-8",
    )
    out = tmp_path / "note.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=md, output_path=out, format_path=PRESET, audit=False,
    ))
    assert result.returncode == 0, result.errors
    bibliography = [p.text for p in Document(out).paragraphs if p.style.name == "Bibliography"]
    assert len(bibliography) == 1, bibliography
    assert "Alpha One" in bibliography[0]
