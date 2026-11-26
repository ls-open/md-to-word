# CSL engine

`md_to_word.csl` is the project's CSL 1.0 rendering engine. It is derived from
[citeproc-py 0.12.2](https://github.com/brechtm/citeproc-py) (BSD-2-Clause-Views,
see `LICENSE`) and is maintained here as first-party code.

We keep it in the source tree instead of installing it as a dependency because
the engine is modified directly:

- `model.py` carries the CSL 1.0 fixes and the project's per-item language,
  script inference and multi-layout support as a single implementation per
  method; the upstream 0.12.2 tag is the comparison point.
- `data/locales/*.xml` is the bundled CSL locale set (CC BY-SA 3.0; see
  `THIRD_PARTY_NOTICES.md` at the repository root).
- Unused upstream parts were removed: `data/schema`, `data/styles`,
  `data/locales/util`, `scripts`, the BibTeX reader, and the plain/RST
  formatters.

When updating from upstream, diff against the upstream tag and port the
changes selectively; do not replace this directory wholesale.
