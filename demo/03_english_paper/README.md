# Demo 03 — English journal manuscript

A short English paper compiled with the `en-nature` preset: numbered headings, a
three-line table with a caption and note, a captioned figure, a centred equation with a
right-aligned number, an `@eq-model` cross-reference, and an APA bibliography generated
from `refs.bib`.

```bash
md-to-word paper.md -o paper.docx                      # an English manuscript selects en-nature by itself
md-to-word paper.md -o paper.docx --preset en-nature   # the same thing, spelled out
# or, from the repository root:
bash scripts/export.sh paper.md -o paper.docx
```

`page-*.png` are rendered from `paper.pdf`, the Word proof; both are committed with the
manuscript so a change in output shows up as a changed image.

Style lines use the English vocabulary (`%% Abstract Title`, `%% Table Caption`,
`%% Image Caption`, `%% References Title`); the Chinese names work identically.
