"""md_to_word.config — 配置与资源路径解析器。

提供预设目录、CSL 目录、基础模板等的统一定位逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# 包所在目录
PACKAGE_DIR = Path(__file__).resolve().parent

# 工作区/工程根目录（根据包所在目录推导）
WORKSPACE_DIR = PACKAGE_DIR.parent.parent


def get_presets_dir() -> Path:
    """获取预设目录 presets/。优先包内，兜底工程根目录。"""
    pkg_presets = PACKAGE_DIR / "presets"
    if pkg_presets.is_dir():
        return pkg_presets
    root_presets = WORKSPACE_DIR / "presets"
    if root_presets.is_dir():
        return root_presets
    return root_presets


def get_resources_dir() -> Path:
    """获取资源目录 resources/。优先包内，兜底工程根目录。"""
    pkg_res = PACKAGE_DIR / "resources"
    if pkg_res.is_dir():
        return pkg_res
    root_res = WORKSPACE_DIR / "resources"
    if root_res.is_dir():
        return root_res
    return root_res


def get_csl_dir() -> Path:
    """获取 CSL 样式文件目录 resources/csl/。"""
    res_dir = get_resources_dir()
    csl = res_dir / "csl"
    if csl.is_dir():
        return csl
    # 兼容直接平铺的情况
    return csl


def get_base_template_path() -> Path:
    """获取纯净现代底模 pure_modern_base.docx。"""
    return get_resources_dir() / "pure_modern_base.docx"


def resolve_preset_path(preset_name: str) -> Optional[Path]:
    """根据预设名称（如 zh-academic、en-nature）返回预设文件路径。"""
    clean_name = preset_name.strip().removesuffix(".txt")
    presets_dir = get_presets_dir()
    target = presets_dir / f"{clean_name}.txt"
    if target.is_file():
        return target
    return None
