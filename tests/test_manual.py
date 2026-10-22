"""包内手册是"没有技能文档时"的唯一入口，必须自足且不落伍。

三条底线：文件真的在包里、词表与代码同源、`--contract` 能把人送到手册跟前。
再加两条防腐：手册里不许出现只在仓库里存在的路径（`references/`、`demo/`、`scripts/`）——
那对 pip 用户是死链；中英两份手册必须覆盖同一批结构，否则译文会悄悄落后一版。
"""

from __future__ import annotations

import re
from pathlib import Path

import md_to_word
from md_to_word.cli import contract_cheatsheet
from md_to_word.config import get_csl_dir
from md_to_word.spec.constants import STYLE_MAP

RESOURCES = Path(md_to_word.__file__).resolve().parent / "resources"
MANUALS = {"zh": RESOURCES / "manual.md", "en": RESOURCES / "manual_en.md"}
REPO_ONLY = ("references/", "demo/", "scripts/", "tests/")
YAML_KEYS = ("bibliography", "csl", "crossref", "link-citations")
BLOCK_MARKERS = ("pagebreak", "toc", "section")
# `csl: apa.csl` 这类反引号里的文件名；§7 清单是唯一真相源
CSL_REF = re.compile(r"`([a-z0-9\-]+\.csl)`")


def manual_path(lang: str = "zh") -> Path:
    return MANUALS[lang]


def _section(text: str, start: str, end: str) -> str:
    """取 `start` 到 `end` 之间的正文；找不到就抛，说明章节编号被改动了。"""
    begin = text.index(start)
    return text[begin : text.index(end, begin)]


def _styles_in(section: str, ascii_only: bool) -> set[str]:
    """这一段里出现的样式（按 Word 内部名去重）。

    只认整词：`Title` 不该被 `Abstract Title` 顺带算作「写了」。
    """
    return {
        target
        for name, target in STYLE_MAP.items()
        if name.isascii() == ascii_only
        and re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", section)
    }


def test_manual_ships_inside_the_package() -> None:
    for lang, path in MANUALS.items():
        assert path.is_file(), f"{lang} 手册没随包发布: {path}"
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) > 200, f"{lang} 手册被削得太薄，已不足以替掉旧的参考文档"


def test_manual_lists_every_style_name() -> None:
    """样式名是封闭词表。词表改了、手册没改，写稿的人照着手册就会写错。"""
    text = manual_path().read_text(encoding="utf-8")
    missing = [cn for cn in STYLE_MAP if not cn.isascii() and cn not in text]
    assert not missing, f"这些样式名没写进手册：{missing}"


def test_both_manuals_cover_the_same_style_names() -> None:
    """两份手册的 §3.4 必须覆盖同一批样式：中文版查中文名，英文版查英文名。"""
    all_targets = set(STYLE_MAP.values())
    for lang, ascii_only in (("zh", False), ("en", True)):
        section = _section(MANUALS[lang].read_text(encoding="utf-8"), "### 3.4", "### 3.5")
        covered = _styles_in(section, ascii_only)
        missing = sorted(all_targets - covered)
        assert not missing, f"{lang} 手册 §3.4 漏了这些样式：{missing}"


def test_both_manuals_document_the_same_structure() -> None:
    """短代码与 YAML 键是结构事实，译文少写一条就等于承诺少了一条。"""
    for lang, path in MANUALS.items():
        text = path.read_text(encoding="utf-8")
        for marker in BLOCK_MARKERS:
            assert f"{{{{< {marker}" in text, f"{lang} 手册没写 {marker} 标记"
        for key in YAML_KEYS:
            assert f"`{key}:" in text, f"{lang} 手册没写 YAML 键 {key}:"


def test_both_manuals_list_the_same_csl_inventory() -> None:
    on_disk = {p.name for p in get_csl_dir().glob("*.csl")}
    listed = {
        lang: set(CSL_REF.findall(path.read_text(encoding="utf-8")))
        for lang, path in MANUALS.items()
    }
    assert listed["zh"], "中文手册没列任何 CSL 样式"
    assert listed["zh"] == listed["en"], (
        f"两份手册的 CSL 清单不一致：仅中文有 {sorted(listed['zh'] - listed['en'])}，"
        f"仅英文有 {sorted(listed['en'] - listed['zh'])}"
    )
    assert listed["en"] == on_disk, f"英文手册与包内 CSL 目录不一致：{sorted(on_disk - listed['en'])}"


def test_manuals_have_no_repository_only_paths() -> None:
    for lang, path in MANUALS.items():
        text = path.read_text(encoding="utf-8")
        found = [p for p in REPO_ONLY if p in text]
        assert not found, f"{lang} 手册里出现了只有仓库才有的路径：{found}"


def test_contract_points_at_real_files() -> None:
    """`--contract` 的全部价值在于给出真实路径：路径不存在的输出等于没说。"""
    for lang in MANUALS:
        out = contract_cheatsheet(lang)
        path = manual_path(lang)
        assert path.is_file(), f"{lang} 手册不存在: {path}"
        assert path.as_posix() in out, f"--contract --lang {lang} 没指向 {path.name}"
        for name in ("zh-academic", "en-nature"):
            assert re.search(rf"{name}\s+\S+{name}\.txt", out), f"没给 {name} 预设的路径"
