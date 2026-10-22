# md-to-word

[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)](https://www.python.org/)

English | [简体中文](README.md)

Compiles Markdown into compliant Word (`.docx`) files: **theses, journal manuscripts, technical
reports and official documents**. Layout lives in a `requirements.txt` that goes into Git together
with the manuscript. Export is deterministic — the same sources produce the same output on every
run. A pre-flight check runs before export and a reconciliation pass after it; anything off-contract
stops the run with a line number.

> Two premises: **content and layout are separate** (Markdown is the source, layout is declared);
> **an AI agent can do the whole job** (the user states the requirement, the agent extracts formats,
> normalises the manuscript and closes the quality loop).

---

## 30-second example

**You write** ([`demo/00_quickstart/hello.md`](demo/00_quickstart/hello.md), excerpt):

```markdown
---
crossref:
  tbl-prefix: "表"
---

%% 文档标题 我的第一份规范 Word 文档

# 引言

这是一份最小样例：一页纸、二十二行 Markdown。中文首行缩进两个字符、西文用
Times New Roman、行距 1.5 倍、各级标题黑体——这些都不用你在 Word 里点。

# 一个三线表

%% 表题 **表 1** 三套样例的端到端导出耗时

| 样例 | 篇幅 | 稳定耗时 | 主要演示的排版要素 |
|:------|:--|:---|:--------------|
| 最小样例（本文） | 1 页 | 0.15 s | 中西文字体、首行缩进、多级标题、三线表 |
| 技术白皮书样例 | 5 页 | 0.30 s | 全网格数据表、APA 引用、单线极简页眉 |
| 学位论文样例 | 8 页 | 0.43 s | 目录、分节页码、双线章名页眉、跨页表头 |
```

**You declare** ([`demo/00_quickstart/requirements.txt`](demo/00_quickstart/requirements.txt), excerpt):

```text
纸张：A4
页边距：上2.54cm 下2.54cm 左2.54cm 右2.54cm
西文字体：Times New Roman

文档标题：黑体/Times New Roman 二号 加粗 不倾斜 居中 行距1.5倍 段前0磅 段后12磅 首行缩进0字符 无边框
一级标题：黑体/Times New Roman 三号 加粗 不倾斜 左对齐 行距1.5倍 段前12磅 段后6磅 首行缩进0字符 与下段同页
正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符
表格：居中 三线表 线宽上1.5磅 线宽底1.5磅 线宽表头下0.75磅 单元格垂直居中
表头：宋体/Times New Roman 五号 加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 跨页重复
```

**You run**:

```bash
md-to-word hello.md -r requirements.txt -o hello.docx
```

**You get** (about 0.2 s, one page):

[![Output of the minimal demo](demo/00_quickstart/page-1.png)](demo/00_quickstart/hello.docx)

Two-character first-line indent, Times New Roman for Latin text, a three-line table with caption
and note — nothing was clicked in Word.

---

## Install

There is one implementation: the Python package `md-to-word`. The skill, the command line and the
library API are all entries into it.

| Entry | For | Install | Use |
|:--|:--|:--|:--|
| **Command line** | local exports, CI | `pip install md-to-word` | `md-to-word paper.md -o paper.docx` |
| **Python library** | scripts, custom pipelines | same | `from md_to_word import export` |
| **AI skill** | handing the job to an agent | put `SKILL.md` + `references/` + `scripts/` in the skill directory, then install the package | "Export this manuscript as Word, following my school's format." |

**PyPI status**: not published yet. Until then install from source or Git; after the release the
first command above is the one to use.

```bash
pip install "git+https://github.com/ls-open/md-to-word@main"
pip install -r requirements.txt    # or install dependencies inside a source checkout
```

Updates: `pip install -U md-to-word` (use `pipx install` / `pipx upgrade` to keep it out of the
system environment). Skill files only need reinstalling when the documentation changes — that is the
point of keeping the implementation in the package.

**Dependencies**: `python-docx`, `lxml`, `PyYAML`, `latex2mathml`, `citeproc-py` — five pure-Python
packages. **Export needs no external binary**: no Pandoc, no Quarto, no Word. Only the optional
`--pdf` proof uses the local Word installation (macOS only; skipped elsewhere, `.docx` unaffected).

---

## Usage

**Command line**:

```bash
md-to-word paper.md -o paper.docx                    # default Chinese preset (zh-academic)
md-to-word paper.md --preset en-nature -o out.docx   # English journal preset
md-to-word paper.md -r format.txt -o out.docx        # explicit requirements file
md-to-word --help                                    # all options; help follows manuscript language
```

Exit codes: `0` done; `1` manuscript, gate or dependency problem; `3` `.docx` written but `--pdf`
was skipped (non-macOS).

**Python**:

```python
from md_to_word import export

result = export("paper.md", "paper.docx", preset="zh-academic")
if not result.ok:            # ok = the .docx was written (a skipped --pdf is not a failure)
    raise SystemExit("\n".join(result.errors))
print(result.output_docx)    # result.messages holds progress notes and reminders
```

**AI skill**: hand the Markdown to an agent together with the format requirement. The agent reads
`SKILL.md` and runs format extraction, manuscript normalisation, template generation and the gates.
Trigger phrases and scope are in that file's frontmatter.

---

## Capabilities and limits

| Supported | Notes |
|:--|:--|
| Page and body text | paper size, margins, gutter, document grid, CJK/Latin fonts, size, spacing, indent, alignment, colour |
| Headings, headers, footers | six heading levels, odd/even and first-page variants, page number format and start, sections, `{页码}` `{总页数}` `{样式标题}` fields |
| Tables | three-line / full grid / top-and-bottom / none, border widths, repeating header rows, cell alignment and padding, column width ratios |
| Equations | native OMML, centred with the number set hard right, per-chapter numbering, number template, `@eq-` cross-references |
| Figures and captions | image width clamped to the text block, caption bound to the figure, caption placement chosen by the author |
| Bibliography | `.bib` + CSL, 29 bundled styles (GB/T 7714, APA, Nature, IEEE, Vancouver and more) |
| Inline text | bold, italic, strikethrough, underline, super/subscript, inline code, inline maths, links, footnotes |
| Lists | ordered, unordered, three nesting levels, lists inside block quotes |
| Gates | pre-flight contract/style/citation check, post-export number audit, element-by-element style reconciliation |

**Not supported** (finish in Word, or restructure the manuscript):

| Not possible | Why, and what to do instead |
|:--|:--|
| Custom cover pages (crests, fill-in fields, signature sheets) | `%% 文档标题` produces one standard title block; merge the cover in Word, or typeset a simple one as a table |
| Merged cells, diagonal header rules, cell shading | Markdown tables are a regular 2-D grid; export the grid, merge in Word |
| Multi-column text, floating figures with text wrap | Single-column is the only layout; figures are standalone centred blocks; wrapping is a Word-side edit |
| Limits above/below Σ and ∫ in numbered equations | Word only stacks limits in display maths, and numbered equations are inline; symbols and content are correct, placement differs |
| Inline text colour | Colour is a style property (`颜色#1F4E79` on a style line); inline `{color=…}` is not supported |

The full vocabulary and rationale live in [`references/reference.md`](references/reference.md)
(Chinese); design decisions are in [`references/design.md`](references/design.md) (Chinese).

---

## Already have a template?

You do not have to transcribe a school or journal `.docx` by hand. Run the bundled reader against it
to get a draft requirements file:

```bash
python3 scripts/read_reference_docx.py school_template.docx -o paper_requirements.txt
```

It reads page size, margins, header/footer distances, page number format and start, per-style fonts
and sizes, bold/italic, alignment, line spacing (multiple, exact and minimum are distinguished),
space before and after, indents (including character units), paragraph bottom borders, table borders
and header rows, and header/footer content with fields. **Anything it cannot read is listed as a
to-confirm item** — it does not pretend to have read it.

---

## Repository layout

| Path | What it is for |
|:--|:--|
| [`SKILL.md`](SKILL.md) | Skill entry: agent workflow, manuscript contract, requirements assembly, export and verification |
| [`references/reference.md`](references/reference.md) | Complete vocabulary with wrong-spelling comparisons, derived defaults, CSL inventory |
| [`references/design.md`](references/design.md) | Design rationale and troubleshooting (start at its §2 when output looks wrong) |
| [`demo/`](demo/) | Four samples: minimal, Chinese thesis, technical whitepaper, English journal submission |
| `scripts/` | `export.sh` is a forwarding shell; the rest are development tools (read a template, build a template, check a manuscript, normalise CSL) |
| `src/md_to_word/` | The implementation: model → OOXML writer, style generation, validation, reconciliation |
| `resources/` | Word 365 base template and 29 normalised CSL styles |
| `presets/` | Built-in presets: `zh-academic.txt` (default), `en-nature.txt` |

What ships to a user's machine: `src/`, `presets/`, `resources/` and package metadata
(wheel ≈ 288 KB). `tests/`, `demo/`, `scripts/` and `references/` are the repository's acceptance
surface, not runtime dependencies.

---

## Built here, borrowed elsewhere

Layout, numbering, gates and the OOXML writer are this project's own code. Two pieces with public
standards are borrowed: LaTeX parsing (`latex2mathml`) and CSL citation rendering (`citeproc-py`).
The rule: **borrow what is standardised, build what is not**.

---

## License

Code is [MIT](LICENSE). Citation styles under `resources/csl/` come from
[citation-style-language/styles](https://github.com/citation-style-language/styles) and are used
under CC BY-SA 3.0. `resources/pure_modern_base.docx` is generated by this project and released
under MIT.
