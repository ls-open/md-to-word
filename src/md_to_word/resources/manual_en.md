# md-to-word Manual

Chinese edition: `manual.md`

Markdown → compliant Word (`.docx`). Content and layout are separate: Markdown is the source,
every format decision is declared in the requirements file; export is deterministic — rerun the
same source at any time and the output is byte-for-byte identical.

This manual ships with the Python package and is versioned with the implementation — `pip install -U`
replaces an implementation and its documentation together. `md-to-word --contract` prints the
contract cheatsheet, the absolute paths of the getting-started guide and of this file, and the
built-in preset paths.

One export needs two files:

| File | What it holds |
|:--|:--|
| manuscript `*.md` | body text + three conventions (§2) |
| requirements `*.txt` | one line of typography declarations per style (§3); without `-r` the built-in preset is used |

---

## Contents

1. Entry points and exit codes
2. Manuscript contract
3. The requirements file
4. Agent workflow
5. Export and gates
6. Capability limits
7. Built-in CSL
8. Error quick reference

---

## 1. Entry points and exit codes

| Entry point | How to use it |
|:--|:--|
| Command line | `md-to-word manuscript.md -o out.docx` |
| Python | `from md_to_word import export` |
| Reverse-engineer a requirements draft from a reference `.docx` | `md-to-word-template reference.docx -o format.txt` |
| AI skill | The skill directory's `export.sh` calls an installed `md-to-word`; a source checkout runs `src/` directly |
| Getting-started guide | `guide.md` inside the package: order of work, how to read the gates, boundaries. Read it first when only the package is installed: `md-to-word --guide` prints it |
| Starting from nothing | `md-to-word init [dir]`: writes a `format.txt` and a `hello.md` that exports as-is |

```bash
md-to-word manuscript.md -o out.docx                     # built-in zh-academic preset (Chinese)
md-to-word manuscript.md --preset en-nature -o out.docx  # international journal preset
md-to-word manuscript.md -r format.txt -o out.docx # explicit requirements file
md-to-word init                                          # format.txt + a hello.md that exports as-is
md-to-word --guide                                       # getting-started guide (pipeline entry)
md-to-word --contract                                    # cheatsheet + guide, manual and preset paths
md-to-word --contract --lang en                          # same, in English (canonical English style names)
md-to-word manuscript.md -o out.docx --verbose           # per-style log, for "the format had no effect"
```

**Choosing the requirements file — one of three**: pass `-r`; otherwise a single `.txt` beside the
manuscript is taken over automatically (the run reports which one); otherwise the built-in preset is
used, **selected by the manuscript's language**: `zh-academic` for Chinese, `en-nature` for every
other language.

**Exit codes**: `0` done; `1` a manuscript, gate or dependency problem; `3` the `.docx` was written
but `--pdf` was not rendered (non-macOS). `0` means every gate passed — **it does not mean the
layout has been checked by eye** (§5.3).

**`--json`**: for programs and agents. stdout carries one JSON object; progress and errors still go
to stderr:

```json
{"ok": true, "returncode": 0, "input": "paper.md", "output": "…/paper.docx", "pdf": null,
 "lang": "en", "messages": ["…"], "errors": []}
```

The keys are fixed and do not change between versions; the values of `messages` and `errors` are
sentences for humans, in the manuscript's language. Parse the keys, not the wording.

**Library call**:

```python
from md_to_word import export

result = export("manuscript.md", "out.docx", preset="en-nature")
if not result.ok:            # ok = the docx was written (a skipped --pdf is not a failure)
    raise SystemExit("\n".join(result.errors))
print(result.output_docx)    # result.messages carries progress and reminders
```

---

## 2. Manuscript contract

A manuscript is ordinary Markdown plus three conventions: headings use `#`, paragraph styles use
`%%`, and numbered equations use `{#eq-}`. **There is no path from arbitrary Markdown to a finished
document**: when the contract is violated, the pre-flight check stops before export and points at
the line number; it never produces a document that looks normal while the formatting was never
mapped.

### 2.1 Headings and levels

- The document title is one line, `%% Title My Document Title`; its position is decided by that
  line (it may come after a cover page). Subtitle, author and date work the same way, one line
  each: `%% Subtitle …` / `%% Author …` / `%% Date …`. **Do not put these four in YAML**; the
  pre-flight check rejects them.
- In the body, `#` starts the section headings; levels are consecutive and never skipped.
- If headings carry their own Arabic numbering (`1.`, `2.1`, `2.1.1`), the depth of the numbering
  equals the number of `#` characters.

### 2.2 The paragraph style line `%%`

To style a paragraph, start the line with `%% Style Name content`:

```markdown
%% Abstract Title Abstract

%% Abstract This paper proposes a method …

%% Keywords Keywords: alpha; beta; gamma
```

- Symbol, style name and content on the same line; **one line is one paragraph and a blank line
  ends it**; there is no closing symbol — the same layout rule as `# Heading`.
- Why headings can use a symbol and paragraphs cannot: there are only six heading levels, so the
  number of `#` characters encodes the level; there are thirty-odd paragraph styles, which a symbol
  cannot encode, so the name follows the symbol.
- Style names come from the closed vocabulary in §3.4; a wrong name is an error with a line number.
  **Heading styles (`Heading 1` etc.) cannot be written here**; the level is set by `#` only.
- `Bibliography` cannot be written here either: the reference list is generated from `.bib` and is
  **inserted after the `%% References Title` line** (a literal `# References` heading also works),
  so appendices and acknowledgements can follow the references normally.
- Every block-level element (`$$` equation, first table row, standalone image line, short code,
  `%%` line) **must be separated from adjacent body text by a blank line**; §2.5 has the table of
  which side must be blank. `%% Table Caption` may sit directly above the first table row.

### 2.3 Equations

**There is only one numbering syntax**: `$$…$$ {#eq-label}`; the number is generated by the writer
in order of appearance.

```markdown
$$Y_{ij} = \alpha_0 + \beta_1 X_{1,ij} + \varepsilon_{ij}$$ {#eq-model1}
```

- Refer to it in the body as `@eq-model1`; the rendered prefix follows the manuscript language:
  `Equation` for English manuscripts, 「式」 for Chinese ones. To override, write `crossref:`
  explicitly in YAML (§2.7); YAML wins.
- **Numbering by chapter** (a thesis `(2-1)` rather than `(1)`): write `crossref: chapters: true`
  in YAML. The chapter number is the ordinal of the level-1 heading the equation belongs to; a
  hand-typed number in the heading is not read.
- **Number appearance**: write one line in the requirements file,
  `Equation Number Format: ({c}.{n})` — `{n}` is the ordinal (required) and `{c}` the chapter
  number (optional). Without it the language default applies: `(5.1)` / `(1)` for English,
  `（5-1）` / `（1）` for Chinese. The number beside the equation and `@eq-x` in the body use the
  same format — never parenthesised in one place and not in another.
- An unnumbered equation is simply `$$…$$`: it gets no number and consumes none. Writing a label
  without referring to it is allowed; the number still appears.
- **Do not write `\tag{…}`**: the whole equation degrades into literal text in Word; the
  pre-flight check stops it and shows how to rewrite the line.

### 2.4 Figures, tables and captions

| Element | How to write it | Style it lands in |
|:--|:--|:--|
| Table caption | one line above the table: `%% Table Caption **Table 1** Comparison of methods` | `Table Caption` |
| Table note | one line below the table: `%% Table Note Note: …` | `Table Note` |
| Image | `![](path/img.png){width=14cm}` | `Figure` |
| Image caption | one line above or below the image: `%% Image Caption Figure 1 System overview` | `Image Caption` |

- A caption is a **separate paragraph**, not a field attached to the table or image; a leading
  `%%` is the only styling entry point. "The caption stays on the same page as its figure or table"
  is controlled by `keep-with-next` on the caption style, and the writer adds it according to
  whether the caption sits above or below the figure.
- The image line describes the image itself only: the square brackets hold the accessible
  alternative text, and `{width=…}` is clamped to the text block (an over-wide value is silently
  clamped to the text-block width; the pre-flight check stops the over-wide spelling).
- **Do not add a `{#fig-xxx}` label to an image line**: it would get the three-line table's rules
  and lose its centring. Type the figure number into the caption text instead.
- Local formatting inside a caption is written directly in the text (`**Table 1**` for a bold
  number, `*Title*` for an italic title) and is preserved faithfully in the export.
- Column widths are left alone by default (sized by content). **To set column-width ratios, make
  the dashes in the separator row uneven** (`|:--|:--|:------|` ≈ 2:2:6, spread across the text
  block; only the dashes are counted). Identical dashes = not specified, which is also why equal
  widths cannot be forced.
- Tables need leading and trailing pipes (`| a | b |`); a table without outer borders is not
  recognised.

### 2.5 Block markers

Only three are recognised, **each on its own line** and separated from body text by blank lines:

| Marker | Effect |
|:--|:--|
| `{{< pagebreak >}}` | page break |
| `{{< toc >}}` / `{{< toc 2 >}}` | table-of-contents field; the depth follows the `TOC 1/2/3` styles declared in the requirements file, or is given directly by the number |
| `{{< section page_number=lowerRoman start=1 >}}` | section break that closes **the section above it** |

- All three write OOXML nodes (the `w:sdt` TOC field, `sectPr`) and are valid only in this tool.
- `\newpage` / `\pagebreak` / `\clearpage` have no effect in docx.
- The TOC uses a **field**, not a static list: page numbers must be computed by Word. It updates
  once when the document is opened; **to be fully accurate press F9 once more**.
- Entries come from the **outline level**: `#` headings have one natively; a custom style needs
  `join-toc` on its style line (it cannot be written on body styles).

**Two rules for `{{< section … >}}`**:

- **It describes "the section above it"** (in OOXML `sectPr` belongs to the preceding section):
  written after the TOC and before chapter 1, yet it declares the front matter's lowercase Roman
  numerals — **the body section's page numbers come from `Page Number:` in the requirements file**.
  Its parameter names are the same set as `Page Number:`.
- **Do not put a `{{< pagebreak >}}` after it**: the section break already starts a new page, and
  stacking them pushes out an extra page (the pre-flight check warns). A single-section document
  (report, technical proposal) can use Arabic page numbers throughout and does not need this
  marker.

**Which side must be blank** (varies by marker; each case was checked against the output):

| Marker | Side where it breaks | Consequence |
|:--|:--|:--|
| `$$…$$` equation | after | the next heading or body line is merged into the same paragraph |
| `{{< pagebreak >}}`, `{{< toc >}}`, `{{< section … >}}` | after | same as above |
| standalone image line | before, after | before: merged into the previous paragraph and inherits its style; after: the heading is merged into the image paragraph |
| first table row | before | the table degrades to literal text |
| headings, closing fence line, last table row | none | either way is harmless |

### 2.6 Lists, block quotes, code and inline formatting

- **Lists**: `- ` / `1. ` land in `Body Text`; numbering and indentation come from the engine's
  three-level numbering definition (Enter, changing the level and changing the number format all
  still work in Word); **two spaces of indentation is the next level, at most three levels**; the
  fourth level and beyond merge into the third. Lists inside block quotes are supported too.
- **Block quotes**: write `> ` as usual; the requirements file must declare a `Block Text:` style
  line (the built-in presets already do).
- **Code blocks**: a ``` fence lands in `SourceCode`; the base template already gives it a
  monospace font, zero indentation, single line spacing and left alignment, so **it works without a
  `Code:` line**; write one only to change size or colour. Inline `` `code` `` uses
  `VerbatimChar`.
- **Footnotes**: write `[^1]` in the body plus `[^1]: the note text`; **nothing has to be declared
  in the requirements file** (without it the style is inferred from the body: same font and
  alignment as the body, one size smaller, single line spacing, superscript number).
- **Inline formatting is written directly in the text**: `**bold**`, `*italic*`,
  `~~strikethrough~~`, `[underline]{.underline}`, `H~2~O`, `x^2^` — the renderer writes them
  straight as character properties; no declaration in the requirements file is needed and they do
  not conflict with style-level settings.
- **Fonts are free**: any font installed locally (`SimSun`/`宋体`, `FangSong`/`仿宋`,
  `仿宋_GB2312`, `方正小标宋简体`, `Microsoft YaHei`/`微软雅黑`, `KaiTi`/`楷体`).

### 2.7 Manuscript header: YAML carries configuration only, never position

There is one criterion: **YAML has no position.** Anything whose "which page, which paragraph" is
decided by the author goes into a body style line. The title especially — it may be the first line
of page 1, or it may come after a cover page; in YAML it can only be the former.

| Element | How to write it |
|:--|:--|
| Bibliography, CSL style | YAML `bibliography:` / `csl:` |
| Cross-reference prefixes, numbering by chapter | YAML `crossref:` (`eq-prefix`, `fig-prefix`, `tbl-prefix`, `chapters`) |
| Whether citations are hyperlinked | YAML `link-citations:` (on by default; `false` turns it off) |
| Title, subtitle, author, date, abstract, keywords, references section title | body style lines, see §2.1 and §2.2 |

```markdown
---
bibliography: references.bib
csl: apa.csl
---

%% Title My Document Title

%% Author Jane Doe

%% Abstract The abstract text …
```

> **`title` / `subtitle` / `author` / `date` / `abstract` / `keywords` in YAML are rejected by the
> pre-flight check**, and the error names the exact line to write instead. This is not a
> compatibility gap: a title nailed to page 1, or an abstract silently dropped, is far harder to
> find than an error. The only exception is `reference-section-title`, which only warns.

### 2.8 Unsupported syntax

These do not raise an error on their own; they would print the raw syntax into Word unchanged, so
the pre-flight check always stops them and gives an alternative:

HTML tags and `<https://…>` autolinks, horizontal rules `---`, setext (`====`) headings,
definition lists, task checkboxes `- [ ]`, tables without leading and trailing pipes, a block quote
inside a block quote, full-width `％％`, four-space indented code blocks, bold spanning two lines
`**…(newline)…**`, inline maths spanning two lines, a second paragraph in a list item (blank line +
indentation), a heading with no space after `#`, a heading with only `#` and no text, properties
other than `width` on an image line (such as `{align=right}`).

---

## 3. The requirements file

The format requirements file (`format.txt` throughout this manual — the name is free) is a small language: one style per line, every property written on that line.
Three rules:

1. **Write every property on one line**: each style line must contain
   `font size [bold/not-bold italic/not-italic] alignment line-spacing space-before Npt
   space-after Npt indent Nchars`. When there is no paragraph spacing or indent, **still write it
   explicitly**: `space-before 0pt space-after 0pt indent 0`.
2. **Assemble in complete sets by structure**: the five base lines are needed by every document
   (§3.4); tables / figures / abstract and keywords / references / TOC / block quotes / footnotes
   are added in complete sets for the structures the manuscript actually uses. If a structure is
   used but its lines are missing, the pre-flight check reports it.
3. **Start from a preset**: do not start from a blank file. Copy a built-in preset (its path is
   printed by `md-to-word --contract`) next to the manuscript and change only the lines the user
   explicitly mentioned.

**Comments**: a whole line starting with `#` is a comment; **a `#` inside a line is not** — in
`Body Text: Times New Roman 12pt #bold` the `#bold` is reported as an unknown word (the only
in-line use of `#` is colour, `color#1F4E79`).

### 3.1 Vocabulary (one spelling per property)

A style line has the form `<style name>: <property 1> <property 2> …` (either `:` or the full-width
`：` works). **Any word outside this table is an error with its line number** — parsing consumes
whole words, so an unrecognised word is reported: it is neither silently dropped nor misread by
another rule.

| Property | Canonical spelling | Example | Wrong spelling (reported as an error) |
|:--|:--|:--|:--|
| Font | `<CJK font>/<Latin font>`, or a single font | `SimSun/Times New Roman` | — |
| Font size | `<number>pt`, or a Chinese size name | `12pt`, `小四`, `三号` | `12` (no unit), `12lb`, `12磅` |
| Bold | `bold` / `not-bold` | `bold` | `notbold`, `bold=true` |
| Italic | `italic` / `not-italic` | `italic` | `notitalic`, `oblique` |
| Alignment | `center` / `left` / `right` / `justify` | `left` | `centre`, `middle`, `justified`, `both` |
| Colour | `color#<six hex digits>` | `color#1F4E79` | `color blue` (colour names are interpreted differently across devices, so only hex values are accepted); inline `{color=…}` has no effect |
| Line spacing (multiple) | `line-spacing <number>` | `line-spacing 1.5` | `line-spacing 1.5x`, `line-spacing single` |
| Line spacing (fixed) | `line-spacing <number>pt` | `line-spacing 20pt` | `fixed-line-spacing 20pt` (pins the line height at N pt, so content taller than it is clipped) |
| Line spacing (minimum) | `min-line-spacing <number>pt` | `min-line-spacing 25pt` | `line-spacing-min 25pt` — reported on the spot with the expected form |
| Space before / after | `space-before <number>pt` `space-after <number>pt` | `space-before 0pt space-after 6pt` | — |
| Indent (required; one kind per line) | `indent <number>chars` (Chinese manuscripts) / `indent <number>in` (English) / `hanging-indent <number>in` | `indent 2chars`, `indent 0` | `indent 1cm`, **writing both first-line and hanging indent on the same line** |
| Left indent | `left-indent <number>chars` | `left-indent 2chars` | `indent-left 2chars`, `left-indent 2cm` |
| Dot-leader tab | `dot-leader-tab` | add it to a hand-typed line: the page number is right-aligned at the end, with a dot leader | writing a position number; writing it on `TOC 1/2/3` has no effect |
| Pagination control | `keep-with-next`, `page-break-before`, `keep-lines`, `widow-control` / `no-widow-control` | `Heading 1: … keep-with-next page-break-before` | — (`page-break-before` is more robust than a hand-written `{{< pagebreak >}}`: after content is added or removed the heading still starts on a new page automatically) |
| Join TOC | `join-toc` | `Abstract Title: … join-toc` | writing it on a body style (`Body Text` / `First Paragraph` / `Normal` / `Compact`) — every paragraph would become a TOC entry |
| Repeat across pages | `repeat-header` | `Table Header: … repeat-header` | writing it on any style line other than `Table Header:` (it describes the header row's `w:tblHeader`) |
| No border | `no-border` (removes the bottom border built into the base template) | `Title: … no-border` | `border-bottom-none` — identical output to `no-border`, so only one spelling is kept |
| Bottom border | `border-bottom-<single\|double\|even-double\|thick-thin\|triple>` `[border-width <N>pt]` | `Header: … border-bottom-double border-width 1.5pt` | `underline` (that is a character property); `border-width` on its own (nowhere to land without a bottom border) |
| Character spacing | `char-spacing <N>pt` (positive widens, negative tightens) | `char-spacing 0.5pt`, `char-spacing -0.2pt` | `letter-spacing 0.5pt` |
| Paper | `Paper: <A4\|Letter>` (defaults to A4) | `Paper: A4` | `Paper: B5` |
| Margins | `Margins: top <N>cm bottom <N>cm left <N>cm right <N>cm` | `Margins: top 2.54cm bottom 2.54cm left 2.54cm right 2.54cm` | — |
| Gutter | `Gutter: <N>cm` | `Gutter: 1cm` | — (it is added outside the left margin; do not fold it into the left margin) |
| Header / footer distance from the edge | `Header Distance: <N>cm` / `Footer Distance: <N>cm` | `Header Distance: 1.40cm` | — |
| Document grid | `Document Grid: <N> lines` | `Document Grid: 22 lines` | specify it by line count only; line-spacing multiples are compensated automatically, so no manual tuning is needed; **there is no "characters per line" switch** (it follows font size and text-block width) |
| Latin font | `Font: <typeface>` (global Latin default) | `Font: Times New Roman` | — |
| Proofing language | `Proofing Language: <language code>` | `Proofing Language: en-US` | `Proofing Language: English` (without it the base template proofreads as English, and Word flags a Chinese manuscript as misspelled throughout) |
| Table (required when the manuscript has tables) | `Table: <center\|left\|right> <three-line\|grid\|top-bottom\|none> [border-top/border-bottom/border-header <N>pt (rule widths)] [border-inside <N>pt (grid only)] [valign center\|top\|bottom] [cell-margin <N>cm] [no-row-split]` | `Table: center three-line border-top 1pt border-bottom 1pt border-header 0.25pt valign center` | writing `border-inside` for three-line or top-bottom (there are no inner rules); writing any border width for `none`; `cell-margin` in pt rather than cm |
| Paragraphs in tables | `Compact: <paragraph properties, same syntax as a style line>` | `Compact: Times New Roman 10pt center …` | — (the font, size and alignment of table text **can only come from this line**; without it a paragraph inherits the body's 2-character first-line indent) |
| Header row (required when the manuscript has tables) | `Table Header: <paragraph properties> [repeat-header]` | `Table Header: Times New Roman 10pt bold not-italic center line-spacing 1.0 space-before 0pt space-after 0pt indent 0 repeat-header` | — |
| Table width | **Do not declare it** — sized by content by default | — | to set column-width ratios, vary the dashes in the separator row (§2.4) |
| Header / footer styles | `Header: <paragraph properties>` / `Footer: <paragraph properties>` | `Header: Times New Roman 9pt center line-spacing 1.0 space-before 0pt space-after 0pt indent 0` | putting content into a style line — the font segment is the only free text, so in `Header: Some University 9pt …` the words `Some University` are silently accepted as a font name |
| Header / footer content | `Header Content:` / `Footer Content:`, plus `Even Header Content:` / `First Header Content:` / `Even Footer Content:` / `First Footer Content:` | `Header Content: {style-title:Heading 1}` | `{style-title:一级标题}` (STYLEREF accepts only a Word style name); writing a content line without its style line counts as a missing required line |
| Page number format | `Page Number: <decimal\|roman\|lowerRoman\|lowerLetter\|upperLetter> [start <N>]` | `Page Number: decimal start 1` | `Page Number: 1,2,3`; declaring it without a `{page}` field (this line only writes `sectPr`; the page number appears only through header/footer content) |
| Equation number position | `Equation Number: <right\|inline>` | `Equation Number: inline` | without it the default is `right` (the number sits at the right edge of the text block) |
| Equation number format | `Equation Number Format: <template>`, `{n}` = ordinal (required), `{c}` = chapter (optional) | `Equation Number Format: ({c}.{n})` | writing `{c}` while the manuscript does not enable `crossref.chapters` (the pre-flight check stops it) |
| Footnote (optional) | `Footnote: <paragraph properties>` | `Footnote: Times New Roman 9pt not-bold not-italic left line-spacing 1.0 space-before 0pt space-after 0pt indent 0` | writing half of it (`Footnote: Times New Roman 9pt`) — once declared, every field must be present |

Chinese spellings parse as well and may be mixed into the same line: `加粗` / `不加粗`, `倾斜` /
`不倾斜`, `居中` / `左对齐` / `右对齐` / `两端对齐`, `行距1.5倍`, `行距20磅`, `段前0磅`, `段后6磅`,
`首行缩进2字符`, `悬挂缩进0.5英寸`, `左缩进2字符`, `颜色#1F4E79`, `无边框`, `下边框双线`,
`边框粗1.5磅`, `字距0.5磅`, `与下段同页`, `段前分页`, `段中不分页`, `孤行控制`, `取消孤行控制`,
`加入目录`, `跨页重复`, `点线制表位`. The configuration keys have Chinese forms too (`纸张：`,
`页边距：`, `西文字体：`, `校对语言：`, `页眉距边界：`, `页脚距边界：`, `装订线：`, `文档网格：`,
`页码：`, `表格：`, `表头：`, `页眉：`, `页脚：`, `页眉内容：`, `页脚内容：`, `公式编号：`,
`公式编号格式：`, `脚注：`); the Chinese column of the vocabulary is in `manual.md` §3.1.

**Fields available in headers and footers** (closed set; anything else is an error): `{page}`
(PAGE), `{total-pages}` (NUMPAGES), `{style-title:<Word style name>}` (STYLEREF, e.g.
`{style-title:Heading 1}` = the current chapter title). Field values are computed by Word and
updated when the document is opened or shown in print preview.

### 3.2 A few hard rules that are easy to trip over

- **Units**: a font size is written `12pt`; line spacing, space before/after, border width and rule
  widths also take `pt` in English input (`磅` in Chinese input). A font size written as `12磅` is
  an error with the expected form. Note that a bare number after `line-spacing` is a multiple:
  `line-spacing 20` means 20×, not 20 pt — write `line-spacing 20pt` for an exact height.
- **Indent is a required field on every style line**, and the criterion is not "does this style
  need an indent" but "would omitting it be silently inherited": once the body declares
  `indent 2chars`, `Normal` carries it, and every style based on `Normal` without its own
  declaration inherits the indent. Image paragraphs and text inside tables, pushed right and then
  centred, **push past the right edge**.
- **`Figure` and `Image Caption` are two different styles**: `Figure` is the paragraph holding the
  image (its alignment is controlled by its style line); `Image Caption` is the caption text.
  Without an indent on `Figure`, the paragraph is pushed right and looks like "the image is not
  centred".
- **`Compact` governs table paragraphs only**; **list items go through `Body Text`** and do not
  follow `Compact` (otherwise every item would be centred line by line).
- **TOC entry styles take effect**: `TOC 1/2/3` are written as Word's built-in styles, so font and
  indentation survive a field update. The dot leader and page number are drawn by the field itself;
  `dot-leader-tab` is meaningless for TOC entries.
- **First-line indent and hanging indent are mutually exclusive** (they share the same `w:ind`
  properties); if both appear on one line only one takes effect, so the generator reports an error.
- **Without a width, the border style's built-in default is used**; 1/4 pt is Word's thinnest
  single line.
- **With "different odd and even pages" / "different first page" enabled, containers you did not
  write explicitly are "empty" rather than "inherit the default"**: writing only
  `Footer Content: {page}` and then `Even Header Content: …` leaves even pages without any page
  number at all. The generator fills the empty slots automatically and says so.

### 3.3 The three ways to obtain a requirements file

| What you have | What to do |
|:--|:--|
| A reference `.docx` template | `md-to-word-template reference.docx -o format.txt` reverse-engineers a draft; **items it could not read are listed at the end of the draft** — check each one before using it |
| Format instructions in text or given verbally | fill in whatever the user stated explicitly; derive and fill the unmentioned required fields of the same set per §3.5 |
| Nothing at all | use a built-in preset, export a standard `.docx` first, then adjust from feedback |

### 3.4 Style names (closed vocabulary)

`Title` `Subtitle` `Author` `Date` `Abstract` `Abstract Title` `Keywords` `Heading 1`
`Heading 2` `Heading 3` `Heading 4` `Heading 5` `Heading 6` `Body Text` `First Paragraph`
`Normal` `Compact` `Table Caption` `Table Note` `Figure` `Image Caption` `Bibliography`
`References Title` `Block Text` `Header` `Footer` `Footnote` `SourceCode` `TOC Heading` `TOC 1`
`TOC 2` `TOC 3` `TOC 4` `TOC 5`

Chinese names are accepted as well, so a bilingual or Chinese manuscript can use either column:

| English | Chinese (also accepted) |
|:--|:--|
| `Title` | `文档标题`, `论文标题` |
| `Subtitle` | `副标题` |
| `Author` | `作者` |
| `Date` | `日期` |
| `Abstract` | `摘要` |
| `Abstract Title` | `摘要标题` |
| `Keywords` | `关键词` |
| `Heading 1` … `Heading 6` | `一级标题` … `六级标题` |
| `Body Text` | `正文` |
| `First Paragraph` | `首段` |
| `Normal` | `普通` |
| `Compact` | `紧凑` |
| `Table Caption` | `表格题注`, `表名`, `表题` |
| `Table Note` | `表注` |
| `Figure` | `图` |
| `Image Caption` | `图片题注`, `图名`, `图题` |
| `Bibliography` | `参考文献` |
| `References Title` | `参考文献标题` |
| `Block Text` | `引用块` |
| `Header` | `页眉` |
| `Footer` | `页脚` |
| `Footnote` | `脚注` |
| `SourceCode` | `代码` |
| `TOC Heading` | `目录标题` |
| `TOC 1` … `TOC 5` | `目录一级` … `目录五级` |

- **Equivalent spellings** (pick whichever you like): `Captioned Figure` = `Figure`,
  `Code` = `SourceCode`, `Footnote Text` = `Footnote`, `Block Quote` = `Block Text`,
  `Bibliography Title` = `References Title`. Apart from these and the Chinese column above there
  are no synonyms; any name outside the table is an error.
- Every property and style name also has a Chinese canonical spelling, so the two vocabularies can
  be mixed (`正文：宋体/Times New Roman 小四 行距1.5倍`). Negations must keep the hyphen:
  `not-bold`, `not-italic`. Error messages follow the language of the input.
- **Always required**: `Title`, `Heading 1`, `Body Text`, `First Paragraph`, `Normal`.
- **Required when used**: `Heading 2`–`Heading 6` by the actual heading depth; tables →
  `Table` + `Table Header` + `Compact`; figures → `Figure` + `Image Caption`; TOC →
  `TOC Heading` + `TOC 1/2/3` (4 and 5 are optional but must be consecutive); abstract →
  `Abstract Title` + `Abstract`; references → `References Title` + `Bibliography` (when using
  `.bib`); block quotes → `Block Text`; `Header Content` requires `Header` (same for the footer).

### 3.5 Deriving the rest when the user only specified part of it

1. **Explicit wins**: whatever the user or journal states is filled in verbatim.
2. **Disciplinary fallback**: when unspecified, borrow the authoritative standard for the field
   (APA 7th for English social sciences, IEEE for engineering, GB/T 7714 for Chinese).
3. **Derive relatively from the body**: data and notes (`Compact` / table note / code / footnote)
   one size smaller than the body, line spacing tightened to single, 0 pt before and after;
   captions 1 pt smaller than the body or the same size in bold; Heading 1 is 2–3 pt larger than
   the body, the document title 4–6 pt larger.

There is no separate table of values: the built-in presets are the single source of truth for the
defaults.

---

## 4. Agent workflow

The user's original request is usually "export this content as Word in some format". **Follow "ship
one compliant `.docx` first, then fine-tune from feedback"**, taking care of format extraction,
manuscript normalisation and configuration generation end to end.

| Situation | What the user probably says | What to do |
|:--|:--|:--|
| No explicit format requirements | "Just turn it into Word", "export a first version" | Do not interrogate them about format details; export a baseline with a built-in preset. The preset is itself a complete, compliant format, not a placeholder |
| Explicit format requirements | "Follow the school / journal format" | Given a reference `.docx` → reverse-engineer the requirements file; given text only → fill in the fields (§3.3, §3.5) |
| An existing requirements file | "This is our lab's formatting spec" | Pass it with `-r`; nothing inside needs changing |

**Steps**:

1. **Normalise the manuscript**: the source may be freshly generated text, a `.txt`, plain `.md`,
   an old `.docx` or a `.pdf`. Turn it into a `.md` that follows the contract in §2; when the user
   already has a `.md`, create a copy in the same directory and adapt that, leaving the original
   untouched.
2. **Prepare the requirements file**: pick one of the three paths in §3.3.
3. **Export**: `md-to-word manuscript.md -r format.txt -o out.docx`.
4. **Read the gate output**: on exit code `1`, fix the manuscript or add the missing style lines
   according to the reported line numbers; do not bypass it with `--no-check`.
5. **When delivering, remind the user to open the file in Word and check the layout** (§5.3).

### References: `.bib` is the only route

- **No references**: do not write `bibliography:` or `csl:` in YAML, and do not use `[@key]` in the
  body.
- **With references**: write `bibliography: refs.bib` and `csl: <style>.csl` in YAML. The reference
  list is generated by the engine; the user **does not write** the list and does not write
  `%% Bibliography` (the pre-flight check rejects it) — the engine inserts it after the references
  section title line.
- **Hand-written reference lists are not supported**: if only hand-written entries exist, first turn
  them into `references.bib`, then cite from it.
- When `csl:` names a built-in file (such as `apa.csl`), the package looks it up automatically; it
  also accepts a path relative to the manuscript's directory or an absolute path. **A CSL you bring
  is normalised automatically**: `hanging-indent` / `second-field-align` / `line-spacing` are
  removed from `<bibliography>`, and one line says so — direct formatting outranks the style, and
  without stripping it, changing CSL would change the hanging indent and line spacing.
- **Without `csl:`**: Chinese manuscripts default to GB/T 7714-2015 numeric, everything else to
  APA 7th (the criterion is the body language). The default is defined in one place, so it cannot
  produce two different reference lists through two entry points.
- **Citation syntax**:

  | Syntax | Rendered as |
  |:--|:--|
  | `[@key]` | parenthetical citation; several `[@a; @b]`, with a page `[@a, p. 33]`, with a prefix `[see @a]`, year only `[-@a]` |
  | `@key` | narrative citation (`as @a points out`); with a page `@a [p. 33]` |
  | `user@example.com` | emitted verbatim — an `@` preceded by a letter or digit is not a citation |

- **Keys that do not match are stopped by the pre-flight check**: citing a key that is not in the
  `.bib`, or omitting `bibliography:` from YAML, is reported before export with a line number.

---

## 5. Export and gates

### 5.1 Six things in one command

```
pre-flight check → build the style template → read into the document model → write OOXML
→ numeric-integrity check → audit the product against the requirements line by line
```

The template is generated fresh on every export and never cached; `-t` can point at a `.docx` base
(single-section templates only).

### 5.2 Two pre-flight levels; the criterion is "would the mistake be visible?"

| Level | Criterion | Examples |
|:--|:--|:--|
| **Blocking** | A silent error you cannot see afterwards | Lost characters (a table row with the wrong column count), degradation to literal text (`\tag{}`, undefined cross-references), formatting that never takes effect (a style name missing from the template, a table style missing from the requirements file), an abstract or keywords written in YAML, a caption written into the image's square brackets |
| **Reminder** | Visible, just non-compliant | An over-wide image (it gets clamped), a caption too far from its figure or table, skipped heading levels, an extra page break after a section break, a wrapped paragraph, a missing cross-reference prefix |

Reminders do not block export: the author may have meant it, or may intend to finish the job in
Word. If they blocked, the only way out would be `--no-check`, which would also switch off the real
blockers.

### 5.3 You must check with your own eyes before delivery

A `0` return only says structure, styles and counts passed the gates; **the layout must be looked
at in Word**: table row heights and column widths adapt to content, where equations and captions
land, and headers and footers can only be confirmed by opening the file. The export script prints
this reminder at the end.

**With dynamic fields (TOC, `{style-title}` headers, cross-section page numbers) or wide complex
tables, run `--pdf` once before formal delivery** — it is the only way to expand the fields and see
the real pagination:

```bash
md-to-word manuscript.md -o out.docx --pdf
```

From the PDF, check four places: the first page / the widest table page / the equation-heavy page /
the references page. When PDF rendering is unavailable (Windows, Word not installed, or installed
but never launched) it is skipped automatically and does not affect the `.docx` output (exit code
`3`).

---

## 6. Capability limits

**Supported**: every paragraph property a style line can declare (font, size, bold and italic,
colour, alignment, indentation, line spacing, paragraph spacing, borders and table rule widths,
character spacing, pagination control); headers, footers and the three kinds of field; different
odd/even pages and a different first page, per-section page numbers; tables (three-line, full grid,
top-and-bottom rules, borderless, repeating header rows, cell alignment and margins, column-width
ratios); native OMML equations and cross-references; figures and captions; `.bib` + CSL references;
inline formatting; three-level lists and lists inside block quotes; footnotes.

**Not possible** (do it in Word, or write it differently):

| Not possible | What to do instead |
|:--|:--|
| A custom cover page (crest, underlined fill-in fields, signature page) | `%% Title` generates one standard title block only; merge a cover supplied by your institution into the first page in Word, or lay out a simple one with a table |
| Merged cells, diagonal header cells, cell shading | A Markdown table is a regular two-dimensional grid; export the grid, then merge those cells in Word |
| Multi-column layouts, floating figures with text wrapping | Single column is the only layout; images go into their own centred figure paragraph |
| Limits above and below the sum/integral sign in a numbered equation | Word only stacks limits above and below the symbol in a display equation; a numbered equation is an inline equation (the number sits at the right via a tab). The content and symbols are correct; the layout differs |
| Arbitrary tab stops | Only `dot-leader-tab` exists (right-aligned with a dot leader) |
| Inline text colour | Colour is a style property (`color#1F4E79`); inline `{color=…}` is not supported |
| Footnote position | Always printed at the bottom of the page that cites it — a Word layout rule |
| More than three list levels | The fourth level and beyond merge into the third |

**Silent clamping**: an image wider than the text block is clamped to the text-block width (15.92
cm on A4 with 2.54 cm margins, less any gutter). The pre-flight check computes the real text block
from the requirements file and stops over-wide spellings.

---

## 7. Built-in CSL

`resources/csl/` inside the package holds 29 styles; every `<bibliography>` has been normalised
(direct-formatting attributes removed, paragraph formatting controlled by the template's
`Bibliography` style). The inventory:

| Group | File name (write this in `csl:`) |
|:--|:--|
| General (start here) | `apa.csl` (default for English manuscripts), `chicago-author-date.csl`, `modern-language-association.csl`, `harvard-cite-them-right.csl`, `ieee.csl`, `acm-sig-proceedings.csl`, `nature.csl`, `science.csl`, `cell.csl` |
| Medicine and life sciences | `american-medical-association.csl`, `bmj.csl`, `the-lancet.csl`, `elsevier-vancouver.csl`, `sage-vancouver.csl`, `springer-vancouver.csl`, `american-chemical-society.csl` |
| Publisher-generic | `elsevier-with-titles.csl`, `elsevier-harvard.csl`, `emerald-harvard.csl`, `springer-basic-author-date.csl`, `springer-mathphys-brackets.csl`, `springer-lecture-notes-in-computer-science.csl`, `multidisciplinary-digital-publishing-institute.csl`, `frontiers.csl` |
| Chinese national standard | `chinese-gb7714-2015-numeric.csl` (default for Chinese manuscripts), `chinese-gb7714-2015-author-date.csl`, `china-national-standard-gb-t-7714-2025-numeric.csl` |
| Other | `iso690-author-date-en.csl`, `iso690-numeric-en.csl` |

If a journal is missing from the list, download its CSL from <https://www.zotero.org/styles> and
point `csl:` at it; it is normalised automatically on export. Every bundled style is rendered by a
test, so what you get is not "downloaded but unusable".

---

## 8. Error quick reference

**Messages follow the manuscript's language**: a Chinese manuscript gets Chinese diagnostics, an
English one gets English diagnostics — including the bracketed category tag and the style-name
examples. The tag is a stable category identifier; the text after it says which line to change.

| Symptom | Cause and fix |
|:--|:--|
| `[missing structural style]` | The manuscript uses a structure whose style lines the requirements file does not declare. Add the line at the reported line number, or switch to a preset |
| `[paragraph style]` | The name after `%%` is not in the §3.4 vocabulary; check the spelling |
| Requirements file does not parse | A property word is not in the §3.1 vocabulary; the error gives the line number, the original word and the expected form |
| Image is not centred | The `Figure:` style line has no indent, so it inherits the body's first-line indent |
| A Chinese manuscript is underlined in red throughout | The requirements file has no `Proofing Language: zh-CN` |
| References were not generated | YAML is missing `bibliography:`, the body has no `[@key]`, or the references section title line is missing |
| TOC entry font is wrong | The TOC entry styles were not written as Word's built-in styles (`TOC 1/2/3`), or `dot-leader-tab` was written on them (no effect) |
| Header shows "Error! Reference source not found" | X in `{style-title:X}` is not a Word style name (write `Heading 1`) |
| The font looks right but is wrong in Word | A third-party template's theme attributes override the explicit font; when passed via `-t`, `asciiTheme` / `eastAsiaTheme` / `themeColor` are stripped automatically |
| Two exports of the same manuscript differ | This should not happen: the zip timestamp is fixed at 1980-01-01 and the output is byte-for-byte reproducible; if it happens, report a defect |
