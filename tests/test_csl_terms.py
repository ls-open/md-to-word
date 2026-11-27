"""CSL 术语的两种回退：form 链与序数的性数。

规范写明：`verb-short` → `verb` → 长形式，`symbol` → `short` → 长形式，
`short`/`verb` → 长形式；序数则按名词的性取变体（法语 `1ᵉʳ` / `1ʳᵉ`）。
以前缺 `verb-short` 就直接印空串，法语序数一律取到第一个（阴性）变体。
"""

from __future__ import annotations

import json
from pathlib import Path

from md_to_word.transform.citations import CitationEngine

BIB = "@book{b, title={A Book}, publisher={Press}, year={2020}}"

TERM_STYLE = '''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text">
  <info><title>terms</title><id>terms</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout><text term="{term}" form="{form}"/></layout></citation>
  <bibliography><layout><text variable="title"/></layout></bibliography>
</style>'''


def _citation(tmp_path: Path, term: str, form: str) -> str:
    style = tmp_path / "probe.csl"
    style.write_text(_term_style(term, form), encoding="utf-8")
    engine = CitationEngine(BIB, style, lang="en")
    return "".join(text for text, _fmt in engine.cite([("b", "")]))


def _term_style(term: str, form: str) -> str:
    return TERM_STYLE.replace("{term}", term).replace("{form}", form)


def test_verb_short_falls_back_to_verb(tmp_path: Path) -> None:
    # `chair` 只有长形式与 verb（chaired by），没有 verb-short。
    assert _citation(tmp_path, "chair", "verb-short") == "chaired by"


def test_symbol_falls_back_to_short(tmp_path: Path) -> None:
    # `translator` 有 short（trans.），没有 symbol。
    assert _citation(tmp_path, "translator", "symbol") == "trans."


def test_symbol_falls_back_to_long_when_short_is_missing(
        tmp_path: Path) -> None:
    assert _citation(tmp_path, "chair", "symbol") == "chair"


def test_short_falls_back_to_long(tmp_path: Path) -> None:
    assert _citation(tmp_path, "chair", "short") == "chair"


def test_locale_fallback_comes_before_form_fallback(tmp_path: Path) -> None:
    """规范：form 回退发生在 locale 回退之后，所以编辑器仍取 en-US 的 verb-short。"""
    assert _citation(tmp_path, "editor", "verb-short") == "ed. by"


FRENCH_ORDINAL_STYLE = '''<style xmlns="http://purl.org/net/xbiblio/csl"
    version="1.0" class="in-text" default-locale="fr-FR">
  <info><title>fr</title><id>fr</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout>
    <number variable="volume" form="ordinal" prefix="vol "/>
    <number variable="edition" form="ordinal" prefix=" | ed "/>
    <number variable="volume" form="long-ordinal" prefix=" | long "/>
    <date variable="issued" prefix=" | ">
      <date-part name="day" form="ordinal"/>
      <date-part name="month" form="long" prefix=" "/>
    </date>
  </layout></citation>
  <bibliography><layout><text variable="title"/></layout></bibliography>
</style>'''


def test_ordinals_follow_the_noun_gender(tmp_path: Path) -> None:
    """`volume` 在法语里是阳性（1ᵉʳ），`edition` 是阴性（1ʳᵉ）。"""
    items = [{
        "id": "a", "type": "book", "title": "T", "language": "fr",
        "volume": "1", "edition": "1",
        "issued": {"date-parts": [[2020, 1, 1]]},
    }]
    style = tmp_path / "fr.csl"
    style.write_text(FRENCH_ORDINAL_STYLE, encoding="utf-8")
    engine = CitationEngine(json.dumps(items), style, lang="fr")
    engine.reserve(["a"])
    text = "".join(t for t, _f in engine.cite([("a", "")]))
    assert text == "vol 1ᵉʳ | ed 1ʳᵉ | long premier | 1ᵉʳ janvier", text


def test_long_ordinals_above_ten_fall_back_to_ordinals(tmp_path: Path) -> None:
    items = [{
        "id": "a", "type": "book", "title": "T", "language": "fr",
        "volume": "11", "issued": {"date-parts": [[2020]]},
    }]
    style = tmp_path / "fr.csl"
    style.write_text(FRENCH_ORDINAL_STYLE, encoding="utf-8")
    engine = CitationEngine(json.dumps(items), style, lang="fr")
    engine.reserve(["a"])
    text = "".join(t for t, _f in engine.cite([("a", "")]))
    assert text.startswith("vol 11ᵉ | long 11ᵉ"), text
