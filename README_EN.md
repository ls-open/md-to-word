# md-to-word: Compliant Word (.docx) Typesetting Skill for AI Agents & Markdown

[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Release v1.2.0](https://img.shields.io/badge/Release-v1.2.0-blue.svg)](https://github.com/ls-open/md-to-word/releases/tag/v1.2.0)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)](https://www.python.org/)

[English](README_EN.md) | [简体中文](README.md)

> **Write with Markdown and track with Git; let AI deliver compliant Word (`.docx`) documents automatically.**  
> Effortlessly produce Word files meeting the rigorous formatting standards of **university theses, academic journals, corporate whitepapers, and official reports**.

---

## 💡 Why Markdown + md-to-word?

When writing academic theses, technical reports, and corporate proposals, teams often suffer from Word's inherent collaboration bottlenecks:

* **Word (`.docx`) is an Opaque Binary Black Box**: Git cannot perform line-by-line diffs on binary files. Branch merges frequently corrupt documents, forcing teams to rely on painful file names like `thesis_final_v2_really_final.docx`.
* **Format Tuning Wastes Endless Time**: Authors spend hours manually formatting styles, unlinking headers, adjusting table borders, and pressing spaces to align equations—only to lose all formatting when text content changes.

**The Modern Engineering Workflow of md-to-word**:
1. **Decouple Content from Typography**: Authors write pure Markdown, enjoying the full benefits of Git version control, branching, Pull Request reviews, and CI/CD pipelines.
2. **AI-Agent Native**: LLMs excel at generating and refactoring Markdown; paired with this skill, AI agents can execute end-to-end typesetting and delivery autonomously.
3. **Deterministic Delivery**: Powered by a clean Word 365 base template and declarative specifications, the tool automatically compiles standardized Word documents that satisfy strict review requirements.

---

## ⚡ 30 seconds: what you write vs. what you get

Layout rules live in `requirements.txt` — **one per line, diffable in Git**, no clicking around in Word.

**You write** ([`demo/00_quickstart/hello.md`](demo/00_quickstart/hello.md), excerpt):

```markdown
---
title: "我的第一份规范 Word 文档"   # "My first properly formatted Word document"
crossref:
  tbl-prefix: "表"                  # table numbering prefix
---

# 引言

这是一份最小样例：一页纸、二十六行 Markdown。中文首行缩进两个字符、西文用
Times New Roman、行距 1.5 倍、各级标题黑体——这些都不用你在 Word 里点。

# 一个三线表

| 样例 | 篇幅 | 稳定耗时 | 主要演示的排版要素 |
|:------|:--|:---|:--------------|
| 最小样例（本文） | 1 页 | 0.95 s | 中西文字体、首行缩进、多级标题、三线表 |
| 技术白皮书样例 | 3 页 | 1.03 s | 全网格数据表、APA 引用、单线极简页眉 |
| 学位论文样例 | 8 页 | 1.15 s | 目录、分节页码、双线章名页眉、跨页表头 |

…(the table-caption wrapper and the surrounding prose are elided — see the source file)
```

**You run**:

```bash
bash scripts/export.sh hello.md -r requirements.txt -o hello.docx
```

**You get** (about one second):

[![Output of the 30-second example](demo/00_quickstart/page-1.png)](demo/00_quickstart/hello.docx)

Two-character first-line indent, Times New Roman for Latin, a three-line table with caption and note — **none of it clicked together by hand**.

### Reading that `requirements.txt`

It is the skill's only user-facing language, and it holds two kinds of lines:

- a **document setting** — `<key>：<value>`, e.g. page size, margins, page numbering;
- a **style definition** — `<style name>：<font> <size> <attributes…>`, one line per Word style.

A line whose **first character** is `#` is a comment (useful for recording where a rule came
from). An inline `#` is *not* a comment — it is an unknown word and gets rejected, like any
other typo.

Here is [`demo/00_quickstart/requirements.txt`](demo/00_quickstart/requirements.txt) — all 16
lines, of which 14 carry a rule (the rest are blank) — glossed:

| Line as written | What it says |
|:--|:--|
| `纸张：A4` | Paper size — `A4` or `Letter` (A4 if omitted) |
| `页边距：上2.54cm 下2.54cm 左2.54cm 右2.54cm` | Margins — top / bottom / left / right. All four required, cm only |
| `西文字体：Times New Roman` | Global Latin font, used by any style that does not name its own |
| `校对语言：zh-CN` | Proofing language — without it Word flags the whole document as misspelled |
| `文档标题：黑体/Times New Roman 二号 加粗 不倾斜 居中 行距1.5倍 段前0磅 段后12磅 首行缩进0字符 无边框` | **Title**: Chinese / Latin font, `二号` (22pt), **bold**, *not* italic, centered, 1.5× line spacing, 0pt before / 12pt after, 0 first-line indent, no border |
| `一级标题：… 与下段同页` | **Heading 1** — same field order, ending in "keep with next paragraph" |
| `正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符` | **Body Text**: SimSun / Times New Roman, `小四` (12pt), **not** bold, **not** italic, justified, 1.5× spacing, 0pt/0pt, 2-character first-line indent |
| `首段：…` | **First Paragraph** — the paragraph right after a heading; spelled out in full, same as Body Text here |
| `普通：…` | **Normal** — the inheritance root; must be spelled out or the base template's values propagate to every style derived from it |
| `紧凑：宋体/Times New Roman 五号 … 行距1.0倍 段前0磅 段后0磅 首行缩进0字符` | **Compact** — every table cell *and* every Markdown list item: one size down (`五号` = 10.5pt), single spacing, no indent |
| `表格：居中 三线表 线宽上1.5磅 线宽底1.5磅 线宽表头下0.75磅 单元格垂直居中` | **Table**: centered, three-line layout, 1.5pt top and bottom rules, 0.75pt under the header row, cells vertically centered |
| `表头：… 跨页重复` | **Header row** — its own font/size/bold, plus "repeat on every page" |
| `表格题注：…` / `表注：…` | **Table Caption** / **Table Note** |

**Every attribute has exactly one accepted spelling.** Anything outside the vocabulary is a
hard error that names the line, the word and the expected form — never a silent fallback to
some default. That is the whole point: a rule that is *written but ignored* produces a
document that looks fine and is wrong. The complete vocabulary is
[`references/reference.md §1.5`](references/reference.md).

## 📄 Already have a template? (from your school, journal, or employer)

No need to transcribe its formatting by hand. Hand the `.docx` to your assistant and have it reverse-engineer a `requirements.txt` draft:

```bash
python3 scripts/read_reference_docx.py school_template.docx -o thesis_requirements.txt
```

It reads page size, margins, header/footer distances, page-number format and start, per-style CJK and Latin fonts, sizes, bold/italic, alignment, line spacing (**distinguishing multiple / exact / at-least**), space before/after, indentation (**including character units**), paragraph bottom borders, table borders and header rows, and header/footer content and fields. **Anything it cannot read is listed as a to-confirm list** — it does not pretend.


## 🚀 Install It: three steps, all handed to your AI assistant

This skill is tuned for **AI agents** — you never touch a terminal; hand the repository to your assistant and it does the rest.

1. **Let the assistant install it** — paste this line verbatim. Every assistant keeps skills somewhere different, and so does every OS; **let it work that out for itself**:

   > Install this skill for me: https://github.com/ls-open/md-to-word
   > Clone it into your skills directory, then read SKILL.md and tell me what it can do and how it is triggered.

2. **Verify the install** — ask it to run the smallest sample in the repo. Seeing `✅ Word 文档导出成功` means you are set:

   ```bash
   cd demo/00_quickstart
   bash ../../scripts/export.sh hello.md -r requirements.txt -o hello.docx
   ```

3. **Start using it** — send your Markdown and state the target format:

   > Export this Markdown document to Word (.docx) according to my university's master's thesis formatting guidelines.

   It then handles everything: layout and font requirements, a compliant base template, OOXML cleanup, three quality gates, and the finished `.docx`.

> 💡 **CLI / CI**: you can also call it directly:
> `bash scripts/export.sh input.md [-r requirements.txt] -o output.docx`
>
> Add `--pdf` to also render a PDF through the local Word — **the only way to actually expand the table-of-contents page numbers and chapter-name headers**, and the most direct way to check the finished document (**macOS only**, and it needs Word installed and launched at least once; when unavailable it is skipped and the `.docx` is unaffected).

## 📸 Typesetting Showcase (Self-Documenting Demos)

Besides the minimal sample above, the repository bundles **two complete demos**, both written about md-to-word's engineering principles and benchmarks, demonstrating real-world formatting performance:

### Showcase 1: Academic Thesis & Journal Paper (Full Elements)
> Independent lowercase Roman front-matter page numbers (`i, ii`), a native dynamic TOC (down to level 2), dual-line chapter headers, **a three-line table whose header row repeats when it spans pages**, chapter-scoped equation numbers (`（2-1）`, the CJK thesis form) centred with the number hard right, GB/T 7714-2015 numeric citations — plus a **1 cm gutter**, **22 lines per page**, and **1 pt character spacing** on the title.

📁 Source, formatting rules and one-command reproduction → **[demo/01_chinese_thesis](demo/01_chinese_thesis/README.md)**

| Title & Abstract (Centered Title / No Header) | Dynamic TOC (Dot Leaders / Roman Page Numbers) | Dynamic Chapter Header & Architecture Chart |
| :---: | :---: | :---: |
| ![Thesis Title](demo/01_chinese_thesis/page-1.png) | ![Thesis TOC](demo/01_chinese_thesis/page-2.png) | ![Figures and Text](demo/01_chinese_thesis/page-3.png) |

| Centered Math Equations & Convergence Chart | Three-Line Academic Table & GB/T 7714 References |
| :---: | :---: |
| ![Equation and QA Pipeline](demo/01_chinese_thesis/page-4.png) | ![Header Row Repeating Across Pages](demo/01_chinese_thesis/page-7.png) |

---

### Showcase 2: Modern Enterprise Whitepaper & Research Report
> Flat single-section structure, executive summary, sleek single-line header, full-grid data tables, and APA 7th author-date citation style.

📁 Source, formatting rules and one-command reproduction → **[demo/02_modern_report](demo/02_modern_report/README.md)**

| Executive Summary & Section 1 | Efficiency Model & Benchmark Chart | Full-Grid Data Table & APA References |
| :---: | :---: | :---: |
| ![Report Front](demo/02_modern_report/page-1.png) | ![Benchmark](demo/02_modern_report/page-2.png) | ![Grid Table and References](demo/02_modern_report/page-3.png) |

---

## 🔍 Comparison: the same result, and what each tool needs to get there

Ground rules: every tool is judged on its **default output** (no custom template, no filter). ⚠️ = possible, but you hand-edit the base template, set it paragraph-by-paragraph and table-by-table, or write XML yourself; ✅ = comes out of the box; ❌ = not available by default. **The last column is what this skill actually asks you to write.**

| Typesetting element | Native Pandoc default | Quarto default Word | Manual Word tuning | 🌟 md-to-word: write this |
|:---|:---:|:---:|:---:|:---|
| **Chinese document basics** | | | | |
| Separate CJK and Latin fonts (SimSun + Times New Roman) | ⚠️ Edit base template | ⚠️ Edit base template | ⚠️ Per paragraph | `正文：宋体/Times New Roman 小四 …` |
| Chinese font sizes + 2-character first-line indent | ❌ | ❌ | ⚠️ Per paragraph | `… 首行缩进2字符` |
| Document proofing language (CJK text not flagged) | ✅ On by default | ✅ On by default | ⚠️ Set manually | `校对语言：zh-CN` (pinned, not left to the renderer) |
| **Academic typesetting** | | | | |
| Three-line tables with adjustable rules | ⚠️ Edit base template | ⚠️ Edit base template | ⚠️ Per table | `表格：居中 三线表 线宽上1.5磅 线宽表头下0.75磅` |
| Header row repeats across pages | ✅ On by default | ✅ On by default | ⚠️ Per table, tick a box | `表头：… 跨页重复` |
| Centered display math, equation number hard right | ❌ No numbering (`{#eq-x}` leaks into the text) | ⚠️ Equation centres, number trails it | ⚠️ Manual 3-column tab stops | `$$…$$ {#eq-x}` handles both |
| Dynamic chapter-name header (double rule) | ❌ Edit template + insert field | ❌ Edit template + insert field | ⚠️ Break sections + insert field | `页眉内容：{样式标题:Heading 1}` |
| Roman front matter / Arabic body pagination | ❌ | ❌ | ⚠️ Insert section break by hand | `{{< section 页码=小写罗马 起始=1 >}}` |
| Native dynamic table of contents | ⚠️ A real field, but styling needs the base template | ⚠️ A real field, but styling needs the base template | ⚠️ Insert field by hand | `{{< toc 2 >}}` (entry appearance is Word's own — see `references/reference.md §1.5`) |
| Equation cross-references with a CJK prefix (`式 1`) | ❌ No numbering (`{#eq-x}` leaks into the text) | ✅ Numbered, but the prefix is English `Equation 1` | ❌ | `{#eq-x}` + `crossref:` in YAML (**figure/table numbers are still written by hand in the caption**) |
| Formatted bibliography (GB/T 7714, APA, …) | ✅ citeproc | ✅ citeproc | ❌ | `csl: apa.csl` + `[@key]` in prose |
| **Built for AI and automation** | | | | |
| Layout rules declared in text, reviewable in Git | ❌ Buried in XML and manual steps | ❌ | ❌ | One `requirements.txt` states it all |
| Failure mode: error, or silent drift? | ⚠️ Mostly silent | ⚠️ Mostly silent | ❌ Eyes only | Pre-flight check, reported by line number |
| Quality gates before delivery | ❌ | ❌ | ❌ | Three: pre-flight / number diff / item-by-item audit |

> **Not listed in the table above** — footnotes (`[^1]`), odd/even and first-page headers and footers plus the `{总页数}` field, four table border styles (three-line / full grid / top-and-bottom / none), using an existing `.docx` as the base template (`-t`), and stripping HTML comments from the manuscript before export (`--strip-comments`).
>
> The ✅ marks under Pandoc and Quarto are **honest** — repeating header rows and citeproc bibliographies, for instance, do come out of the box. The value here isn't that others *can't*; it's that a single `requirements.txt` settles **all of it at once**, with no base-template surgery, no XML, and no per-paragraph clicking.

---

## 📚 FAQ: What is a BibTeX (.bib) File and How to Get It?

For users unfamiliar with academic bibliography workflows:

* **What is `.bib`?**  
  `.bib` (BibTeX) is the global standard plain-text format for structured reference databases. Each entry includes publication type, authors, title, journal, volume, and year.
* **How to Obtain It? (No Manual Coding Required)**:
  1. **One-Click Web Export (Google Scholar, CNKI, Baidu Scholar)**:  
     Search for the paper → click the **"Cite"** button → select **"BibTeX"** → copy the text into `references.bib`.
  2. **Batch Export from Reference Managers (Zotero, EndNote, Mendeley)**:  
     Select papers in your library → right click **"Export Library / Items"** → choose **BibTeX** format.
* **How to Cite in Markdown?**  
  Simply write `[@citekey]` (e.g., `[@vaswani2017]`) in your prose. The compiler will automatically format in-text citations and generate the end-of-document bibliography according to your chosen CSL style (e.g., `chinese-gb7714-2015-numeric.csl` or `apa.csl`).

---

## 🛠️ Environment Prerequisites

Running this skill requires only two lightweight prerequisites:

1. **Python Dependencies** (Python 3.9+):
   ```bash
   pip install -r requirements.txt
   ```
2. **Quarto Engine** (Quarto ≥ 1.4, includes Pandoc):
   ```bash
   # macOS
   brew install quarto

   # Linux / Windows: Download installer from https://quarto.org/docs/get-started/
   ```

---

## 📖 Skill Routing & Documentation

| Path | Purpose & Target Audience |
| :--- | :--- |
| [`demo/00_quickstart/`](demo/00_quickstart/) | **Smallest runnable sample** (1 page): a 26-line manuscript plus a 14-line `requirements.txt` (blank lines excluded). Use it to grasp input vs. output in 30 seconds, and to verify the install. |
| [`SKILL.md`](SKILL.md) | **Must-read for AI Agents**: Agent automation workflows, Markdown syntax contracts, and best practices. |
| [`references/reference.md`](references/reference.md) | **Advanced Customization**: Complete vocabulary for `requirements.txt`, default inference rules, and the 20 built-in CSL styles. |
| [`references/design.md`](references/design.md) | **Developers & Hackers**: In-depth architecture, pure Word 365 base template, 3-column equation alignment, and OpenXML internals. |

---

## 📄 License

Open-sourced under the [MIT License](LICENSE) — free to use, modify and distribute, **commercial use included**.
