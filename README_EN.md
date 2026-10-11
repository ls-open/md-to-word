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

## 🔍 Comparison: the same result, and what each tool needs to get there

Ground rules: every tool is judged on its **default output** (no custom template, no filter). ⚠️ = possible, but you hand-edit the base template, set it paragraph-by-paragraph and table-by-table, or write XML yourself; ✅ = comes out of the box; ❌ = not available by default. **The last column is what this skill actually asks you to write.**

| Typesetting element | Native Pandoc default | Quarto default Word | Manual Word tuning | 🌟 md-to-word: write this |
|:---|:---:|:---:|:---:|:---|
| **Chinese document basics** | | | | |
| Separate CJK and Latin fonts (SimSun + Times New Roman) | ⚠️ Edit base template | ⚠️ Edit base template | ⚠️ Per paragraph | `正文：宋体/Times New Roman 小四 …` |
| Chinese font sizes + 2-character first-line indent | ❌ | ❌ | ⚠️ Per paragraph | `… 首行缩进2字符` |
| Document proofing language (CJK text not flagged) | ❌ | ❌ | ⚠️ Set manually | `校对语言：zh-CN` |
| **Academic typesetting** | | | | |
| Three-line tables with adjustable rules | ⚠️ Edit base template | ⚠️ Edit base template | ⚠️ Per table | `表格：居中 三线表 线宽上1.5磅 线宽表头下0.75磅` |
| Header row repeats across pages | ✅ On by default | ✅ On by default | ⚠️ Per table, tick a box | `表头：… 跨页重复` |
| Centered display math, equation number hard right | ❌ Number not right-aligned | ⚠️ Number trails the equation | ⚠️ Manual 3-column tab stops | `$$…$$ {#eq-x}` handles both |
| Dynamic chapter-name header (double rule) | ❌ Edit template + insert field | ❌ Edit template + insert field | ⚠️ Break sections + insert field | `页眉内容：{样式标题:Heading 1}` |
| Roman front matter / Arabic body pagination | ❌ | ❌ | ⚠️ Insert section break by hand | `{{< section 页码=小写罗马 起始=1 >}}` |
| Native dynamic table of contents | ⚠️ A real field, but styling needs the base template | ⚠️ A real field, but styling needs the base template | ⚠️ Insert field by hand | `{{< toc 2 >}}` + 4 style lines |
| Figure/equation cross-references with CJK prefixes | ❌ | ✅ | ❌ | Three `crossref:` lines in YAML |
| Formatted bibliography (GB/T 7714, APA, …) | ✅ citeproc | ✅ citeproc | ❌ | `csl: apa.csl` + `[@key]` in prose |
| **Built for AI and automation** | | | | |
| Layout rules declared in text, reviewable in Git | ❌ Buried in XML and manual steps | ❌ | ❌ | One `requirements.txt` states it all |
| Failure mode: error, or silent drift? | ⚠️ Mostly silent | ⚠️ Mostly silent | ❌ Eyes only | Pre-flight check, reported by line number |
| Quality gates before delivery | ❌ | ❌ | ❌ | Three: pre-flight / number diff / item-by-item audit |

> The ✅ marks under Pandoc and Quarto are **honest** — repeating header rows and citeproc bibliographies, for instance, do come out of the box. The value here isn't that others *can't*; it's that a single `requirements.txt` settles **all of it at once**, with no base-template surgery, no XML, and no per-paragraph clicking.

---

## 📸 Typesetting Showcase (Self-Documenting Demos)

The two built-in showcase demos are written directly about md-to-word's engineering principles and benchmarks, demonstrating real-world formatting performance:

### Showcase 1: Academic Thesis & Journal Paper (Full Elements)
> Independent lowercase Roman front-matter page numbers (`i, ii`), native dynamic TOC, dual-line chapter headers, three-line tables with repeating headers, centered equations with right-aligned numbering, and GB/T 7714-2015 numeric citations.

📁 Source, formatting rules and one-command reproduction → **[demo/01_chinese_thesis](demo/01_chinese_thesis/README.md)**

| Title & Abstract (Centered Title / No Header) | Dynamic TOC (Dot Leaders / Roman Page Numbers) | Dynamic Chapter Header & Architecture Chart |
| :---: | :---: | :---: |
| ![Thesis Title](demo/01_chinese_thesis/page-1.png) | ![Thesis TOC](demo/01_chinese_thesis/page-2.png) | ![Figures and Text](demo/01_chinese_thesis/page-3.png) |

| Centered Math Equations & Convergence Chart | Three-Line Academic Table & GB/T 7714 References |
| :---: | :---: |
| ![Math and Convergence](demo/01_chinese_thesis/page-4.png) | ![Table and Bibliography](demo/01_chinese_thesis/page-5.png) |

---

### Showcase 2: Modern Enterprise Whitepaper & Research Report
> Flat single-section structure, executive summary, sleek single-line header, full-grid data tables, and APA 7th author-date citation style.

📁 Source, formatting rules and one-command reproduction → **[demo/02_modern_report](demo/02_modern_report/README.md)**

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
| [`SKILL.md`](SKILL.md) | **Must-read for AI Agents**: Agent automation workflows, Markdown syntax contracts, and best practices. |
| [`references/reference.md`](references/reference.md) | **Advanced Customization**: Complete vocabulary for `requirements.txt`, default inference rules, and built-in CSL list. |
| [`references/design.md`](references/design.md) | **Developers & Hackers**: In-depth architecture, pure Word 365 base template, 3-column equation alignment, and OpenXML internals. |

---

## 📄 License

Open-sourced under the [MIT License](LICENSE). Contributions and feedback are welcome!
