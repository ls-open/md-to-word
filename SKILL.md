---
name: md-to-word
description: "Compile a Markdown manuscript into journal- or school-compliant Word (.docx): declared typography, native OMML equations, three-line tables, cross-references, page-number sections, CSL bibliographies, and pre/post-export quality gates — no Pandoc, no Quarto. 把 Markdown 导出为符合规范的 Word：学位论文/期刊论文/公文排版，摘要、公式编号、三线表、题注、交叉引用、目录域、CSL 参考文献。Use when the user wants a .docx — a readable copy or a compliant submission — including 导出Word、文档转Word、论文转Word、期刊排版、公文排版、prepare submission docx. Not for PDF, HTML or LaTeX output."
license: MIT
---

# Markdown → compliant Word

This file is the router. The engine is deterministic: the same manuscript and the same format
requirements always produce a byte-identical `.docx`. Do not substitute a hand-written
python-docx script; run the bundled pipeline.

**The full vocabulary lives in the manual inside the package**, not here:

```
src/md_to_word/resources/manual.md      # Chinese
src/md_to_word/resources/manual_en.md   # English
```

`md-to-word --contract` prints the path for the current language. Everything below is order of
work; every spelling is looked up in the manual.

## 1. Decide the scenario first

| Scenario | What the user says | What to do |
|---|---|---|
| Journal or school compliance | "format it for Nature / my university" | Get a target `.docx` template or a written spec, then build a requirements file. |
| Existing requirements | "use our lab's spec file" | Pass it with `-r`. |
| Baseline export (no explicit spec) | "turn this into a Word file" | Normalize the manuscript to the contract, then export with the built-in preset. The preset is a complete, valid format, not a provisional default. |

State the chosen preset or requirements path in one line, then proceed. Without `-r` the preset
follows the **manuscript's language**: `zh-academic` for Chinese, `en-nature` for everything else.
The run reports which one it used.

No path accepts arbitrary Markdown and returns a finished document: a preset supplies formatting,
not missing structure. When the manuscript violates the contract, pre-flight stops with a line
number rather than emitting a document that looks acceptable while its formatting was never mapped.

## 2. Bring the manuscript to the input contract

The source may be pasted text, `.txt`, `.md`, an old `.docx`, or a PDF. Normalize it to Markdown
first; never edit the user's original file in place.

- **Headings**: `#`, `##`, `###`, consecutive and unskipped; a heading that carries its own number
  (`1.`, `2.1`) needs as many `#` as its number has levels.
- **Paragraph styles**: a line starting with `%% ` sets that paragraph's style —
  `%% Abstract …`, `%% Table Caption **Table 1** …`, `%% Image Caption Figure 1 …`.
  One line is one paragraph, ended by a blank line, with no closing fence. Style names come from a
  closed list (manual §3.4) in either language; heading levels are set by `#` only.
- **Title, author, abstract, keywords** are style lines in the body, never YAML — their position on
  the page is the author's decision, and YAML has no position. Pre-flight blocks those keys with the
  exact line to write instead.
- **YAML holds only position-independent configuration**: `bibliography:`, `csl:`, `crossref:`,
  `link-citations:`.
- **Equations**: `$$...$$ {#eq-name}` on its own line, referenced as `@eq-name`. Chinese manuscripts
  get 「式/图/表」 prefixes and （1）numbering, English ones get Equation/Figure/Table and (1). Add
  `crossref: chapters: true` for per-chapter numbering. `\tag{}` is blocked.
- **Citations**: `[@key]` parenthetical, `@key` narrative, from `bibliography:` + `csl:`. A `.bib` is
  mandatory once the manuscript cites: handwritten reference lists are not supported, and `[@key]`
  without `bibliography:` would be printed literally.
- **Figures and tables**: `![](path/img.png){width=13cm}` with the caption in its own
  `%% Image Caption` / `%% 图片题注` paragraph; table caption above, note below. Do not put
  `{#fig-...}` labels on images. Column widths follow the separator row's dash lengths.
- **Block markers** (three, each on its own line with blank lines around): `{{< pagebreak >}}`,
  `{{< toc >}}`, `{{< section page_number=lowerRoman start=1 >}}` (Chinese parameters `页码=` `起始=`
  also work). The section marker closes *the section above it*; never add a page break next to it.
- **Unsupported Markdown is blocked with a replacement**, never printed literally: HTML tags, `---`
  rules, `====` headings, definition lists, `- [ ]` boxes, tables without outer pipes, nested block
  quotes, full-width `％％`, four-space code blocks, `**` across lines, and a second paragraph inside
  a list item.

## 3. Choose or build the format requirements

1. **Built-in preset** — `zh-academic` or `en-nature`. Use as-is when the user gave no detailed spec.
2. **Copy and edit a preset** — change only the lines the user mentioned. Field order is fixed:
   font, size, bold, italic, alignment, line spacing, space before, space after, indent. Every style
   line must be complete; missing fields are errors.
3. **Reverse-engineer a target `.docx`** — `python3 <skill-dir>/scripts/read_reference_docx.py
   target.docx -o requirements.txt`, then review the "to confirm" list at the end of the draft.

Each property has exactly one accepted spelling (two in total: the canonical Chinese and English
forms); anything else is a hard error with a line number. Full table: manual §3.1. Style names:
§3.4. Presets are the reference examples, at `src/md_to_word/presets/`.

Citation style comes from `csl:` with a bundled file name (manual §7) or a path to the user's own
CSL. Without `csl:`, Chinese manuscripts get GB/T 7714 numeric, others APA 7th. A user-supplied CSL
is normalized on export so that one requirements file always produces one layout.

## 4. Export

Run from the manuscript's directory, pointing at the script in the skill directory (inside the
repository that is simply `bash scripts/export.sh …`):

```bash
bash <skill-dir>/scripts/export.sh manuscript.md -o manuscript.docx
bash <skill-dir>/scripts/export.sh manuscript.md -r requirements.txt -o manuscript.docx
bash <skill-dir>/scripts/export.sh --contract          # contract + paths to the manual and presets
bash <skill-dir>/scripts/export.sh --version           # engine version
```

If the package is installed instead, the same commands exist as `md-to-word …`.

The pipeline runs: pre-flight validation → style template generation → manuscript model → OOXML
writing → number-integrity check → line-by-line audit against the requirements file.

## 5. How to read the gates

Two levels, split by "would the mistake be visible afterwards":

- **Blocking** — silently wrong later: dropped content, syntax printed literally, formatting never
  mapped, a title in YAML, a caption inside an image's brackets. Fix the reported line; do not reach
  for `--no-check`, which turns off the blocking gates too.
- **Warning** — visible but non-compliant: an image wider than the text block (it gets clamped), a
  caption far from its figure, a skipped heading level, a page break after a section marker.

Exit codes: `0` every gate passed; `1` manuscript, gate or dependency problem; `3` the `.docx` was
written but the optional `--pdf` proof was skipped (non-macOS). Messages follow the manuscript's
language. Add `--verbose` when a format does not seem to take effect.

## 6. Verify before delivery

- Confirm the `.docx` exists and the command exited `0`.
- Report the applied preset or requirements file, the citation style, and anything the run warned
  about.
- Say plainly that the layout still needs a look in Word: table heights and column widths are
  content-driven, and equations, captions and headers only settle in the real renderer.
- When the document has a TOC, `{style-title}` headers or per-section page numbers, run once with
  `--pdf` (macOS with Word) — that is the only way fields are expanded — and spot-check the first
  page, the widest table, an equation-heavy page and the references.

## 7. Boundaries

- No custom cover pages, merged cells, multi-column text, inline text colour, or text-wrapped
  figures. Export the body, then complete those in Word.
- Only equation cross-references are supported (`{#eq-x}` + `@eq-x`); figure and table numbers are
  typed into the caption.
- Sum and integral limits stay on the right of the symbol in numbered equations (Word stacks limits
  only in display math). Content and symbols are correct; only the arrangement differs.
- TOC page numbers and chapter headers are Word fields; Word asks once whether to update them.
- Runtime: Python 3.9+ and five pure-Python packages (`pip install -r requirements.txt` when running
  from this directory). No Quarto, no Pandoc, no external binary; `--pdf` additionally needs Word on
  macOS and is skipped elsewhere.

Full statements: manual §6 (limits) and §8 (symptom → fix). Design rationale: `references/design.md`.

## 8. Related skills

This skill compiles the manuscript; these cover the steps around it. Hand off rather than
re-implement:

| Skill | What it covers |
|---|---|
| `nature-writing` | Drafting the manuscript and its section-level argument (input to this one) |
| `nature-polishing` | Language polishing and academic phrasing (input to this one) |
| `nature-citation` | Searching for and exporting BibTeX / RIS entries for the `.bib` this skill consumes |
| `nature-ref-verifier` | Cross-checking reference metadata before submission |
| `nature-paper2ppt` | Turning the same manuscript into a presentation deck |

Upstream engine, the general-purpose pip package, and the changelog:
[md-to-word](https://github.com/ls-open/md-to-word).
