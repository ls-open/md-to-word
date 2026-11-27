# Third-party notices

This project is MIT-licensed. It redistributes the following third-party
components; their licenses apply to those components, not to the project as a
whole.

Runtime dependencies installed separately from PyPI (python-docx, lxml, PyYAML,
latex2mathml, pypdfium2, and the optional `mcp`) are not vendored; each keeps
its own license.

## citeproc-py 0.12.2

- Copyright 2011–2013 Brecht Machiels. All rights reserved.
- License: BSD-2-Clause-Views.
- Full text: [`src/md_to_word/csl/LICENSE`](src/md_to_word/csl/LICENSE).
- Upstream: <https://github.com/brechtm/citeproc-py>
- Vendored copy: `src/md_to_word/csl/`. The unused `data/schema`,
  `data/styles`, `data/locales/util` and `scripts` directories were removed.
  Local compatibility changes are folded directly into `model.py`; the
  upstream bodies are recoverable from the citeproc-py 0.12.2 tag.

## CSL locale files

- Source: <https://github.com/citation-style-language/locales>
- License: Creative Commons Attribution-ShareAlike 3.0 Unported
  (CC BY-SA 3.0), <https://creativecommons.org/licenses/by-sa/3.0/>.
- Vendored copy: `src/md_to_word/csl/data/locales/`.
- Each locale XML file carries its own `<rights>` element and contributor
  list; those notices are retained verbatim.

## CSL styles

- Source: <https://www.zotero.org/styles> and the Citation Style Language
  project, <https://github.com/citation-style-language/styles>
- License: Creative Commons Attribution-ShareAlike 3.0 Unported
  (CC BY-SA 3.0), <https://creativecommons.org/licenses/by-sa/3.0/>.
- Bundled copy: `src/md_to_word/resources/csl/`.
- Each style file carries its own `<rights>` element and author list; those
  notices are retained verbatim.
- Local changes: all bundled styles are normalized with
  `scripts/normalize_csl.py` (the `<bibliography>` `hanging-indent` and
  `line-spacing` attributes are removed so paragraph formatting comes from the
  Word template). The GB/T 7714-2015 numeric and author-date styles also
  enable the upstream commented-out `locale="en"` layouts so Chinese and
  English entries can share one bibliography. These changes are indicated here
  as required by CC BY-SA 3.0.
