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
    # 目录空了就是打包坏了；数量也必须和 README/手册里的「29 套」对上。
    assert len(styles) == 29, f"内置 CSL 数量异常：{len(styles)}"
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


def test_display_indent_is_rejected_instead_of_silently_dropping_indent(
    tmp_path: Path,
) -> None:
    """只换行不加缩进，和样式要求的 `display="indent"` 不是一回事。"""
    style = _style('<group display="indent"><text variable="title"/></group>')
    with pytest.raises(CitationError) as caught:
        _engine(tmp_path, style)
    assert 'display="indent"' in str(caught.value)


@pytest.mark.parametrize("rule", ["all-names", "all-names-with-initials"])
def test_all_names_disambiguation_is_rejected_until_implemented(
    tmp_path: Path, rule: str
) -> None:
    """内置样式用 primary-name；all-names 需要给所有作者判重，当前没有实现。"""
    style = _style('<text variable="title"/>').replace(
        "<citation>", f'<citation givenname-disambiguation-rule="{rule}">')
    with pytest.raises(CitationError) as caught:
        _engine(tmp_path, style)
    assert rule in str(caught.value)


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
