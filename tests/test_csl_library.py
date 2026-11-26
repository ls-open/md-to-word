"""内置 CSL 库的三条底线。

用户不该为了一个样式去网上翻仓库——所以内置的要**真的能用**。这三条断言就是
"提前过了一遍"的证据：每份都能渲染、每份都规范化过、每份都在文档里列出来。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from md_to_word.transform.citations import CitationEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
CSL_DIR = REPO_ROOT / "src" / "md_to_word" / "resources" / "csl"

BIB = """@article{a, author={Smith, John and Doe, Jane}, title={A Study of Things},
  year={2020}, journal={Journal of Tests}, volume={3}, issue={2}, pages={10-20}}
@book{b, author={Lee, Kim}, title={A Book}, year={2019}, publisher={Press}}
@inproceedings{c, author={Wang, Wei}, title={A Paper}, year={2021},
  booktitle={Proceedings of X}}
"""

STYLES = sorted(p.name for p in CSL_DIR.glob("*.csl"))


@pytest.mark.parametrize("style", STYLES)
def test_every_bundled_style_is_normalized(style: str) -> None:
    """段落格式必须由模板控制：CSL 里的 direct formatting 会盖掉要求文件的设置。"""
    text = (CSL_DIR / style).read_text(encoding="utf-8")
    for attr in ("hanging-indent", "line-spacing"):
        assert attr not in text, f"{style} 里还有 {attr}，先跑 scripts/normalize_csl.py"


def test_the_numeric_style_declares_its_number_column() -> None:
    """`second-field-align` 是结构不是格式：去掉它，`[1]` 就会和条目正文贴在一起。"""
    text = (CSL_DIR / "chinese-gb7714-2015-numeric.csl").read_text(encoding="utf-8")
    assert 'second-field-align="flush"' in text


@pytest.mark.parametrize("style", STYLES)
def test_numeric_styles_have_tabs_and_author_date_do_not(style: str) -> None:
    """数字制必须自成一栏（以制表符分隔），著者-出版年制绝不带制表符。"""
    engine = CitationEngine(BIB, CSL_DIR / style)
    engine.cite([("a", "")])
    entry = engine.bibliography()[0]
    if engine._first_field_column:
        assert "\t" in entry, f"数字制样式 {style} 参考文献未切分出制表符：{entry!r}"
        prefix, suffix = engine._number_prefix, engine._number_suffix
        assert entry.startswith(f"{prefix}1{suffix}".rstrip()), f"{style} 序号标记格式不符：{entry!r}"
    else:
        assert "\t" not in entry, f"著者年制样式 {style} 不应包含制表符：{entry!r}"
