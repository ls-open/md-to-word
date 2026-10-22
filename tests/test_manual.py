"""包内手册是"没有技能文档时"的唯一入口，必须自足且不落伍。

三条底线：文件真的在包里、词表与代码同源、`--contract` 能把人送到手册跟前。
再加一条防腐：手册里不许出现只在仓库里存在的路径（`references/`、`demo/`、`scripts/`）——
那对 pip 用户是死链。
"""

from __future__ import annotations

import re
from pathlib import Path

import md_to_word
from md_to_word.cli import contract_cheatsheet
from md_to_word.spec.constants import STYLE_MAP

MANUAL = Path(md_to_word.__file__).resolve().parent / "resources" / "manual.md"
REPO_ONLY = ("references/", "demo/", "scripts/", "tests/")


def manual_path() -> Path:
    return MANUAL


def test_manual_ships_inside_the_package() -> None:
    path = manual_path()
    assert path.is_file(), f"手册没随包发布: {path}"
    text = path.read_text(encoding="utf-8")
    assert len(text.splitlines()) > 200, "手册被削得太薄，已不足以替掉旧的参考文档"


def test_manual_lists_every_style_name() -> None:
    """样式名是封闭词表。词表改了、手册没改，写稿的人照着手册就会写错。"""
    text = manual_path().read_text(encoding="utf-8")
    missing = [cn for cn in STYLE_MAP if not cn.isascii() and cn not in text]
    assert not missing, f"这些样式名没写进手册：{missing}"


def test_manual_documents_the_block_markers() -> None:
    text = manual_path().read_text(encoding="utf-8")
    for marker in ("pagebreak", "toc", "section"):
        assert f"{{{{< {marker}" in text, f"手册没写 {marker} 标记"


def test_manual_has_no_repository_only_paths() -> None:
    text = manual_path().read_text(encoding="utf-8")
    found = [p for p in REPO_ONLY if p in text]
    assert not found, f"手册里出现了只有仓库才有的路径：{found}"


def test_contract_points_at_real_files() -> None:
    """`--contract` 的全部价值在于给出真实路径：路径不存在的输出等于没说。"""
    out = contract_cheatsheet()
    assert manual_path().as_posix() in out
    for name in ("zh-academic", "en-nature"):
        assert re.search(rf"{name}\s+\S+{name}\.txt", out), f"没给 {name} 预设的路径"
