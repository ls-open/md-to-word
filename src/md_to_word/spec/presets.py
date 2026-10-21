"""md_to_word.spec.presets — 内置预设管理。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from md_to_word.config import get_presets_dir, resolve_preset_path


def list_available_presets() -> list[str]:
    """列出当前可用的全部预设名（不含 .txt 后缀）。"""
    presets_dir = get_presets_dir()
    if not presets_dir.is_dir():
        return []
    return sorted(p.stem for p in presets_dir.glob("*.txt"))


def read_preset_content(preset_name: str) -> Optional[str]:
    """读取指定预设的内容文本。"""
    p = resolve_preset_path(preset_name)
    if p and p.is_file():
        return p.read_text(encoding="utf-8")
    return None
