# Markdown → compliant Word

Turns a Markdown manuscript into a `.docx` whose typography comes from a declared format file. The
engine is deterministic — the same manuscript and the same declarations produce a byte-identical
file on every run — so do not substitute a hand-written python-docx script; run this pipeline.

**Read this before the first run.** Check the engine with `md-to-word --version`; if it is missing,
install it with `pip install md-to-word-docx`. Flags alone are not enough: the manuscript has a
contract (§2) and the format file a closed vocabulary (§3), neither guessable from `--help`.

**This file is the order of work; the facts live in the manual.** `md-to-word --contract` prints the
manual's path (following the manuscript's language), the built-in preset paths and a one-screen
summary; `--contract --json` returns the same facts as one object (version, preset paths and
`sha256`, style names, exit codes, the exact `--json` keys). A spelling outside the vocabulary is a
hard error with a line number: read the manual rather than guess. The manual's §9 is the thesis
part. An identical copy of this file ships as `guide.md` (`md-to-word --guide --lang en`); one copy
is enough — without `--lang en`, `--guide` prints the shorter Chinese quickstart for human readers.

## 1. The work, in order

Before editing files, understand how **three inputs combine** to produce the final `.docx`:

| Layer | File | What it controls |
|:--|:--|:--|
| **Content & inline** | Manuscript `.md` | Text, headings (`#`), structure (`%% Style`, `{{< toc >}}`, `{{< section >}}`, `$$…$$ {#eq-}`), YAML (`bibliography:`, `csl:`, `crossref:`), and **inline span formatting** (`**bold**`, `*italic*`, `~~strike~~`, `[text]{.underline}`, `^sup^`, `~sub~`, `` `code` ``, `[text](url)`). |
| **Format & page** | `format.txt` or `--preset` | Global page geometry (`Paper`, `Margins`, `Gutter`, `Mirror Margins`), language/punctuation (`Proofing Language`, `Punctuation Compression`), running header/footer content (`{page}`, `{total-pages}`, `{style-title:Heading 1}`), and **style-level** typography (`Body Text`, `Heading 1`, `Table`, style `color#RRGGBB`, etc.). |
| **Cover / base** *(optional)* | `--base-template x.docx` | Keeps an institutional cover/declaration `.docx` verbatim in leading sections (`--keep-until` / `--cover-sections` / `--keep-pages`). Note: the base's document settings (`settings.xml`, theme, `docDefaults`) apply globally; your declared styles and body page/margin/header rules come from `format.txt`. |

Workflow:

1. **Confirm requirements & decide format** (§3): choose a built-in preset (`zh-academic` / `zh-tw-academic` / `zh-report` / `zh-gb9704` / `en-nature` / `en-apa-student`), edit a copy of one, use the user's `format.txt`, or extract one from a reference `.docx`.
2. **Normalize the manuscript**: map structures beyond standard Markdown (title/abstract lines, captions, TOC, page breaks, section breaks, numbered equations) using the contract in §2, and keep inline emphasis/super/sub/code/links directly in Markdown. Write a new file; never overwrite the user's source if adapting one.
3. **Export** (§4), adding `--base-template` only when an existing `.docx` cover/front-matter template must be preserved untouched.
4. **Read the gates** (§4), fix reported line numbers, and re-run until exit code is `0`.
5. **Report** (§5): state the format/preset/CSL used, relay any warnings, and note that visual layout still needs a check in Word.

Nothing here accepts arbitrary Markdown and returns a finished document: a preset supplies
formatting, not missing structure. Pre-flight stops with a line number instead of emitting a
document that looks acceptable while its formatting was never mapped.

## 2. The manuscript contract

**Headings** — `#`, `##`, `###`, consecutive and unskipped; a heading that carries its own number
(`1.`, `2.1`) needs as many `#` as its number has levels. Heading levels are set by `#` only.
Append `{.unlisted}` (or `{不入目录}`) to opt a single heading out of the TOC while keeping `#`
hierarchy and chapter equation numbering (it will not update `{style-title:Heading 1}` headers
unless separated by `{{< section >}}`).

**Style lines** — a line starting with `%% ` sets that paragraph's style. One line is one paragraph,
ended by a blank line, no closing fence. Names come from a closed list, valid in either language;
these are the ones that come up in almost every document:

| Style line | Sets |
|---|---|
| `%% Title …` / `%% 文档标题 …` | the document title |
| `%% Author …` / `%% 作者 …` | author line |
| `%% Abstract Title …` / `%% 摘要标题 …` | the "Abstract" heading |
| `%% Abstract …` / `%% 摘要 …` | abstract body |
| `%% Keywords …` / `%% 关键词 …` | keywords |
| `%% Table Caption …` / `%% 表题 …` | caption above a table |
| `%% Table Note …` / `%% 表注 …` | note below a table |
| `%% Image Caption …` / `%% 图片题注 …` | caption for a figure |
| `%% References Title …` / `%% 参考文献标题 …` | the bibliography heading |

Full list: manual §3.4.

**Paragraphs** — one line is one paragraph; consecutive lines are never joined. A break *inside* a
paragraph (an address, verse, a long title) is written as a backslash or two spaces at the end of the
line: it becomes a line break within the same paragraph, not a new paragraph. Suspected wrapping — a
plain line without closing punctuation followed by another plain line — is reported as a warning with
the line numbers; short paragraphs written one per line are correct as they are.

**Title, author, abstract and keywords go in the body as style lines, never in YAML** — their
position on the page is the author's decision and YAML has no position. Pre-flight blocks those keys
and prints the exact line to write instead.

**YAML holds only position-independent configuration**: `bibliography:`, `csl:`, `crossref:`
(`link-citations: false` drops the in-text hyperlink).

**Equations** — `$$...$$ {#eq-name}` on its own line, referenced as `@eq-name` (no brackets: `[@eq-name]` is citation syntax and pre-flight rejects it). Chinese manuscripts
get 「式/图/表」 prefixes and （1）numbering, English ones Equation/Figure/Table and (1);
`chapters: true` under `crossref:` switches to per-chapter numbering (indented on its own line —
`crossref: chapters: true` on one line is not valid YAML). `\tag{}` is blocked.

**Citations** — `[@key]` parenthetical, `@key` narrative, resolved from `bibliography:` + `csl:`. A
`.bib` is mandatory once the manuscript cites: handwritten reference lists are not supported, and
`[@key]` without `bibliography:` would be printed literally.

**Figures and tables** — `![](path/img.png){width=13cm}`, caption in its own `%% Image Caption`
paragraph; table caption above, note below. Do not put `{#fig-...}` labels on images. Column widths
follow the separator row's dash lengths.

**Block markers** — three, each on its own line with blank lines around it: `{{< pagebreak >}}`,
`{{< toc >}}`, and `{{< section >}}` / `{{< section body >}}`. A section marker names *the section
below it*; that name's page numbering, header and footer are declared once in the format file
(`Section: body`, `body page-number: …`, `body header: …`, `body footer: …`). A marker at the very
start names the first section without adding a blank page; never add a page break next to one.

**Unsupported Markdown is blocked with a replacement, never printed literally** — the list is manual §2.8.

## 3. The format file

**Two different things can be done with a `.docx` the user supplies — keep them apart:**

| | command | what it takes from the `.docx` | limit |
|:--|:--|:--|:--|
| **read it** (反推) | `md-to-word-template x.docx -o format.txt` | its styles and page setup, as a draft `format.txt` | what `format.txt` can express; the rest lands in the "to confirm" list |
| **pour into it** (灌入) | `--base-template x.docx --keep-until …` | its front matter, kept byte for byte; the body is replaced by ours | cut point must stop before its contents page; needs a Word-installed machine for the layout check |

Reading it gives a reusable format file; pouring into it keeps an existing template's cover and front
matter verbatim. Neither replaces the other, and a document with an official cover usually wants both.

**Check for an existing format file before writing one** — the user may already have one beside the
manuscript, or a target `.docx` worth reverse-engineering.

0. **Starting from nothing** — `md-to-word init` writes a complete preset copy plus a one-page
   manuscript that exports as-is. Useful when the user has no format file and no template.
1. **Built-in preset** — auto-selected by manuscript language (`zh-academic` for Chinese, `en-nature`
   for others), or explicitly `--preset zh-tw-academic` (Traditional Chinese), `zh-report`,
   `zh-gb9704` (official-document body, not the red-header letterhead or 版记) or `en-apa-student`
   (APA 7 student paper). Use as-is when the user has no custom template or spec; details: manual §3.3.
2. **Copy and edit a preset** — change only the lines the user mentioned. Field order is fixed: font,
   size, bold, italic, alignment, line spacing, space before, space after, indent. Every style line
   must be complete; missing fields are errors.
3. **Reverse-engineer a target `.docx`** — `md-to-word-template target.docx -o format.txt`, then work
   through the "to confirm" list at the end of the draft.

Each property has exactly one accepted spelling (Simplified Chinese or English — Traditional Chinese
key names are not accepted in `format.txt`, even for `zh-TW` manuscripts); anything else is a hard
error with a line number (manual §3.1). `format.txt` in these instructions means *the format file* —
any filename works, `-f` takes it.

`bibliography:` accepts BibTeX / BibLaTeX (`.bib`) **or CSL-JSON** (Zotero, Mendeley and Crossref
exports) — the file content decides, not the extension. Citation style comes from `csl:` with a
bundled name (manual §7) or a path to the user's own CSL. Without `csl:`, Chinese manuscripts get
GB/T 7714 numeric and everything else APA 7th.

Without `-f` the only file picked up is one named exactly `format.txt` beside the manuscript.
When `format.txt` is absent, other `.txt` files there are ignored and named in a reminder. With no `format.txt`, the preset follows the
**manuscript's language**. `--lang` changes the **message language only**; it never changes the
document language, the default preset or the default CSL.

## 4. Export, then the gates

```bash
md-to-word manuscript.md -o manuscript.docx                    # preset by language
md-to-word manuscript.md -f format.txt -o manuscript.docx      # explicit format
md-to-word manuscript.md --validate-only                       # pre-flight only; writes nothing
md-to-word --guide --lang en                                   # this agent guide (pip-only entry)
md-to-word manuscript.md --contract                            # contract + guide, manual and preset paths
md-to-word --contract --json                                   # the same facts, machine-readable
md-to-word thesis.md --base-template base.docx --keep-until "目录" --blind-review
                                                               # keep the cover, strip identifying metadata
```

Run every command from the manuscript's directory: relative image and `.bib` paths resolve against
it. Add `--pdf` (macOS with Word) to expand fields and spot-check the result.

Add `--json` whenever the result must be read back programmatically: stdout carries one JSON object
(`ok`, `returncode`, `input`, `output`, `pdf`, `pdf_skip_reason`, `lang`, `doc_lang`, `format_source`, `messages`,
`warnings`, `errors`, `diagnostics`); logs stay on stderr. `lang` is the message language; `doc_lang`
is the document language actually used (format proofing language first, manuscript otherwise) and
drives the default CSL, cross-reference prefixes and equation-number appearance. `pdf_skip_reason`
is a code when `--pdf` produced nothing, else `null`; `format_source` is `file:/abs/path` or
`preset:zh-academic`.

`diagnostics` is the same findings as structured data, one object each:
`{severity: "error"|"warning", code, file, line, message}`. Branch on `code` (for example
`gate.image.missing`), show `message`; `line` is null when a finding has no single line. Never parse
the prose. `--contract --json` returns version, guide/manual paths, preset paths and `sha256`,
accepted style names in both languages, YAML keys, block markers, figure formats, exit codes and
the exact `--json` keys.

`--validate-only` runs the same pre-flight, tries building the style template in a temporary
directory, and writes no `.docx`: exit `0` means the manuscript and format are exportable, `1` carries
the line-numbered errors.

`--blind-review` strips identifying **document properties** from the final file: author, company,
custom properties (student ID), cover thumbnail, comment and revision authors. It does not anonymise
text — names in the body, cover and headers still need to be replaced. With `--base-template`, an
identifying base is reported in the result when the flag is absent; that metadata otherwise travels
into the output verbatim.

Two gate levels, split by "would the mistake be visible afterwards" (criteria: manual §5):

- **Blocking** — invisible afterwards (dropped content, literal syntax, unmapped formatting); fix the line, never `--no-check`.
- **Warning** — visible but non-compliant (over-wide image, distant caption, skipped level); report it.

Exit codes: `0` every gate passed; `1` manuscript, gate or dependency problem; `2` a usage error
(bad flags or a missing argument); `3` the `.docx` was written but the optional `--pdf` proof was
skipped. Messages follow the manuscript's language.

## 5. Verify before delivery

- Confirm the `.docx` exists and the command exited `0`; report the format source, the citation
  style and every warning.
- Say plainly that layout still needs a check in Word: row heights, column widths, and where
  equations and captions settle are only visible in a real renderer.
- With a TOC, `{style-title}` headers or per-section page numbers, run once with `--pdf` and check
  the first page, the widest table, an equation-heavy page and the references.

## 6. Boundaries

- **Covers & front matter**: custom graphical covers/declarations cannot be authored in `format.txt`
  alone — pass `--base-template cover.docx --keep-until …` (§3, manual §9.3) to preserve an existing
  `.docx` cover untouched, or merge the cover in Word afterwards.
- **Tables & layout**: merged cells, diagonal headers, cell shading, multi-column layouts, and
  text-wrapped floating figures are not supported in Markdown; complete those in Word after export.
  (Double-sided `Mirror Margins` and `Gutter` *are* supported in `format.txt`.)
- **Colours**: style-level text colour (`color#RRGGBB` in `format.txt`) works; **inline per-word
  colour** (`{color=…}` inside a Markdown run) is not supported (unlike inline bold/italic/sub/sup,
  which go directly in `.md`).
- Only equation cross-references are supported (`{#eq-x}` + `@eq-x`); figure and table numbers are
  typed into the caption.
- TOC page numbers are Word fields, filled when Word opens the file. A title excluded from the TOC
  cannot also feed `{style-title:Heading 1}` (`no-toc` + `join-header` is rejected; split sections
  with `{{< section >}}`).
- **Fonts and office suites**: a `.docx` records font *names*, not the fonts themselves. The
  declared sets target Chinese Windows + Microsoft Word; if the opening machine lacks one, Word
  substitutes it and pagination can shift. WPS can open the file, but does not expand the TOC field
  and may show `Error! The style is not specified.` in a `STYLEREF` chapter header — Microsoft Word
  is the acceptance target. Check the delivered file in the software the recipient will use.

Full statements: manual §6 (limits) and §8 (symptom → fix).

## 7. Scope

This skill compiles a finished manuscript into a `.docx` and nothing else. Drafting, rewriting,
polishing, searching for sources and verifying reference metadata belong to whatever writing tools
the user already works with: take the Markdown they hand you, produce the `.docx`, return it. The
interface in both directions is a Markdown file plus a `format.txt`.

## 8. What this file may rely on

Command and flag names (`init`, `--preset`, `--json`, `--pdf`, `--lang`, `--validate-only`, `-f`, `-o`),
exit codes `0`–`3`, the `--json` keys, diagnostic `code` values (`gate.*`, `pipeline.*`,
`textio.*`), the §2 contract, the §3 vocabulary, the preset names `zh-academic` and `en-nature`
(plus `zh-tw-academic`, `zh-report`, `zh-gb9704`, `en-apa-student`), and the fixed file name
`format.txt` are stable. Message wording, package layout and the version number may change — pass
`--json` and read the keys, never the prose.
