# md-to-word

[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)](https://www.python.org/)

English | [简体中文](https://github.com/ls-open/md-to-word/blob/main/README.md)

Compile Markdown into a Word (`.docx`) document that matches a declared format. A thesis, a journal
submission, a technical report, an official document and a product manual all use the same notation
— only the `format.txt` differs. The typography lives beside the manuscript and goes into Git with
it; the same sources produce a byte-identical file on every run; an incomplete style line, an
unknown style name or a citation without a bibliography stops the export before a file is written,
with the line number.

[![Output of the English demo](https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/03_english_paper/page-1.png)](https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/paper.docx)

*Exported from [`demo/03_english_paper`](https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/):
APA author-date citations from a `.bib`, a centred equation with its number set hard right, a
three-line table with note above and below the rule — nothing was clicked in Word.*

---

## Installation

```bash
pip install md-to-word-docx
```

The distribution carries a `-docx` suffix because plain `md-to-word` is too close to existing PyPI
projects; the command is still `md-to-word`. Use `pipx install md-to-word-docx` to stay out of the
system environment, and `pip install -U md-to-word-docx` to update.

Read `md-to-word --guide` once: workflow, gate criteria, boundaries. It is the same text as
`SKILL.md` in the repository — skill users read that file, package users read this one; same
content, different entry.

## In 30 seconds

**Start with one command**: `md-to-word init` writes a `format.txt` and a `hello.md` that exports
as-is — see the finished file first, then change the content and the format.

```bash
md-to-word init
md-to-word hello.md -o hello.docx
```

**Write the manuscript** — ordinary Markdown, with three conventions: a line starting with `%%` sets
that paragraph's style, `$$…$$ {#eq-x}` is a numbered equation, and markers such as `{{< toc >}}`
stand on their own line.

```markdown
%% Title My first compliant Word document

# Introduction

One page of Markdown. The first-line indent, Times New Roman for Latin text and the
caption above the table are declared, not clicked.

%% Table Caption **Table 1** End-to-end export time of the samples

| Sample | Length | Time |
|:------|:--|:---|
| Minimal (this file) | 1 page | 0.15 s |
| Thesis sample | 8 pages | 0.43 s |
```

**Declare the format** — one line per style, complete fields (excerpt: a complete file also declares
the headings, footnotes, bibliography and page numbers):

```text
Paper: A4
Margins: top 2.54cm bottom 2.54cm left 2.54cm right 2.54cm
Font: Times New Roman

Title: Times New Roman 18pt bold not-italic left line-spacing 1.5 space-before 0pt space-after 12pt indent 0
Body Text: Times New Roman 12pt not-bold not-italic justify line-spacing 1.5 space-before 0pt space-after 0pt indent 0
First Paragraph: Times New Roman 12pt not-bold not-italic justify line-spacing 1.5 space-before 0pt space-after 0pt indent 0
Table: center three-line border-top 1pt border-bottom 1pt border-header 0.5pt valign center
Table Header: Times New Roman 10pt bold not-italic center line-spacing 1.0 space-before 0pt space-after 0pt indent 0 repeat-header
```

Each property has exactly one accepted spelling; every style name and value also has a Chinese
form, so the same engine takes `正文：宋体/Times New Roman 小四 …` from a Chinese manuscript. The
full vocabulary is in the manual (§3).

**Export**:

```bash
md-to-word manuscript.md -r format.txt -o manuscript.docx
```

About 0.2 s. Without `-r` the built-in preset applies, chosen by the manuscript's language:
`zh-academic` for Chinese, `en-nature` for everything else.

## Samples

Four samples, all really exported and opened in Word; the page images below are rendered from the
exported PDFs, not mock-ups.

| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png" width="250"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/01_chinese_thesis/thesis_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/01_chinese_thesis/page-1.png" width="250"></a> |
|:--:|:--:|
| **Minimal** · one page, shortest path from manuscript to file | **Chinese thesis** · TOC field, per-section page numbers, per-chapter equation numbers |
| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/02_modern_report/report_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/02_modern_report/page-1.png" width="250"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/paper.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/03_english_paper/page-1.png" width="250"></a> |
| **Technical whitepaper** · full-grid table, block quote, coloured heading | **English journal submission** · APA author-date, `Equation 1` cross-reference |

## What it does

- **Page and body text**: paper size, margins, gutter, document grid, CJK/Latin fonts, size, line spacing, indent, space before/after, alignment, colour
- **Headings, headers, footers**: six heading levels, odd/even and first-page variants, sections, page-number format and start, `{页码}` `{总页数}` `{样式标题}` fields
- **Tables**: three-line, full grid, top-and-bottom, none; border widths, repeating header rows, cell alignment and padding, column width ratios
- **Equations**: native OMML, centred with the number set hard right, per-chapter numbering, declarable number template, `@eq-` cross-references
- **Figures and captions**: image width clamped to the text block, caption bound to the figure, caption placement chosen by the author
- **Bibliography**: `.bib` + CSL, 29 bundled styles (GB/T 7714, APA, Nature, IEEE, Vancouver and more), or a CSL file of your own
- **Inline text**: bold, italic, strikethrough, underline, super/subscript, inline code, inline maths, links, footnotes
- **Lists**: ordered, unordered, three nesting levels, lists inside block quotes
- **Gates**: pre-flight contract/style/citation check, post-export number audit, element-by-element style reconciliation
- **No external binary**: no Pandoc, no Quarto, no Word

What it cannot do, and why, is in the manual
([`manual_en.md`](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual_en.md)
§6) — `md-to-word --contract` prints its path — together with the full vocabulary, in English and
Chinese. Design decisions are in
[`design.md`](https://github.com/ls-open/md-to-word/blob/main/references/design.md).

## Common notations

| What you want | What to write |
|:--|:--|
| A section heading | `# Introduction`, `## 2.1 Method` — one `#` per level, no skipped levels |
| A styled paragraph | Start the line with `%% Abstract …` (one line is one paragraph, no closing fence) |
| A numbered equation | `$$E=mc^2$$ {#eq-mass}`, referenced in the text as `@eq-mass` |
| A citation | `bibliography: refs.bib` in YAML, `[@smith2024]` in the text |
| A figure | `![](figures/arch.png){width=13cm}` then `%% Image Caption Figure 1 Architecture` |
| A table | `%% Table Caption **Table 1** …` above it, `%% Table Note Note: …` below it |
| A table of contents | `{{< toc >}}` on its own line |
| A new section with restarting page numbers | `{{< section page_number=lowerRoman start=1 >}}` on its own line |
| A page break | `{{< pagebreak >}}` on its own line |

## How it differs

| | Pandoc / Quarto | Typical Markdown→Word libraries | This one |
|:--|:--|:--|:--|
| Where the format lives | command-line flags + a Word template; details need XML | in code, or a few presets | one `format.txt`, versioned with the manuscript |
| Equation numbers set right | extra post-processing | usually not available | by default; per-chapter numbering is declared |
| Section page numbers, chapter headers | edit the template and insert fields | not supported | one marker + one requirements line |
| When something is wrong | mostly silently off | raise, or silently off | pre-flight with line numbers, audit after export |

What other tools already do by default — CJK/Latin font separation, three-line tables, repeating
header rows, bibliography typesetting — is supported here too; the table lists only the differences.

## Two more entry points

**As a library** — when it has to sit inside your own pipeline:

```python
from md_to_word import export

result = export("manuscript.md", "manuscript.docx")   # preset follows the manuscript language
if not result.ok:
    raise SystemExit("\n".join(result.errors))
```

**As an agent skill** — when the job goes to an agent: clone this repository and point the agent at
[`SKILL.md`](https://github.com/ls-open/md-to-word/blob/main/SKILL.md) in the root. It normalizes the
manuscript → writes `format.txt` → exports → reads the gates and fixes the reported lines.

**From a script or an agent** — add `--json`: one JSON object on stdout, messages on stderr.

```bash
md-to-word manuscript.md -o manuscript.docx --json
```

The keys are fixed (`ok`, `returncode`, `output`, `pdf`, `messages`, `errors`) and do not change
between versions; the sentences inside them follow the manuscript's language. Read the keys, not the
wording.

## Environment

- **Dependencies**: `python-docx`, `lxml`, `PyYAML`, `latex2mathml`, `citeproc-py` — five packages, all pure Python except `lxml` (a C extension, wheels available for every platform)
- **Export needs no external binary**: no Pandoc, no Quarto, no Word
- **Only the optional `--pdf` proof** uses the local Word installation (macOS; skipped elsewhere, `.docx` unaffected)
- **Chinese and English**: runtime messages, gate diagnostics and the manual each exist in both
  languages, chosen by the **manuscript's language** — an English manuscript gets English errors with
  English style-name examples, while a Chinese one is unchanged

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

## Recommended upstream

This project covers the last mile — deterministic typesetting and delivery. For drafting and
reference work, two academic agent frameworks are worth pairing with it:

- [Academic Research Skills](https://github.com/Imbad0202/academic-research-skills): a five-stage
  research and writing framework. After Stage 5 (FINALIZE) produces a Markdown draft and its
  bibliography, this tool turns it into a compliant `.docx`.
- [Nature Skills](https://github.com/Yuan1z0825/nature-skills): an agent skill set for academic
  writing — literature review, experimental argument and draft generation.

(This project is currently listed among the third-party entries of Academic Research Skills.)

## License

Code is [MIT](https://github.com/ls-open/md-to-word/blob/main/LICENSE). The bundled citation styles
come from [citation-style-language/styles](https://github.com/citation-style-language/styles) and
are used under CC BY-SA 3.0. The bundled base template is generated by this project and released
under MIT.
