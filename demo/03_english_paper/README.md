# Demo 03 — English journal manuscript

A short English paper compiled with the `en-nature` preset: numbered headings, a
three-line table with a caption and note, a captioned figure, a centred equation with a
right-aligned number, an `@eq-model` cross-reference, and an APA bibliography generated
from `refs.bib`.

```bash
md-to-word paper.md -o paper.docx --preset en-nature
# or, from the skill directory:
bash scripts/export.sh demo/03_english_paper/paper.md -o paper.docx --preset en-nature
```

Style lines use the English vocabulary (`%% Abstract Title`, `%% Table Caption`,
`%% Image Caption`, `%% References Title`); the Chinese names work identically.
