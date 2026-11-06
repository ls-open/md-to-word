"""外面稿子里常见的写法：能映射的就映射，映射不了的当场拦下。

判据只有两条——**能无损翻译的就翻**（带 title 的链接、HTML 实体、`...` 结尾的 YAML），
**翻不了的就拦住**（引用式链接、自动链接、远程图片），绝不原样印进 Word。
"""

from __future__ import annotations

from pathlib import Path

from md_to_word.model.reader import parse_inlines
from md_to_word.utils.skill_utils import (
    citations_without_bibliography, dialect_issues, split_frontmatter,
)


def test_a_link_title_is_parsed_not_printed() -> None:
    nodes = parse_inlines('See [docs](https://example.com "Docs").')
    assert [type(n).__name__ for n in nodes] == ["Text", "Link", "Text"]
    assert nodes[1].url == "https://example.com"


def test_html_entities_are_decoded() -> None:
    assert parse_inlines("Copyright &copy; 2024 &amp; more.")[0].value == "Copyright © 2024 & more."


def test_entities_inside_code_stay_literal() -> None:
    """反引号里是逐字内容，解码会把作者写的 `&amp;` 变掉。"""
    nodes = parse_inlines("写 `&amp;` 表示与号")
    assert any(getattr(n, "value", "") == "&amp;" for n in nodes)


def test_frontmatter_may_end_with_three_dots() -> None:
    front, body = split_frontmatter("---\nbibliography: r.bib\n...\n\n# 标题\n")
    assert "bibliography" in front and body.strip() == "# 标题"


def test_reference_links_are_refused_not_printed() -> None:
    text = "See [the docs][docs].\n\n[docs]: https://example.com/docs\n"
    lines = [line for line, _ in dialect_issues(text)]
    assert lines == [1, 3], lines


def test_a_footnote_definition_is_not_a_reference_link() -> None:
    assert dialect_issues("正文[^1]。\n\n[^1]: 注释。\n") == []


def test_wikilinks_inside_a_code_fence_are_data() -> None:
    assert dialect_issues("# 标题\n\n```\n[[foo]]\n```\n") == []


def test_an_email_autolink_is_not_a_citation() -> None:
    assert citations_without_bibliography("见 <foo\\+@bar.example.com>。") == []
    assert citations_without_bibliography("见 [@smith2020]。") == [1]
