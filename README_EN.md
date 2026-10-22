# md-to-word

[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)](https://www.python.org/)

English | [简体中文](https://github.com/ls-open/md-to-word/blob/main/README.md)

Compile Markdown into compliant Word (`.docx`): theses, journal manuscripts, technical reports and
official documents.

Three rules: **content and layout are separate** — the format lives in a `format.txt` that goes
into Git; **export is deterministic** — the same sources produce a byte-identical file on every run;
**the gates do not ship silent errors** — a pre-flight check runs before export and a reconciliation
pass after it, and anything off-contract stops the run with a line number.

---

## Two ways to use it

There is one engine (`src/md_to_word/`); both paths are entries into it.

### 1. As a command

For terminal exports, CI, or your own scripts.

```bash
pip install md-to-word-docx
md-to-word manuscript.md -o manuscript.docx
```

```python
from md_to_word import export

result = export("manuscript.md", "manuscript.docx")   # preset follows the manuscript language
if not result.ok:
    raise SystemExit("\n".join(result.errors))
```

- Update with `pip install -U md-to-word-docx` (use `pipx install` / `pipx upgrade` to stay out of the
  system environment)
- The distribution carries a `-docx` suffix because plain `md-to-word` is too close to existing PyPI
  projects; the command is still `md-to-word`
- No documentation at hand? `md-to-word --contract` prints the manuscript contract and the absolute
  paths of the full manual and the built-in presets

### 2. As a skill

For handing the job to an agent: state the format requirement, let the agent do the rest.

1. Clone this repository (or drop the directory into your skills directory)
2. Point the agent at `SKILL.md` in the repository root
3. The agent normalizes the manuscript → writes `format.txt` → exports → reads the gates and
   fixes the reported lines

**Nothing needs installing**: `scripts/export.sh` runs the source tree directly, and `SKILL.md` holds
only the order of work — every spelling is looked up in the manual shipped inside the package. Only
the dependencies are needed: `pip install -r requirements.txt`. Updates come with `git pull`.

The same entry also exists as [`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word)
in the `nature-skills` repository: documentation only, running on the same pip package — for people
who want the skill directory inside an agent but would rather not clone the engine repository.

| | As a command | As a skill |
|:--|:--|:--|
| Who works | you, from a terminal | an agent |
| What to install | `pip install md-to-word-docx` | dependencies only, not the package |
| Updates | `pip install -U md-to-word-docx` | `git pull` |
| What to read | this file and `--contract` | `SKILL.md`, details in the manual |

---

## 30-second example

**You write** ([`demo/00_quickstart/hello.md`](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.md), excerpt):

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

**You declare** ([`demo/00_quickstart/format.txt`](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/requirements.txt), excerpt):

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
md-to-word hello.md -r format.txt -o hello.docx
```

**You get** (about 0.2 s, one page):

[![Output of the minimal demo](https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png)](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx)

Two-character first-line indent, Times New Roman for Latin text, a three-line table with caption and
note — nothing was clicked in Word.

---

## Capabilities

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

What it cannot do, and why, is in the packaged manual
([`manual_en.md`](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual_en.md)
§6), together with the full vocabulary — both shipped in Chinese and English. Design decisions are
in [`references/design.md`](https://github.com/ls-open/md-to-word/blob/main/references/design.md).

---

## Environment

- **Dependencies**: `python-docx`, `lxml`, `PyYAML`, `latex2mathml`, `citeproc-py` — five pure-Python
  packages
- **Export needs no external binary**: no Pandoc, no Quarto, no Word
- **Only the optional `--pdf` proof** uses the local Word installation (macOS; skipped elsewhere,
  `.docx` unaffected)
- **Chinese and English**: runtime messages, gate diagnostics and the manual each exist in both
  languages, chosen by the **manuscript's language** — an English manuscript gets English errors with
  English style-name examples, while a Chinese one is unchanged

---

## Already have a template?

A school or journal `.docx` does not have to be transcribed by hand. Run the bundled reader against
it to get a draft requirements file:

```bash
md-to-word-template school_template.docx -o paper_format.txt
```

It reads page size, margins, header/footer distances, page number format and start, per-style fonts
and sizes, bold/italic, alignment, line spacing (multiple, exact and minimum are distinguished),
space before and after, indents (including character units), paragraph bottom borders, table borders
and header rows, and header/footer content with fields. **Anything it cannot read is listed as a
to-confirm item** — it does not pretend to have read it.

---

## Documentation and repository layout

| Path | What it is for |
|:--|:--|
| [`SKILL.md`](https://github.com/ls-open/md-to-word/blob/main/SKILL.md) | Skill entry: agent workflow, how to read the gates, boundaries. Facts live in the manual |
| [`src/md_to_word/resources/manual_en.md`](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual_en.md) | **The manual**: contract, full vocabulary, workflow, gates, limits, CSL inventory (also in Chinese) |
| [`references/design.md`](https://github.com/ls-open/md-to-word/blob/main/references/design.md) | Design rationale and troubleshooting (start at its §2 when output looks wrong) |
| [`demo/`](https://github.com/ls-open/md-to-word/blob/main/demo/) | Four samples: minimal, Chinese thesis, technical whitepaper, English journal submission |
| `scripts/` | Development and acceptance tools (see [`scripts/README.md`](https://github.com/ls-open/md-to-word/blob/main/scripts/README.md)) |
| `src/md_to_word/` | The implementation: model → OOXML writer, style generation, validation, reconciliation |
| `resources/` | Word 365 base template and 29 normalised CSL styles |
| `presets/` | Built-in presets: `zh-academic.txt`, `en-nature.txt` |

What ships to a user's machine: `src/` — which contains `md_to_word/presets/` and
`md_to_word/resources/`, both manuals included — plus package metadata (wheel ≈ 320 KB). `tests/`, `demo/`, `scripts/`, `references/` and `SKILL.md` are the
repository's acceptance surface and skill entry, not runtime dependencies.

**Exit codes**: `0` done; `1` manuscript, gate or dependency problem; `3` `.docx` written but `--pdf`
skipped. `md-to-word --help` lists every option, in the manuscript's language; `--verbose` logs each
style as it is applied.

---

## Recommended upstream

This project covers the last mile — deterministic typesetting and delivery. For drafting and
reference work, two academic agent frameworks are worth pairing with it:

- [Academic Research Skills](https://github.com/Imbad0202/academic-research-skills): a five-stage
  research and writing framework. After Stage 5 (FINALIZE) produces a Markdown draft and its
  bibliography, this tool turns it into a compliant `.docx`.
- [Nature Skills](https://github.com/Yuan1z0825/nature-skills): an agent skill set for academic
  writing — literature review, experimental argument and draft generation.

(This project is currently listed among the third-party entries of Academic Research Skills.)

---

## How it differs

| | Pandoc / Quarto | Typical Markdown→Word libraries | This one |
|:--|:--|:--|:--|
| Where the format lives | command-line flags + a Word template; details need XML | in code, or a few presets | one `format.txt`, versioned with the manuscript |
| Equation numbers set right | extra post-processing | usually not available | by default; per-chapter numbering is declared |
| Section page numbers, chapter headers | edit the template and insert fields | not supported | one marker + one requirements line |
| When something is wrong | mostly silently off | raise, or silently off | pre-flight with line numbers, audit after export |

What other tools already do by default — CJK/Latin font separation, three-line tables, repeating
header rows, bibliography typesetting — is supported here too; the table lists only the differences.

---

## License

Code is [MIT](https://github.com/ls-open/md-to-word/blob/main/LICENSE). Citation styles under
`resources/csl/` come from
[citation-style-language/styles](https://github.com/citation-style-language/styles) and are used
under CC BY-SA 3.0. `resources/pure_modern_base.docx` is generated by this project and released
under MIT.
