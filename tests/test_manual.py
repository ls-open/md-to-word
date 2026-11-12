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


def test_the_thesis_part_ships_in_both_manuals() -> None:
    """学位论文那一部分在手册 §9，中英两版都得有，且小节同构。

    以前它单独成册。合回一份之后，中英两版的小节数必须还对得上，否则译文会悄悄落后一版。
    """
    heads = {}
    for lang, path in MANUALS.items():
        text = path.read_text(encoding="utf-8")
        assert "## 9. " in text, f"{lang} 手册里没有学位论文那一章"
        heads[lang] = [l for l in text.splitlines() if l.startswith("### 9.")]
    assert heads["zh"] and len(heads["zh"]) == len(heads["en"]), (
        f"§9 小节数不同：中文 {len(heads['zh'])}，英文 {len(heads['en'])}"
    )


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
        # Windows 上 --contract 打印的是反斜杠路径，用户看着才正常；比对时统一成正斜杠
        assert path.as_posix() in out.replace("\\", "/"), f"--contract --lang {lang} 没指向 {path.name}"
        for name in ("zh-academic", "en-nature"):
            assert re.search(rf"{name}\s+\S+{name}\.txt", out), f"没给 {name} 预设的路径"


# 章节编号是**对外契约**：技能文档（含另一个仓库里的 nature-paper2word）用 §3.1 / §3.4 /
# §6 / §7 / §8 指路。改手册时随手重排小节，那些指路就会静默指着别的段落，而对方仓库
# 的文档改不动也发现不了。这里把被外部引用的编号钉住。
REFERENCED_SECTIONS = {
    "zh": ["### 3.1 ", "### 3.3 ", "### 3.4 ", "## 6. ", "## 7. ", "## 8. "],
    "en": ["### 3.1 ", "### 3.3 ", "### 3.4 ", "## 6. ", "## 7. ", "## 8. "],
}
# 学位论文那一章同样被外部指路：nature-paper2word 讲底模时让人读封面与前置件那一节。
# 编号一旦挪位，对面仓库读到的就是别的内容，而它自己发现不了。
THESIS_SECTIONS = {"zh": ["### 9.2 "], "en": ["### 9.2 "]}


def test_section_numbers_cited_elsewhere_stay_put() -> None:
    for lang, headings in {**REFERENCED_SECTIONS, **THESIS_SECTIONS}.items():
        text = MANUALS[lang].read_text(encoding="utf-8")
        missing = [h.strip() for h in headings if h not in text]
        assert not missing, f"{lang} 手册缺了对外引用的章节编号：{missing}"


def test_every_flag_is_documented_somewhere() -> None:
    """加了参数却没人写进文档，用户看 `--help` 也只有一行，出了事只能来问。

    这条把「文档跟上代码」变成红灯，而不是指望每次收尾都有人通读四份文档。
    真有故意不写的，加进 DELIBERATELY_HIDDEN 并写清理由。
    """
    import re

    from md_to_word.cli import build_parser

    # 逃生舱：写进文档等于推荐绕过门禁。旧别名：不该再有人学着用。
    DELIBERATELY_HIDDEN = {"--no-audit", "--no-postflight", "--requirements"}
    # 文档里用缩写形式写的那几个
    SHORT_FORM = {"--format": "-f", "--output": "-o"}

    repo_root = Path(md_to_word.__file__).resolve().parents[2]
    corpus = "\n".join([
        (repo_root / "SKILL.md").read_text(encoding="utf-8"),
        (RESOURCES / "manual.md").read_text(encoding="utf-8"),
        (RESOURCES / "manual_en.md").read_text(encoding="utf-8"),
    ])

    flags = sorted({
        opt
        for action in build_parser("zh")._actions
        for opt in action.option_strings
        if opt.startswith("--")
    } - {"--help"} - DELIBERATELY_HIDDEN)

    missing = [
        flag for flag in flags
        if not re.search(re.escape(SHORT_FORM.get(flag, flag)) + r"\b", corpus)
    ]
    assert not missing, f"这些参数没有任何文档提到：{missing}"
