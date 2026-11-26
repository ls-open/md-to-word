"""发版脚本列出的样例必须真的存在、真的能按声明的方式导出。

上次新增 05/06 时，DEMOS 里把没有 `format.txt` 的目录写成了 `format.txt`，
又把需要专用预设的两份写成了 `-`；发版脚本会到发版当天才失败，或者更糟：
用错预设重出一份“看起来正常”的成品，把已提交的样例覆盖掉。
"""

from __future__ import annotations

import re
from pathlib import Path

from md_to_word.config import get_presets_dir

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE = (REPO_ROOT / "scripts" / "release.sh").read_text(encoding="utf-8")


def _demo_rows() -> list[tuple[str, str, str, str]]:
    block = RELEASE.split("DEMOS=(", 1)[1].split("\n)", 1)[0]
    rows = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'^"(\S+)\s+(\S+)\s+(\S+)\s+(\S+)"$', line)
        assert m, line
        rows.append(tuple(m.groups()))
    return rows


def test_release_demos_exist_and_name_a_real_source() -> None:
    rows = _demo_rows()
    assert len(rows) == 7

    presets = {path.stem for path in get_presets_dir().glob("*.txt")}
    for directory, _stem, manuscript, source in rows:
        demo = REPO_ROOT / "demo" / directory
        assert (demo / manuscript).is_file(), f"{directory} 缺少稿件 {manuscript}"
        if source == "-":
            continue
        if source.startswith("preset:"):
            assert source.removeprefix("preset:") in presets, f"{directory} 的预设不存在：{source}"
        else:
            assert (demo / source).is_file(), f"{directory} 缺少来源文件 {source}"
