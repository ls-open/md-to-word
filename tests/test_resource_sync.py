"""预设与资源两份拷贝必须一致（手册除外）。

技能按目录分发（`presets/`、`resources/` 在仓库根），pip 安装则用包内的同名目录
（`src/md_to_word/presets/`、`src/md_to_word/resources/`）。同一份事实两处存放，
改一份忘另一份就会「本地跑对、装完跑错」。

为什么不用软链接合并：本技能要在 Windows 上跑，而 Windows 的 git checkout 默认
不落软链接。既然只能存两份，就让测试盯着它们不许分叉。

`resources/manual.md` 是唯一例外：使用手册只随包发布，仓库根不放副本——它必须与代码
同一个版本，而仓库根那份既没人读，也没人负责同步。
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
PACKAGE_ONLY = {"manual.md"}


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
