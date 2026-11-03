# md-to-word Manual (volume 2: theses)

Read this volume when the manuscript contains any of `{{< section >}}`, `{{< toc >}}`,
`crossref: chapters`, `Appendix`, `References` or `--base-template`. **It does not repeat volume 1**
(`manual_en.md`): commands, the style vocabulary, format-file syntax, gates and exports live there.

## 1. What a thesis has that a journal paper does not

| Element | Where it is explained |
|:--|:--|
| Cover, originality statement, English cover | §2 here |
| Roman numerals for front matter, body starting at 1 | §3 here; syntax in volume 1 §2.5 |
| Table of contents (field, dot leaders, depth) | volume 1 §2.5; outline levels §6 here |
| Equations numbered by chapter `(2-1)` | volume 1 §2.3; appendices §4 here |
| Double-ruled chapter header (`{style:Heading 1}`) | volume 1 §2.5, §3.1 |
| References in GB/T 7714 | volume 1 §4, "References: only the `.bib` route" |
| Three-line tables, repeating header rows | volume 1 §2.4, §3.1 |

## 2. Cover and front matter

The cover is rarely one page: Chinese cover, English cover, originality statement, copyright
authorisation, with blank pages in between. All of it is **layout**, and `format.txt` cannot express
layout — Markdown gives you centring, sizes, spacing and pictures, not absolute positioning, text
boxes or exact alignment inside a fixed line grid.

Three routes, ordered by how much can be guaranteed:

1. **Pour the body into the school's template (recommended)**: keep the school's `.docx` as front
   matter and replace the rest with our typeset body. See the next section.
2. **Text-only covers**: if the cover is plain text with no crest or fixed rules, Markdown can do it
   (`%%` style lines, a picture, and a closing `{{< section header=none footer=none >}}`). The
   template library states whether a given school allows this.
3. **Lay it out yourself in Word**: the tool produces the body, you merge the cover by hand. Most
   robust, most manual. **Never paste the school's cover into the output** — Word redefines
   same-named styles and the whole body follows.

### 2.1 Pour the body into the school's own template (experimental)

Covers, originality statements and double-ruled chapter headers cannot be expressed in `format.txt`,
and copying them by hand lets Word redefine same-named styles and drag the whole body with it. This
path works the other way round: **use the school file as the base**, keep its first sections as front
matter, and replace the rest with our typeset body.

```bash
md-to-word manuscript.md -f format.txt --base-template school-template.docx --cover-sections 4 -o out.docx
```

`--cover-sections N` is **your declaration**: the first N sections of the base are front matter.
Pages and sections are not the same thing (4 sections = 6 pages when blank pages sit between them),
so you can also say it in pages: `--keep-pages 6` makes the tool try a few cuts and report
"6 pages = 3 sections", which you then keep as `--cover-sections 3`.
The number is never guessed; cutting too early silently drops later cover pages, so the export always
reports "the first paragraph after the cut is ..." — read it.

One rule: **no file is produced unless it verifies**, in two layers:

- **Structure (every platform)**: every front-matter node must be byte-identical to the original, none
  of its styles, numbering definitions or theme may go missing, style names must stay unique with one
  default per type, and every footnote reference must resolve. This proves *we did not touch the cover*.
- **Layout (only where Word is installed)**: both files are laid out by Word and the front-matter pages
  are compared word by word; any mismatch deletes the output. This proves *it still prints the same* —
  pagination and blank pages cannot be seen in the XML.

On Windows only the first layer runs, and the export says so: check the layout yourself in Word.
(PDF rendering has only ever been implemented for macOS.)

Two things it cannot verify: whether the cut point is right (that is what the note above is for), and
whether fields or macro buttons in the cover need a click when opened.

## 3. Sections and page numbers

**One rule**: `{{< section … >}}` describes **the section above it**, not the one after. So "front
matter in lower-case Roman" goes after the table of contents, before chapter one.

- For a cover: `{{< section page_number=lowerRoman start=1 header=none footer=none >}}` — give all
  three, or the cover will carry a header and a page number.
- **The body's numbering comes from the format file's `Page Numbers:` line**: it restarts at `start`
  when the preceding section uses another numbering style or shows no numbers at all, and keeps
  counting when that section is already decimal (references after the body never fall back to 1).
- A section break already starts a new page: **do not add `{{< pagebreak >}}` after it**, or you get
  one extra page (the pre-check warns).

## 4. Numbering equations by chapter and by appendix

- By chapter: `crossref: chapters: true` in the YAML. The chapter number comes from the enclosing
  level-1 heading, never from digits typed into the heading.
- Appendices: a level-1 heading such as `# Appendix A Data` is treated as an appendix chapter; `{c}`
  takes `A`, and numbering restarts at 1 inside it. Headings without an identifier get A, B, C in
  order. Appendices **do not consume chapter numbers** — six chapters before an appendix stay 1–6,
  and an acknowledgement after it is chapter 7.
- For a prefix such as `(App 2-1)`, add `Appendix Equation Number Format: (App {c}-{n})`; without it
  the body's format applies.

## 5. Double-ruled chapter headers

Write `Header Content: {Style:Heading 1}` in the format file and the header follows each chapter
title. Two things must hold at once:

- every chapter in the manuscript uses `#` (level 1); `##` will not be found;
- the references heading must also be level 1 in the structure, or those pages keep showing the
  previous chapter.

## 6. Common traps

All of these came from real reports. None of them fails loudly; they just come out slightly wrong:

| Symptom | Cause |
|:--|:--|
| A table is set to centred but stays left | Only a separator row with colons makes per-column statements; the whole table follows the `Compact:` row's alignment |
| Equations crush the lines above and below | Fixed line spacing (`line-spacing 20pt`) is shorter than the formula; use `line-spacing-min` or a larger value |
| Declared "22 lines per page" but nothing changed | There is a ceiling: body-height ÷ line-height. Declarations beyond it do not take effect, and the pre-check says so |
| References missing from the table of contents | The references heading is not in the TOC levels |
| Page numbers continue from the front matter | See §3: the body restarts from the format file's `start` |
| Appendix equations numbered (1-1) | The appendix heading has no identifier, or no appendix number format is set |
| Front matter needs page numbers but no header | `header=none` only drops the header; page numbers ride on the footer, so do not write `footer=none` |

## 7. Back to volume 1

Style vocabulary (§3.4), the full format-file syntax (§3.1–3.5), pre-check and the three gates (§5),
capability limits (§6), built-in CSL (§7) and the error reference (§8) are all in `manual_en.md`.
