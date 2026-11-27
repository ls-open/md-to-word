"""CSL 能力门禁：未实现的构造明确报错，内置样式不误伤。"""

from __future__ import annotations

from pathlib import Path

import pytest

from md_to_word.config import get_csl_dir
from md_to_word.csl.features import CslFeatureError, check_style
from md_to_word.transform.citations import CitationEngine, CitationError

BIB = "@book{a, author={A, B}, title={T}, year={2020}}\n"


def _style(body: str, *, attrs: str = "") -> str:
    return f'''<style xmlns="http://purl.org/net/xbiblio/csl" version="1.0" class="in-text" {attrs}>
  <info><title>probe</title><id>probe</id><updated>2024-01-01T00:00:00+00:00</updated></info>
  <citation><layout><text variable="title"/></layout></citation>
  <bibliography><layout>{body}</layout></bibliography>
</style>'''


def _engine(tmp_path: Path, style: str) -> CitationEngine:
    path = tmp_path / "s.csl"
    path.write_text(style, encoding="utf-8")
    return CitationEngine(BIB, path, lang="en")


def test_every_bundled_style_passes_the_gate() -> None:
    styles = sorted(get_csl_dir().glob("*.csl"))
    # 目录空了就是打包坏了；没有这一句，整条门禁会变成「零份被检查」而仍然全绿。
    assert len(styles) >= 20, f"内置 CSL 数量异常：{len(styles)}"
    for path in styles:
        check_style(path)


def test_unknown_rendering_element_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(CitationError) as caught:
        _engine(tmp_path, _style("<institution/>"))
    assert "institution" in str(caught.value)


def test_note_styles_are_rejected(tmp_path: Path) -> None:
    style = _style("<text variable=\"title\"/>").replace('class="in-text"', 'class="note"')
    with pytest.raises(CitationError) as caught:
        _engine(tmp_path, style)
    assert "note" in str(caught.value)


def test_unimplemented_attribute_is_rejected(tmp_path: Path) -> None:
    style = _style("<text variable=\"title\"/>").replace(
        "<citation>", '<citation et-al-subsequent-min="2">')
    with pytest.raises(CitationError) as caught:
        _engine(tmp_path, style)
    assert "et-al-subsequent-min" in str(caught.value)


def test_only_complete_all_substitute_rule_is_accepted(tmp_path: Path) -> None:
    """`subsequent-author-substitute` 只实现了默认规则；其它规则会只替换部分姓名。"""
    unsupported = _style('<text variable="title"/>').replace(
        "<bibliography>",
        '<bibliography subsequent-author-substitute="—" '
        'subsequent-author-substitute-rule="partial-first">',
    )
    with pytest.raises(CitationError) as caught:
        _engine(tmp_path, unsupported)
    assert "partial-first" in str(caught.value)

    accepted = _style('<text variable="title"/>').replace(
        "<bibliography>",
        '<bibliography subsequent-author-substitute="—" '
        'subsequent-author-substitute-rule="complete-all">',
    )
    path = tmp_path / "ok.csl"
    path.write_text(accepted, encoding="utf-8")
    check_style(path)


def test_metadata_outside_info_is_rejected(tmp_path: Path) -> None:
    style = _style("<text variable=\"title\"/>").replace(
        "</style>", "<title>stray</title></style>")
    path = tmp_path / "s.csl"
    path.write_text(style, encoding="utf-8")
    with pytest.raises(CslFeatureError) as caught:
        check_style(path)
    assert "title" in str(caught.value)


def test_ignored_but_bundled_attribute_is_accepted(tmp_path: Path) -> None:
    style = _style("<text variable=\"title\"/>").replace(
        "<bibliography>", '<bibliography entry-spacing="0">')
    style = style.replace("<citation>", '<citation cite-group-delimiter=", ">')
    path = tmp_path / "s.csl"
    path.write_text(style, encoding="utf-8")
    check_style(path)
