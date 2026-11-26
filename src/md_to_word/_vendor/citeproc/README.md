# Vendored citeproc-py

This directory is a copy of the `citeproc` package from
[citeproc-py 0.12.2](https://github.com/brechtm/citeproc-py), distributed under
the BSD-2-Clause-Views license in `LICENSE`.

It is vendored rather than installed as a dependency because the project
patches engine internals (`Names`, `Group`, `Macro`, `Label`, `FormatNumber`,
`to_ordinal`). Those patches and the engine must ship as one version.

Local changes:

- Removed `data/schema`, `data/styles`, `data/locales/util` and `scripts`;
  only the runtime code and `data/locales/*.xml` are kept.
- Runtime compatibility patches still live in
  `src/md_to_word/transform/citations.py` and will be folded into this copy
  incrementally.

When updating from upstream, diff against the upstream tag and re-apply the
local patches; do not replace this directory wholesale.
