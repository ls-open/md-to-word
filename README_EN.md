# md-to-word

[![Official Skill: Nature Skills](https://img.shields.io/badge/Official%20Skill-Nature%20Skills%20(51k+%E2%98%85)-d9381e?logo=github&logoColor=white)](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)

**English** | [简体中文](https://github.com/ls-open/md-to-word/blob/main/README.md) | [Web Playground](https://124.220.135.226)

Compile Markdown into publication-grade Word (`.docx`) documents matching strict formatting specifications. Designed for academic papers, theses, technical reports, and official publications — **and built as a deterministic Word compilation engine for AI Agents**.

> 🌐 **Try it Online (No Installation Needed)**: [Launch the Web Playground](https://124.220.135.226) to edit live manuscripts, inspect native formulas, three-line tables, running headers, and download publication `.docx` outputs in seconds.

---

### Why md-to-word?

Prompting LLMs to hand-write `python-docx` scripts often leads to formatting hallucinations, table drifts across page breaks, and styling inconsistencies. Tools like Pandoc require wrestling with complex internal XML templates and brittle post-filters for fine adjustments.

`md-to-word` uses a **declarative typographic contract** and **bidirectional quality gates with exact line numbers**:
- **Byte-Identical Reproducibility**: The same Markdown source always yields identical document binaries across different machines.
- **Autonomous Self-Healing**: Missing formats or invalid syntax are caught before writing the file with exact line numbers and guidance, enabling AI Agents to auto-debug and self-heal.
- **Publication-Grade Typography**: Native OMML math formulas (vector, double-click editable, centered with numbering hard right), three-line tables with repeating headers across page breaks, and double/single-rule running headers.

---

## Core Usage Concept

There are **only 2 ways to use this tool across 3 entry points**. Whether via an Agent Skill or pip installation, **the AI Agent must first read the specification document before compiling**:
- **Via Skill**: The AI automatically activates and uses the skill when it recognizes a formatting intent.
- **Via pip**: You explicitly prompt the AI to read the specification before invoking the command.

---

## How to Use: 2 Methods, 3 Entry Points

### Method 1: Use as an Agent Skill (Recommended · Autonomous AI Routing)

#### Entry 1: Install the Skill into Any Agent Supporting the Skills Standard
Works with Claude Code, Codex, Cursor, Windsurf, OpenCode, and general AI agents.

- **Automated CLI Installation (Recommended)**:
  ```bash
  npx skills add ls-open/md-to-word
  ```
  *(Complies with the Agent Skills standard: automatically detects `SKILL.md` in the repository root and mounts it)*

- **Manual Import**:  
  Copy [`SKILL.md`](https://github.com/ls-open/md-to-word/blob/main/SKILL.md) from the repository root into your project's rules or skills directory (e.g. `.claude/skills/` or `.cursor/rules/`), or feed its raw URL directly to conversational agents:  
  `https://raw.githubusercontent.com/ls-open/md-to-word/main/SKILL.md`

- **Natural Language Usage**:  
  No need to memorize CLI flags. Prompt your AI directly:
  > *"Format my manuscript draft (paper.md) into a compliant Word document following IEEE journal standards."*  
  > *"Here are our university thesis formatting requirements (or attached template.docx). Export the draft accordingly."*

#### Entry 2: Direct Use in the Nature Skills Ecosystem
This project is officially integrated as the independent skill [`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word) within **Nature Skills (51k+ ★)**.

- **How to Use**:  
  In an environment with Nature Skills installed, **no extra installation is required**. Simply invoke `$nature-paper2word`, or ask the AI to export the final publication-ready Word file at the end of the writing pipeline.

---

### Method 2: Use via pip Installation (Drive Your Local Agent)

#### Entry 3: Local pip Installation + Prompting the Agent
If you prefer direct Python CLI usage or operate in a local terminal / editor Agent environment:

1. **Install the Compiler**:
   ```bash
   pip install md-to-word-docx
   ```
   *(Note: The PyPI package name is `md-to-word-docx`, while the installed command remains `md-to-word`. Use `pipx install md-to-word-docx` for isolated environments, and update via `pip install -U md-to-word-docx`)*

2. **Core Principle & Prompting AI**:  
   The package includes a comprehensive guide identical to `SKILL.md`. When interacting with an Agent, **prompt it to read the guide first**:

   > 💬 **Standard Prompt Template (Ready to copy):**  
   > "I have installed `md-to-word-docx`. Please first run `md-to-word --guide` to understand its formatting rules and contracts, then help me format the manuscript in this directory into a compliant Word document (if a template Word file is available, run `md-to-word-template` first to deduce formatting requirements)."

3. **Autonomous AI Execution Loop**:
   - **Read specs**: Runs `md-to-word --guide` (or `--contract`) to understand closed vocabulary and Markdown contracts.
   - **Define rules**: Generates or adjusts `format.txt`, or deduces from an existing `.docx` template.
   - **Compile**: Runs `md-to-word manuscript.md -r format.txt -o manuscript.docx --json`.
   - **Self-heal**: If intercepted by preflight gates, fixes issues automatically based on reported line numbers until exit code is `0`.

---

### For Developers and Automated Pipelines (Optional)

If you need to call the engine directly in scripts or CI/CD pipelines:

- **CLI Usage**:
  ```bash
  # Initialize minimal sample
  md-to-word init
  # Compile with specific rule file
  md-to-word manuscript.md -r format.txt -o output.docx
  ```
- **Python API**:
  ```python
  from md_to_word import export

  result = export("manuscript.md", "manuscript.docx", rules="format.txt")
  if not result.ok:
      raise SystemExit("\n".join(result.errors))
  ```

---

## Gallery

Generated through the genuine compilation pipeline; page snapshots rendered from actual PDF exports:

| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png" width="240"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/01_chinese_thesis/thesis_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/01_chinese_thesis/page-1.png" width="240"></a> |
|:--:|:--:|
| **Minimal Quickstart** · Single page, shortest path from draft to Word | **Academic Thesis** · TOC field, sectional pagination, double-rule header |
| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/02_modern_report/report_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/02_modern_report/page-1.png" width="240"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/paper.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/03_english_paper/page-1.png" width="240"></a> |
| **Technical White Paper** · Full grid table, blockquotes, color headings | **English Journal** · APA author-date citation, `Equation 1` cross-refs |

---

## Reverse-Engineered from Existing Word Templates?

No need to transcribe guidelines manually from `.docx` files issued by publishers or universities. Use the built-in deduction tool:

```bash
md-to-word-template university_template.docx -o format.txt
```

It automatically extracts page dimensions, margins, header/footer spacing, pagination, fonts, sizes, line spacing, paragraph before/after spacing, indentations, and table borders into a clean `format.txt`.

---

## Typography Capabilities

- **Page & Prose**: Paper size, margins, gutters, document grid, Chinese/Western fonts, sizes, line spacing, indents, paragraph spacing, alignments, colors.
- **Headings & Headers/Footers**: 6 heading levels, odd/even/first-page distinctions, sectional pagination, `{page}` `{numpages}` `{title}` fields.
- **Tables**: Three-line tables, full grid, top/bottom rules, custom borders, repeating header rows, vertical/horizontal alignment, column width ratios.
- **Equations**: Native OMML equation objects (double-click editable in Word, never bitmapped), centered, right-aligned numbering, chapter numbering, `@eq-` cross-references.
- **Figures & Captions**: Width clamped to body margins, keep-with-next binding to avoid orphan captions, native vector PDF image support (auto-rasterized to 300 dpi on export).
- **Citations & Bibliography**: `.bib` + CSL system with 29 built-in standard styles (GB/T 7714, APA, Nature, IEEE), custom CSL support.
- **Inline Formatting**: Bold, italic, strikethrough, underline, sub/superscript, inline code, inline math, hyperlinks, footnotes.
- **Structure**: Native TOC fields `{{< toc >}}`, section breaks `{{< section >}}`, page breaks `{{< pagebreak >}}`.
- **Quality Gates**: Preflight syntactic and citation validation, post-export integrity checks, granular style accounting.
- **Pure Python**: Fully self-contained pipeline; zero dependency on Microsoft Word, WPS, or Pandoc.

Refer to the [User Manual](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual_en.md) for full boundaries and vocabulary.

---

## Syntax Cheat Sheet

| Element | Syntax | Note |
|:--|:--|:--|
| **Headings** | `# Heading 1`, `## Heading 2` | Each `#` denotes level; do not skip levels |
| **Paragraph Style** | `%% Abstract Text here...` | Prefix line with `%% styleName`; one line per paragraph |
| **Soft Line Break** | End line with `\` or two spaces | For addresses, poems, long titles |
| **Numbered Equation** | `$$E=mc^2$$ {#eq-mass}` | Standalone line; referenced via `@eq-mass` |
| **Citation** | `[@smith2024]` | Declare `bibliography: refs.bib` in YAML |
| **Figure & Caption** | `![](figures/arch.png){width=13cm}`<br>`%% Figure Caption Fig. 1 Architecture` | Placed on consecutive lines; bound together |
| **Table & Caption** | Before table: `%% Table Caption **Table 1** Benchmark`<br>`\| A \| B \|`<br>After: `%% Table Note Note: ...` | Standard Markdown table with automatic rule borders |
| **TOC Field** | Standalone `{{< toc >}}` | Generates native Word TOC field |
| **Section & Paging** | `{{< section page_number=lowerRoman start=1 >}}` | Breaks section and restarts page numbering |
| **Page Break** | Standalone `{{< pagebreak >}}` | Inserts page break |

---

## Ecosystem & Listed In

Focused on deterministic downstream compilation and publication delivery. Recommended to pair with upstream research frameworks:

- **[Nature Skills](https://github.com/Yuan1z0825/nature-skills) (51k+ ★)**: Top-tier academic research and writing agent toolkit. Officially integrated as [`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word) to deliver publication-compliant Word documents in the final stage.
- **[Academic Research Skills](https://github.com/Imbad0202/academic-research-skills) (51k+ ★)**: 5-stage research framework. Listed in the official ecosystem, directly compiling Stage 5 (FINALIZE) Markdown and `.bib` outputs into Word.
- **[Chinese Independent Developer](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)**: Featured in the developer showcase.

---

## License

MIT License. See [LICENSE](https://github.com/ls-open/md-to-word/blob/main/LICENSE) for details.  
Built-in citation styles are from [citation-style-language/styles](https://github.com/citation-style-language/styles) (CC BY-SA 3.0). Built-in modern base template generated by this project under MIT.
