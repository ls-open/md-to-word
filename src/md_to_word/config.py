"""md_to_word.config — 配置与资源路径解析器。

提供预设目录、CSL 目录、基础模板等的统一定位逻辑。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# 包所在目录
PACKAGE_DIR = Path(__file__).resolve().parent

# 内置预设名：不传 -f 时按稿件语种二选一。名字只在这里写一次，
# 命令、提示与 `init` 都从这里取。
DEFAULT_PRESET_ZH = "zh-academic"
DEFAULT_PRESET_EN = "en-nature"


def default_preset_name(lang: str) -> str:
    """按**稿件语言**取默认预设。消息语言（`--lang`）不参与这个判断。"""
    return DEFAULT_PRESET_ZH if lang == "zh" else DEFAULT_PRESET_EN


def get_presets_dir() -> Path:
    """包内预设目录 presets/。预设与资源都只随包发布，仓库里没有第二份。"""
    return PACKAGE_DIR / "presets"


def get_resources_dir() -> Path:
    """包内资源目录 resources/（CSL、底模、手册）。"""
    return PACKAGE_DIR / "resources"


def get_csl_dir() -> Path:
    """获取 CSL 样式文件目录 resources/csl/。"""
    return get_resources_dir() / "csl"


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


# 稿件没写 `csl:` 时的兜底引文样式。默认值必须**可预期**：同一份稿子今天与明天导出，
# 文献表要一样长、一样排。
DEFAULT_CSL_ZH = "chinese-gb7714-2015-numeric.csl"
DEFAULT_CSL_EN = "apa.csl"


# 常见「只有繁体才这么写」的字。不是完整的简繁对照表，只用来在自动选预设前
# 提醒一句：简体稿里偶尔出现一两个（人名、书名）很常见，所以要求至少命中 3 个不同字。
_TRADITIONAL_HINTS = set(
    "學術確體這說與為來時會開關實應個們無發經對問題國專業務員動產權畫點數變還進遠運過達"
    "選鄉醫藥車東馬鳥魚龍龜臺灣澳門網路資訊軟硬體設計師錯誤處理檔案編輯器標準規範"
)


def looks_traditional(text: str) -> bool:
    """正文是否明显是繁体中文（只用于提醒，不改变默认预设）。"""
    seen = {ch for ch in (text or "") if ch in _TRADITIONAL_HINTS}
    return len(seen) >= 3


def looks_chinese(text: str, threshold: float = 0.05) -> bool:
    """正文是不是中文写的。

    只数**自然语言正文**里的汉字占比：`%% 表题`、`%% 图片题注` 这些样式名是词表的一部分，
    英文稿里也会出现；代码、frontmatter、URL、公式与引文键同样不是正文。中文技术稿里
    夹着大段英文代码时，代码不该把中文稿判成英文稿。行首 `%%` 的行整行跳过。
    """
    from md_to_word.utils.masking import mask_prose_noise

    text = mask_prose_noise(text or "")
    lines = [line for line in text.split("\n") if not line.lstrip().startswith("%%")]
    # `mask_prose_noise` uses "." as a placeholder; it must not dilute the ratio.
    dense = [ch for ch in "".join(lines) if not ch.isspace() and ch != "."]
    if not dense:
        return False
    cjk = sum(1 for ch in dense if "\u4e00" <= ch <= "\u9fff")
    return cjk / len(dense) > threshold


def lang_from_proofing(value: Optional[str]) -> Optional[str]:
    """格式文件的 `校对语言：` → 文档语言（`zh` / `en`）。

    格式文件一旦显式声明了语言，它就是这份文档的语言；稿件里夹一段中文引文或英文附录
    不该把它翻过去。没有声明时才按正文判定。
    """
    if not value:
        return None
    return "en" if str(value).strip().lower().startswith("en") else "zh"


def default_csl_path_for_lang(lang: str) -> Path:
    """按文档语言挑默认 CSL：中文走 GB/T 7714 数字制，其余走 APA。"""
    return get_csl_dir() / (DEFAULT_CSL_ZH if lang == "zh" else DEFAULT_CSL_EN)


def default_csl_path(text: str) -> Path:
    """按稿件的字种挑默认 CSL（没有格式语言可依据时的兜底）。"""
    return default_csl_path_for_lang("zh" if looks_chinese(text) else "en")


def default_crossref_prefixes(chinese: bool) -> dict[str, str]:
    """交叉引用前缀的默认值：`@eq-a` 该长成「式1」还是「Equation 1」。"""
    if chinese:
        return {"eq-prefix": "式"}
    return {"eq-prefix": "Equation "}
