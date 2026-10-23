"""预设与资源两份拷贝必须一致（手册除外）。

技能按目录分发（`presets/`、`resources/` 在仓库根），pip 安装则用包内的同名目录
（`src/md_to_word/presets/`、`src/md_to_word/resources/`）。同一份事实两处存放，
改一份忘另一份就会「本地跑对、装完跑错」。

为什么不用软链接合并：本技能要在 Windows 上跑，而 Windows 的 git checkout 默认
不落软链接。既然只能存两份，就让测试盯着它们不许分叉。

`resources/manual.md` / `resources/manual_en.md` 是唯一例外：使用手册只随包发布，仓库根
不放副本——它必须与代码同一个版本，而仓库根那份既没人读，也没人负责同步。
"""

from __future__ import annotations

import filecmp
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT_PRESETS = REPO_ROOT / "presets"
ROOT_RESOURCES = REPO_ROOT / "resources"
PKG_PRESETS = REPO_ROOT / "src" / "md_to_word" / "presets"
PKG_RESOURCES = REPO_ROOT / "src" / "md_to_word" / "resources"


# 只随包发布、仓库根不放副本的文件
PACKAGE_ONLY = {"manual.md", "manual_en.md", "guide.md", "render_via_word.sh"}


def _relative_files(root: Path) -> set[str]:
    return {
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.name not in PACKAGE_ONLY
    }


@pytest.mark.parametrize(
    ("root", "package", "label"),
    [
        (ROOT_PRESETS, PKG_PRESETS, "presets"),
        (ROOT_RESOURCES, PKG_RESOURCES, "resources"),
    ],
)
def test_copies_are_identical(root: Path, package: Path, label: str) -> None:
    root_files = _relative_files(root)
    package_files = _relative_files(package)
    assert root_files == package_files, (
        f"{label}/ 与 {package.relative_to(REPO_ROOT)}/ 的文件清单不一致："
        f"仅根目录有 {sorted(root_files - package_files)}，"
        f"仅包内有 {sorted(package_files - root_files)}"
    )

    _, mismatch, errors = filecmp.cmpfiles(
        root, package, sorted(root_files), shallow=False
    )
    assert not errors, f"{label}/ 有文件无法比较：{errors}"
    assert not mismatch, f"{label}/ 与包内拷贝内容不一致：{mismatch}"


def test_packaged_guide_is_the_skill_entry() -> None:
    """只装了 pip 包的 Agent 也要有“先读哪一份”的入口。

    技能入口是仓库根的 `SKILL.md`（带 frontmatter），包内是同一份正文的 `guide.md`。
    两处内容必须一字不差，否则 pip 用户读到的流程与技能用户读到的会分叉。
    """
    skill = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    body = skill.split("---", 2)[2].lstrip("\n")
    guide = (PKG_RESOURCES / "guide.md").read_text(encoding="utf-8")
    assert guide == body, "SKILL.md 正文与包内 guide.md 不一致：改了一处要同步另一处"


def test_skill_frozen_surface_exists_in_the_code() -> None:
    """技能文件里的「版本契约」必须兑现：写了要冻结的东西，代码里就得真有。

    这份技能会被拷进别人的 `~/.claude/skills`，`pip install -U` 不会更新它。所以它列进
    §8 的每一样都是承诺——命令、参数、退出码、预设名、`format.txt`。承诺与实现对不上时，
    用户看到的是「按文档敲，命令不存在」，而我们要等下一次有人手动去翻才会知道。
    """
    import re

    from md_to_word.cli import build_parser
    from md_to_word.config import resolve_preset_path

    text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
    section = text[text.index("## 8. Version contract"):]

    parser = build_parser("zh")
    known = {opt for action in parser._actions for opt in action.option_strings}
    flags = set(re.findall(r"`(--[a-z][a-z0-9-]+)`", section))
    assert flags, "§8 没列出任何参数"
    missing_flags = sorted(flags - known - {"--force"})   # --force 属于 init 子命令
    assert not missing_flags, f"§8 冻结的参数在 CLI 里不存在：{missing_flags}"

    for preset in ("zh-academic", "en-nature"):
        assert f"`{preset}`" in section, f"§8 没冻结预设名 {preset}"
        path = resolve_preset_path(preset)
        assert path is not None and path.is_file(), f"预设 {preset} 解析不到文件"

    assert "`format.txt`" in section
    assert "`init`" in section and "md-to-word init" in text
