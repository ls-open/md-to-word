# md-to-word: Compliant Word (.docx) Typesetting Skill for AI Agents & Markdown

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

## 🔍 Objective Comparison with Mainstream Tools

| Feature & Capability | Native Pandoc CLI | Quarto (Default Word) | Markdown Editors (Typora, etc.) | Manual Word Tuning | 🌟 md-to-word Automated Solution |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Git Line-by-Line Diff & Merge** | Supported | Supported | Supported | ❌ **Binary file; corrupts on merge** | ** Native Git diff support** |
| **Dynamic Chapter Headers** | ❌ Unsupported | ❌ Unsupported | ❌ Unsupported | ⚠️ Supported (manual per section) | ** Native `STYLEREF` tracking** |
| **Independent Roman/Arabic Pagination** | ❌ Requires manual XML hacking | ❌ Unsupported | ❌ Unsupported | ⚠️ Supported (manual break) | ** Declarative independent sections** |
| **Academic Three-Line Tables** | ❌ Plain black grid only | ⚠️ Needs manual template | ❌ Plain black grid | ⚠️ Supported (manual borders) | ** Configurable; auto-repeating headers** |
| **Grid Tables (Inner/Outer Borders)** | ⚠️ Basic grid | ⚠️ Basic grid | ⚠️ Basic grid | ⚠️ Supported (manual widths) | ** Precise border width controls** |
| **Centered Math with Right-Aligned No.** | ❌ Number breaks onto new line | ⚠️ Basic support | ❌ Uncontrollable | ⚠️ Supported (manual tab stops) | ** 3-column borderless alignment** |
| **Native Dynamic Table of Contents** | ❌ Static text without page numbers | ❌ Static text list | ❌ Static text list | ⚠️ Supported (manual field) | ** Native TOC field with dot leaders** |
| **Quality & Number Audit Gates** | ❌ No validation | ❌ No validation | ❌ No validation | ❌ **Manual checks; error-prone** | ** 3 deterministic audit gates** |

---

## 📸 Typesetting Showcase (Self-Documenting Demos)

The two built-in showcase demos are written directly about md-to-word's engineering principles and benchmarks, demonstrating real-world formatting performance:

### Showcase 1: Academic Thesis & Journal Paper (Full Elements)
> Independent lowercase Roman front-matter page numbers (`i, ii`), native dynamic TOC, dual-line chapter headers, three-line tables with repeating headers, centered equations with right-aligned numbering, and GB/T 7714-2015 numeric citations.

| Title & Abstract (Centered Title / No Header) | Dynamic TOC (Dot Leaders / Roman Page Numbers) | Dynamic Chapter Header & Architecture Chart |
| :---: | :---: | :---: |
| ![Thesis Title](demo/01_chinese_thesis/page-1.png) | ![Thesis TOC](demo/01_chinese_thesis/page-2.png) | ![Figures and Text](demo/01_chinese_thesis/page-3.png) |

| Centered Math Equations & Convergence Chart | Three-Line Academic Table & GB/T 7714 References |
| :---: | :---: |
| ![Math and Convergence](demo/01_chinese_thesis/page-4.png) | ![Table and Bibliography](demo/01_chinese_thesis/page-5.png) |

---

### Showcase 2: Modern Enterprise Whitepaper & Research Report
> Flat single-section structure, executive summary, sleek single-line header, full-grid data tables, and APA 7th author-date citation style.

| Executive Summary & Section 1 | Efficiency Model & Benchmark Chart | Full-Grid Data Table & APA References |
| :---: | :---: | :---: |
| ![Report Front](demo/02_modern_report/page-1.png) | ![Benchmark](demo/02_modern_report/page-2.png) | ![Grid Table and References](demo/02_modern_report/page-3.png) |

---

## 🚀 Effortless Usage: AI Agent Full Automation (Recommended ✨)

Designed as a specialized skill for AI coding assistants (Claude Code, Cursor, Antigravity, etc.), **you do not need to memorize or run command lines**:

1. **Install — let your AI assistant do it**: just paste the line below into your assistant. Every assistant keeps skills somewhere different, and so does every OS — **let the assistant work that out for itself**:

   > Install this skill for me: https://github.com/ls18166407597-design/md-to-word
   > Clone it into your skills directory, then read SKILL.md and tell me what it can do and how it is triggered.

2. **Natural Language Request**: Provide your Markdown draft and describe your target format:
   > *"Export this Markdown document to Word (.docx) according to my university's master's thesis (or target journal) formatting guidelines."*
3. **Closed-Loop Autonomous Delivery**:
   - The AI identifies margins, font styles, line spacing, and table requirements;
   - Compiles a compliant temporary template and cleanses OOXML attributes;
   - Executes deterministic audit gates (precision numbers and XML styles);
   - Delivers the final validated `.docx` file directly to you.

> 💡 **For CI/CD Pipelines**: Developers can also invoke the CLI directly:  
> `bash scripts/export.sh input.md [-r requirements.txt] -o output.docx`

---

## 📚 FAQ: What is a BibTeX (.bib) File and How to Get It?

For users unfamiliar with academic bibliography workflows:

* **What is `.bib`?**  
  `.bib` (BibTeX) is the global standard plain-text format for structured reference databases. Each entry includes publication type, authors, title, journal, volume, and year.
* **How to Obtain It? (No Manual Coding Required)**:
  1. **One-Click Web Export (Google Scholar, CNKI, Baidu Scholar)**:  
     Search for the paper $\to$ click the **"Cite"** button $\to$ select **"BibTeX"** $\to$ copy the text into `references.bib`.
  2. **Batch Export from Reference Managers (Zotero, EndNote, Mendeley)**:  
     Select papers in your library $\to$ right click **"Export Library / Items"** $\to$ choose **BibTeX** format.
* **How to Cite in Markdown?**  
  Simply write `[@citekey]` (e.g., `[@vaswani2017]`) in your prose. The compiler will automatically format in-text citations and generate the end-of-document bibliography according to your chosen CSL style (e.g., `chinese-gb7714-2015-numeric.csl` or `apa.csl`).

---

## 🛠️ Environment Prerequisites

Running this skill requires only two lightweight prerequisites:

1. **Python Dependencies** (Python 3.9+):
   ```bash
   pip install -r requirements.txt
   ```
2. **Quarto Engine** (Quarto $\ge 1.4$, includes Pandoc):
   ```bash
   # macOS
   brew install quarto

   # Linux / Windows: Download installer from https://quarto.org/docs/get-started/
   ```

---

## 📖 Skill Routing & Documentation

| Path | Purpose & Target Audience |
| :--- | :--- |
| [`SKILL.md`](SKILL.md) | **Must-read for AI Agents**: Agent automation workflows, Markdown syntax contracts, and best practices. |
| [`references/reference.md`](references/reference.md) | **Advanced Customization**: Complete vocabulary for `requirements.txt`, default inference rules, and built-in CSL list. |
| [`references/design.md`](references/design.md) | **Developers & Hackers**: In-depth architecture, pure Word 365 base template, 3-column equation alignment, and OpenXML internals. |

---

## 📄 License

Open-sourced under the [MIT License](LICENSE). Contributions and feedback are welcome!
