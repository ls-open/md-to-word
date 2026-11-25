# Demo 06 — APA Style 7th edition, student paper

An APA 7 student paper compiled with the `--preset en-apa-student` preset: US Letter,
1-inch margins, 12pt Times New Roman, double spacing, 0.5-inch first-line indent,
page number in the top-right header, five heading levels, and a three-line table.

```bash
md-to-word paper.md -o paper.docx --preset en-apa-student
# or, from the repository root:
bash scripts/export.sh demo/06_apa_student/paper.md -o /tmp/apa.docx
```

`paper.docx` / `.pdf` / `page-*.png` are the compiled deliverable and its pages, rendered by Word.

The title page is written with style lines (`%% 文档标题`, repeated `%% 作者`, `%% 日期`)
and ends with a manual `{{< pagebreak >}}`; the title is then repeated with `%% 副标题`.

Known differences from the official sample:

- Level 4 and 5 headings are run-in in APA; here they are separate indented paragraphs.
- Affiliation, course, and instructor have no dedicated styles — repeat `%% 作者`.
- Table number (bold) and title (italic) must be written inline: `%% 表格题注 **Table 1** …`.
- Figures and tables are not auto-numbered; write Table 1 / Figure 1 yourself.
- Block quotes use `left-indent 3chars` ≈ 0.5in rather than an exact 0.5in indent.
