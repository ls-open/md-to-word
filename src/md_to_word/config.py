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


# 稿件没写 `csl:` 时的兜底引文样式。**两条写出通道必须用同一份**：Pandoc 未收到 csl
# 时会用自己内置的芝加哥作者-年份制，自研写出器若另选一套，同一份稿子换个后端就换出
# 两种文献表——这是对拍里最不该出现的差异。
DEFAULT_CSL_ZH = "chinese-gb7714-2015-numeric.csl"
DEFAULT_CSL_EN = "apa.csl"


def default_csl_path(text: str) -> Path:
    """按稿件的字种挑默认 CSL：中文稿走 GB/T 7714 数字制，其余走 APA。"""
    dark = sum(1 for ch in text if "一" <= ch <= "鿿")
    dense = sum(1 for ch in text if not ch.isspace())
    name = DEFAULT_CSL_ZH if dense and dark / dense > 0.05 else DEFAULT_CSL_EN
    return get_csl_dir() / name
