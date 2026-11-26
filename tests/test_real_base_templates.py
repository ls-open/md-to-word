"""真实底模：不只验“灌进去了”，还要验灌进去之后正文没变样。

模板体积大、来源许可不一，放在被 `.gitignore` 忽略的 `testdata/base_templates/`，
有就跑、没有就整份跳过。它补的是合成底模很难覆盖的东西：真实模板的多节结构、
表格/图片封面、域、批注、外部链接与复杂样式。

安全底线：任何模板都不允许带 VBA 宏；测试只读 XML / 用纯 Python 注入，不运行宏。
"""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest
from docx import Document

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.template.base_inject import inspect_base

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "testdata" / "base_templates"
MANIFEST = FIXTURES / "MANIFEST.json"

pytestmark = [
    pytest.mark.localdata,
    pytest.mark.skipif(not MANIFEST.is_file(), reason="本机没有真实底模目录，跳过"),
]

BIB = """
@article{alpha,
  author = {Alpha, Ann and Beta, Bob},
  title = {Alpha One},
  journal = {Journal of Tests},
  year = {2020},
  volume = {1},
  pages = {1--9}
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


def _manifest() -> list[dict]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _rich_manuscript(lang: str) -> tuple[str, str]:
    """(正文, 正文起点标记)。同一套结构，中英文各一份。"""
    if lang == "zh":
        marker = "1 研究背景与问题"
        body = f"""---
bibliography: refs.bib
---

# {marker}

这是正文开头，包含**加粗**、*斜体*、`行内代码`、上标 x^2^、下标 H~2~O、行内公式 $x^2+y^2=z^2$，以及文献引用 @alpha 和 @beta。

脚注引用[^n]与交叉引用 @eq-short 都在这一节。

$$a^2+b^2=c^2$$ {{#eq-short}}

$$
\\begin{{aligned}}
f(x) &= \\frac{{1}}{{\\sqrt{{2\\pi\\sigma^2}}}} \\exp\\left(-\\frac{{(x-\\mu)^2}}{{2\\sigma^2}}\\right) \\\\
g(x) &= \\int_{{-\\infty}}^{{x}} f(t)\\,dt
\\end{{aligned}}
$$ {{#eq-long}}

$$
\\begin{{cases}}
x+y=1 \\\\
x-y=0
\\end{{cases}}
$$ {{#eq-cases}}

%% 表题 **表 1** 三线表示例

| 指标 | 数值 | 说明 |
|:--|--:|:--|
| 甲 | 42 | 第一行 |
| 乙 | 3.14159 | 第二行 |

%% 表注 注：表格用于真实底模注入后的结构核对。

![](pic.png){{width=6cm}}

%% 图片题注 图 1 示意图

- 列表第一项，引用 @alpha。
  - 嵌套第二层。
- 列表最后一项。

> 引用块里的文字，引用 @beta。

```text
code line with @alpha and 42
```

# 参考文献 {{.unlisted}}

[^n]: 脚注里的说明，引用 @alpha。
"""
        return body, marker

    marker = "1 Research Background and Questions"
    body = f"""---
bibliography: refs.bib
---

# {marker}

This body opens with **bold**, *italic*, `inline code`, superscript x^2^, subscript H~2~O, inline math $x^2+y^2=z^2$, and citations @alpha and @beta.

A footnote reference[^n] and a cross-reference @eq-short both live here.

$$a^2+b^2=c^2$$ {{#eq-short}}

$$
\\begin{{aligned}}
f(x) &= \\frac{{1}}{{\\sqrt{{2\\pi\\sigma^2}}}} \\exp\\left(-\\frac{{(x-\\mu)^2}}{{2\\sigma^2}}\\right) \\\\
g(x) &= \\int_{{-\\infty}}^{{x}} f(t)\\,dt
\\end{{aligned}}
$$ {{#eq-long}}

$$
\\begin{{cases}}
x+y=1 \\\\
x-y=0
\\end{{cases}}
$$ {{#eq-cases}}

%% Table Caption **Table 1** Three-line sample

| Item | Value | Note |
|:--|--:|:--|
| Alpha | 42 | first row |
| Beta | 3.14159 | second row |

%% Table Note Note: used to check structure after base injection.

![](pic.png){{width=6cm}}

%% Image Caption Figure 1 sample

- First list item, cites @alpha.
  - Nested second level.
- Last list item.

> Quoted body text cites @beta.

```text
code line with @alpha and 42
```

# References {{.unlisted}}

[^n]: A footnote sentence cites @alpha.
"""
    return body, marker


def _tail(path: Path, marker: str) -> list[str]:
    """正文起点之后的段落文字。样式名可随底模本地化命名变化，正文不能。"""
    paragraphs = Document(path).paragraphs
    index = next((i for i, p in enumerate(paragraphs) if marker in p.text), None)
    assert index is not None, f"{path.name} 里找不到正文起点 {marker!r}"
    tail = [p.text for p in paragraphs[index:]]
    while tail and not tail[-1].strip():
        tail.pop()
    return tail


def _table_rows(path: Path) -> list[tuple[str, ...]]:
    return [
        tuple(cell.text.strip() for cell in row.cells)
        for table in Document(path).tables
        for row in table.rows
    ]


def _media_bytes(path: Path) -> set[bytes]:
    with zipfile.ZipFile(path) as archive:
        return {
            archive.read(name) for name in archive.namelist()
            if name.startswith("word/media/")
        }


def _footnote_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        try:
            xml = archive.read("word/footnotes.xml").decode("utf-8")
        except KeyError:
            return ""
    import re

    return " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


def _omath_texts(path: Path) -> list[str]:
    """每个公式的可见文字，用来确认正文里的公式内容也原样跟过去了。"""
    import re

    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    found = []
    for block in re.findall(r"<m:oMath[ >].*?</m:oMath>", xml, re.S):
        found.append("".join(re.findall(r"<m:t[^>]*>([^<]*)</m:t>", block)))
    return found


def test_templates_are_safe_to_inspect() -> None:
    """每份模板都能打开、不含宏；不能因为来源是真实文件就跳过检查。"""
    records = _manifest()
    assert records, "MANIFEST.json 是空的"

    for record in records:
        base = FIXTURES / record["file"]
        assert base.is_file(), record["file"]
        with zipfile.ZipFile(base) as archive:
            names = [name.lower() for name in archive.namelist()]
        assert not any(name.endswith("vbaproject.bin") for name in names), record["file"]
        assert record.get("has_macro") is False, record["file"]

        # 模板是本地下载物，清单里记了摘要：文件被替换/截断时当场发现
        import hashlib

        digest = hashlib.sha256(base.read_bytes()).hexdigest()[:16]
        assert digest == record["sha256"], f"{record['file']} 与清单摘要不一致"

        # 能读、能体检，不抛异常（是否允许灌入由具体切点决定，下一页的正文比对再验）
        inspect_base(base, 1, record["lang"])


def test_real_templates_keep_the_body_identical(
    tmp_path: Path, monkeypatch,
) -> None:
    """真实模板注入后，正文必须和不用底模的导出逐段一致。

    比较不是“灌入成功”就结束：正文从唯一标记开始逐段比文本，并核对表格行、图片字节、
    脚注、公式数量与参考文献段落。只有前置件不同，正文没有理由不同。
    """
    from md_to_word.visual_qa import word_pdf

    monkeypatch.setattr(word_pdf, "can_render_word_pdf",
                        lambda: (False, "disabled in real-template body check"))

    successes = 0
    for record in _manifest():
        if record["sections"] < 2:
            continue
        base = FIXTURES / record["file"]
        work = tmp_path / record["slug"]
        work.mkdir()
        (work / "refs.bib").write_text(BIB, encoding="utf-8")
        shutil.copyfile(REPO_ROOT / "demo" / "00_quickstart" / "page-1.png", work / "pic.png")
        body, marker = _rich_manuscript(record["lang"])
        manuscript = work / "m.md"
        manuscript.write_text(body, encoding="utf-8")
        preset = "zh-academic" if record["lang"] == "zh" else "en-nature"

        reference = work / "reference.docx"
        no_base = run_export_pipeline(ExportOptions(
            input_path=manuscript, output_path=reference, preset=preset,
        ))
        assert no_base.returncode == 0, (record["slug"], no_base.errors)

        with_base = work / "with-base.docx"
        result = run_export_pipeline(ExportOptions(
            input_path=manuscript,
            output_path=with_base,
            preset=preset,
            base_template=base,
            cover_sections=1,
        ))
        if result.returncode != 0:
            assert result.returncode == 1, (record["slug"], result.errors)
            assert "pipeline.base_failed" in {d.code for d in result.diagnostics}, (
                record["slug"], result.diagnostics)
            continue

        successes += 1
        Document(with_base)  # 产物仍是合法 docx
        assert _tail(with_base, marker) == _tail(reference, marker), record["slug"]

        ref_rows = _table_rows(reference)
        base_rows = set(_table_rows(with_base))
        assert set(ref_rows) <= base_rows, (record["slug"], "正文表格行丢失")

        assert _media_bytes(reference) <= _media_bytes(with_base), (record["slug"], "正文图片丢失")
        ref_footnotes = _footnote_text(reference)
        assert ref_footnotes.strip() and ref_footnotes.strip() in _footnote_text(with_base), (
            record["slug"], "脚注内容丢失")
        reference_math = set(_omath_texts(reference))
        assert reference_math <= set(_omath_texts(with_base)), (record["slug"], "公式内容丢失")

    assert successes >= 5, f"真实模板成功注入太少：{successes}"


@pytest.mark.skipif(
    not __import__("md_to_word.visual_qa.word_pdf", fromlist=["can_render_word_pdf"])
    .can_render_word_pdf()[0],
    reason="本机没有 Microsoft Word",
)
def test_a_real_thesis_template_passes_page_verification(tmp_path: Path) -> None:
    """有 Word 时，拿真实 14 节学位论文模板跑一遍逐页封面验真。"""
    base = FIXTURES / "zh" / "uni-sjtu.docx"
    if not base.is_file():
        pytest.skip("没有 uni-sjtu 模板")
    body, _marker = _rich_manuscript("zh")
    (tmp_path / "refs.bib").write_text(BIB, encoding="utf-8")
    shutil.copyfile(REPO_ROOT / "demo" / "00_quickstart" / "page-1.png", tmp_path / "pic.png")
    manuscript = tmp_path / "m.md"
    manuscript.write_text(body, encoding="utf-8")
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "out.docx",
        preset="zh-academic",
        base_template=base,
        cover_sections=1,
    ))
    assert result.returncode == 0, result.errors
