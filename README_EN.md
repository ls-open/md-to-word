# md-to-word

[![Official Skill: Nature Skills](https://img.shields.io/badge/Official%20Skill-Nature%20Skills%20(51k+%E2%98%85)-d9381e?logo=github&logoColor=white)](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)

English | [简体中文](https://github.com/ls-open/md-to-word/blob/main/README.md) | [🌐 Web Playground (No-Install Demo)](http://124.220.135.226)

Compile Markdown into a Word (`.docx`) document that matches a declared format. Designed for academic papers, theses, technical reports, and official documents — **and built as a deterministic Word compilation engine for AI Agents**.

Prompting LLMs to hand-write `python-docx` scripts often leads to formatting hallucinations, table drifts across page breaks, and styling inconsistencies. `md-to-word` uses strict contracts, declarative format files, and pre-export quality gates with exact line numbers. The same source always produces a byte-identical document on every run. Any missing formatting or invalid syntax stops the export before writing a file and reports the exact line number, enabling AI Agents to achieve true self-healing document compilation.

[![Output of the English demo](https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/03_english_paper/page-1.png)](https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/paper.docx)

*Exported from [`demo/03_english_paper`](https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/): APA author-date citations from a `.bib`, a centred equation with its number set hard right, a three-line table with note above and below the rule — nothing was clicked in Word.*

---

> 💡 **Core Usage Concept**  
> In essence, there are **only 2 ways to use this tool across 3 entry points**. Whether via an Agent Skill or pip installation, **the AI Agent must first read the specification document before compiling**:
> - **Via Skill**: The AI automatically activates and uses the skill when it recognizes a formatting intent.
> - **Via pip**: You explicitly prompt the AI to read the specification before invoking the command.

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

- **How to Use (Natural Language)**:  
  No need to memorize CLI flags. Prompt your AI directly:
  > *"Format my manuscript draft (paper.md) into a compliant Word document following IEEE journal standards."*  
  > *"Here are our university thesis formatting requirements (or attached template.docx). Export the draft accordingly."*

#### Entry 2: Direct Use in the Nature Skills Ecosystem
This project is officially integrated as the independent skill [`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word) within **Nature Skills (51k+ ★)**.

- **How to Use**:  
  In an environment with Nature Skills installed, **no extra installation is required**. Simply invoke `$nature-paper2word`, or ask the AI to export the final publication-ready Word file at the end of the writing pipeline.

---

### Method 2: Use via pip Installation (Drive Your Local Agent)

#### Entry 3: Local pip Install + Prompting Your Local Agent
If you prefer running via local Python tools, or are using local agentic coding assistants (Cursor Agent, Claude Code, terminal AI):

1. **Install the compiler engine**:
   ```bash
   pip install md-to-word-docx
   ```
   *(Note: The PyPI distribution carries a `-docx` suffix to avoid name collisions; the installed command is `md-to-word`. In isolated environments use `pipx install md-to-word-docx`; upgrade via `pip install -U md-to-word-docx`)*

2. **Core Mechanism & Prompting the AI**:  
   The package bundles a complete guide identical to `SKILL.md`. When interacting with an Agent, **the key is to direct the AI to read the guide first**:

   > 💬 **Standard Prompt for Agents (Copy & Paste):**  
   > "I have installed the `md-to-word-docx` CLI tool. Please run `md-to-word --guide` first to read the typography specifications and input contracts, then export the manuscript in this directory to a compliant Word document (if an existing target `.docx` template is available, run `md-to-word-template` first to reverse-engineer the formatting rules)."

3. **Autonomous Loop Executed by the Agent**:
   - **Reads Specs**: Runs `md-to-word --guide` (or `--contract`) to learn the vocabulary and markdown contracts;
   - **Defines Typography**: Generates `format.txt` or extracts rules from an existing `.docx` template;
   - **Compiles**: Runs `md-to-word manuscript.md -r format.txt -o manuscript.docx --json`;
   - **Self-Healing on Errors**: If quality gates block compilation, the agent inspects the exact line numbers reported, fixes the manuscript, and re-exports until exit code `0`.

---

### For Developers & Automated Pipelines (Optional)

If you need direct programmatic or script-based invocation:

- **Run directly via CLI**:
  ```bash
  # Initialize minimal demo
  md-to-word init
  # Export with format specification
  md-to-word manuscript.md -r format.txt -o manuscript.docx
  ```
- **Call via Python API**:
  ```python
  from md_to_word import export

  result = export("manuscript.md", "manuscript.docx", rules="format.txt")
  if not result.ok:
      raise SystemExit("\n".join(result.errors))
  ```

---

## Samples

All samples below are produced by real compilation runs and rendered from exported PDFs (not mockups):

| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png" width="250"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/01_chinese_thesis/thesis_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/01_chinese_thesis/page-1.png" width="250"></a> |
|:--:|:--:|
| **Minimal Demo** · One page, shortest path from draft to final document | **Chinese University Thesis** · TOC field, per-section page numbers, chapter-numbered equations, double-line headers |
| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/02_modern_report/report_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/02_modern_report/page-1.png" width="250"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/paper.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/03_english_paper/page-1.png" width="250"></a> |
| **White Paper / Report** · Grid tables, blockquotes, colored level-1 headings | **English Journal Paper** · APA author-date system, `Equation 1` cross-references |

---

## Have an Existing Word Template?

Target `.docx` templates issued by schools or journals do not need to be manually transcribed rule-by-rule. Use the built-in extractor:

```bash
md-to-word-template target_template.docx -o format.txt
```

The extractor automatically infers paper dimensions, margins, header/footer offsets, page number formatting, font families, font sizes, weights, line spacing, paragraph spacing, indents, table borders, and header repetition. **Items that cannot be determined with full confidence are listed in a "to-confirm" checklist** rather than guessed.

---

## Capabilities Overview

- **Page & Body Typography**: Paper size, margins, gutter, grid alignment, multi-language fonts, font sizes, line spacing, indentation, paragraph spacing, alignments, colors.
- **Headings & Headers/Footers**: 6 heading levels, different first page, odd/even page headers, multi-sectioning, page numbering formats, `{Page}`, `{TotalPages}`, and `{StyleHeading}` fields.
- **Tables**: Three-line tables, full grid lines, top/bottom borders, borderless tables, line weights, repeating table headers across page breaks, vertical & horizontal cell alignments, relative column widths.
- **Equations**: Native OMML equation objects (editable in Word, never rasterized images or literal code), centered, right-aligned numbering, per-chapter numbering, `@eq-` cross-referencing.
- **Figures & Captions**: Image widths clamped to printable page width, keep-with-next caption binding to avoid orphans, native support for vector PDF figures (automatically rasterized at 300 dpi on export).
- **Bibliographies**: `.bib` + CSL engine, 29 built-in styles (APA, Nature, IEEE, GB/T 7714, Vancouver, etc.), support for custom CSL files.
- **Inline Formatting**: Bold, italic, strikethrough, underline, superscript, subscript, code, inline math, links, footnotes.
- **Structural Markers**: TOC field `{{< toc >}}`, section breaks with restarted page numbers `{{< section >}}`, page breaks `{{< pagebreak >}}`.
- **Quality Gates**: Pre-flight verification (contract, style names, citation database existence), post-export count checks, line-by-line reconciliation.
- **Pure Python Local Export**: Pipeline runs entirely inside Python; no background Office, WPS, or Pandoc processes required.

See the [Manual](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual_en.md) for full vocabulary and constraints.

---

## Common Syntax Cheat Sheet

| Element | Syntax | Description |
|:--|:--|:--|
| **Headings** | `# Introduction`, `## 2.1 Methods` | One `#` per level; consecutive and unskipped |
| **Paragraph Style** | `%% Abstract This study presents...` | Paragraph begins with `%% StyleName`; one line is one paragraph |
| **Soft Break** | End line with `\` or two spaces | Line break within the same paragraph |
| **Numbered Equation** | `$$E=mc^2$$ {#eq-mass}` | On its own line; cross-referenced with `@eq-mass` |
| **Citations** | `[@smith2024]` or `@smith2024` | Declare `bibliography: refs.bib` in YAML |
| **Figures & Captions** | `![](figures/arch.png){width=13cm}`<br>`%% Image Caption Figure 1 System Architecture` | Caption immediately follows image; bound to same page |
| **Tables & Captions** | Above: `%% Table Caption **Table 1** Benchmark`<br>`\| A \| B \|`<br>Below: `%% Table Note Note: ...` | Standard markdown table; automatic rules & header repeat |
| **TOC Field** | Standalone line `{{< toc >}}` | Emits a native Word TOC field |
| **Section Break** | `{{< section page_number=lowerRoman start=1 >}}` | Closes previous section, begins new section with restarted page number |
| **Page Break** | Standalone line `{{< pagebreak >}}` | Inserts a hard page break |

---

## Comparison with Other Solutions

| Dimension | Pandoc / Quarto | Typical Markdown→Word Libraries | md-to-word |
|:--|:--|:--|:--|
| **Rule Declaration** | CLI arguments + reference `.docx`; modifying details requires editing OOXML | Hardcoded in Python scripts, or limited to few presets | Plain-text `format.txt` alongside manuscript; tracked in Git |
| **Equations** | Requires extra post-processing scripts for right-aligned numbers | Often converted to images or plain text | Native OMML equation objects, centered with right-aligned numbering |
| **Sections & Headers** | Requires manual template editing and field insertion | Generally unsupported | Direct declarative syntax (e.g. Roman numerals in front matter, Arabic in body) |
| **Error Handling** | Silent formatting bugs or broken layouts | Python exceptions or silent errors | Strict pre-flight gates reporting **exact line numbers** |
| **AI Agent Friendliness**| Difficult to control formatting via prompts | Generates hallucinated and inconsistent scripts | **Designed for Agents**: Read Guide -> Call CLI -> Self-Heal on line errors |

---

## Ecosystem & Recommendations

This project focuses on downstream deterministic compilation and publication delivery. For upstream topic selection, literature review, and academic drafting, we recommend pairing with:

- **[Nature Skills](https://github.com/Yuan1z0825/nature-skills) (51k+ ★)**: Top-tier academic writing agent skill suite. This project is officially merged as the built-in skill [`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word), powering the final compliant Word compilation stage. Invoke with `$nature-paper2word` within Nature Skills.
- **[Academic Research Skills](https://github.com/Imbad0202/academic-research-skills) (51k+ ★)**: A 5-stage academic research and writing framework. Listed in the official third-party catalog to handle Stage 5 (FINALIZE) docx compilation.
- **[Chinese Independent Developers](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)**: Featured in the programmer edition of curated independent projects.

---

## License

Source code is released under the [MIT License](https://github.com/ls-open/md-to-word/blob/main/LICENSE).  
Built-in citation styles are from [citation-style-language/styles](https://github.com/citation-style-language/styles) (CC BY-SA 3.0); base document template is generated by this project and released under MIT.
