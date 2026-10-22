"""内置 CSL 库的三条底线。

用户不该为了一个样式去网上翻仓库——所以内置的要**真的能用**。这三条断言就是
"提前过了一遍"的证据：每份都能渲染、每份都规范化过、每份都在文档里列出来。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from md_to_word.config import get_csl_dir
from md_to_word.transform.citations import CitationEngine

REPO_ROOT = Path(__file__).resolve().parents[1]
CSL_DIR = REPO_ROOT / "resources" / "csl"
REFERENCE = REPO_ROOT / "references" / "reference.md"

BIB = """@article{a, author={Smith, John and Doe, Jane}, title={A Study of Things},
  year={2020}, journal={Journal of Tests}, volume={3}, issue={2}, pages={10-20}}
@book{b, author={Lee, Kim}, title={A Book}, year={2019}, publisher={Press}}
@inproceedings{c, author={Wang, Wei}, title={A Paper}, year={2021},
  booktitle={Proceedings of X}}
"""

STYLES = sorted(p.name for p in CSL_DIR.glob("*.csl"))


@pytest.mark.parametrize("style", STYLES)
def test_every_bundled_style_renders(style: str) -> None:
    """每份内置样式都要能渲染三条样例——citeproc-py 不支持的写法会在这里炸出来。"""
    engine = CitationEngine(BIB, CSL_DIR / style)
    engine.cite([("a", ""), ("b", ""), ("c", "")])
    entries = engine.bibliography()
    assert len(entries) == 3, f"{style} 渲染出 {len(entries)} 条"
    assert all(text.strip() for text in entries), f"{style} 有空白条目"


@pytest.mark.parametrize("style", STYLES)
def test_every_bundled_style_is_normalized(style: str) -> None:
    """段落格式必须由模板控制：CSL 里的 direct formatting 会盖掉要求文件的设置。"""
    text = (CSL_DIR / style).read_text(encoding="utf-8")
    for attr in ("hanging-indent", "second-field-align", "line-spacing"):
        assert attr not in text, f"{style} 里还有 {attr}，先跑 scripts/normalize_csl.py"


def test_package_copy_matches_repository_copy() -> None:
    package_dir = get_csl_dir()
    assert sorted(p.name for p in package_dir.glob("*.csl")) == STYLES


def test_reference_manual_lists_every_style() -> None:
    """文档与目录一一对应：加了文件忘写、或删了文件忘改，都会在这里红。"""
    documented = set(re.findall(r"`([a-z0-9\-]+\.csl)`", REFERENCE.read_text(encoding="utf-8")))
    documented = {name for name in documented if (CSL_DIR / name).exists()}
    missing = sorted(set(STYLES) - documented)
    assert not missing, f"这些样式没写进 references/reference.md §3：{missing}"
