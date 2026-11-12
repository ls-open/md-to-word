"""md_to_word.audit.postflight — 产物防丢完整性检查。

两样东西原稿有、产物就必须有：三位以上的小数，和每一个汉字。前者是精度，后者是内容——
两者丢了产物都看着正常，退出码也还是 0。
"""

from __future__ import annotations

import re
import zipfile
from collections import Counter
from pathlib import Path
from md_to_word.utils.masking import HTML_COMMENT_RE
from md_to_word.utils.skill_utils import split_frontmatter

_RE_NUMBER = re.compile(r"\b\d+\.\d{3,}\b")
_RE_YEAR_LIKE = re.compile(r"^20\d{2}\.\d+$")
_RE_OPENXML_FENCE = re.compile(
    r"^(?:```|~~~)\{=openxml\}.*?^(?:```|~~~)\s*$", re.DOTALL | re.MULTILINE
)


def load_source_text(md_path: Path | str) -> str:
    text = Path(md_path).read_text(encoding="utf-8")
    _, text = split_frontmatter(text)
    for pattern in (HTML_COMMENT_RE, _RE_OPENXML_FENCE, _RE_IMAGE):
        text = pattern.sub(" ", text)
    return text


def extract_numbers(text: str) -> set[str]:
    return {n for n in _RE_NUMBER.findall(text) if not _RE_YEAR_LIKE.match(n)}


_RE_CJK = re.compile(r"[㐀-䶿一-鿿]")
# 下面几条都在**去掉对文字的硬性要求**，方向只会让检查更松，不会误报
_RE_SHORTCODE = re.compile(r"\{\{<.*?>\}\}", re.DOTALL)   # 短码参数是指令，不落成文字
_RE_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")           # 替代文字进 descr、路径进关系，都不在正文
_RE_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")           # 链接留文字、丢地址
_RE_LABEL = re.compile(r"\{#[^}]*\}")
_RE_CITE = re.compile(r"@[\w:.\-]+")                        # 引用键渲染成 [1]
_RE_STYLE_LINE = re.compile(r"^(\s*)%%\s*\S+", re.MULTILINE)  # `%% 表题 …` 里那个词是指令
_RE_UNLISTED_ATTR = re.compile(
    r"^(\s*#{1,6}\s+\S[^\n]*?)\s*\{(?:\.unlisted|不入目录)\}\s*$", re.MULTILINE
)
_RE_FENCE_INFO = re.compile(r"^\s*(?:```|~~~)[^\n]*$", re.MULTILINE)


def verify_chinese_integrity(md_path: Path | str, docx_path: Path | str) -> tuple[bool, list[str]]:
    """原稿里的汉字，产物里一个都不能少。返回 (是否齐全, 缺的字)。

    只比汉字：字母数字在公式、文献库、URL 里本来就该变形，比不出结论；汉字是纯内容。
    也是只查"少"不查"多"——目录、图题、编号都是引擎加上去的。
    """
    wanted = Counter(_RE_CJK.findall(_source_for_chinese(md_path)))
    if not wanted:
        return True, []
    rendered = Counter(_RE_CJK.findall(docx_text(docx_path)))
    missing = wanted - rendered
    return not missing, sorted(missing.elements())


def _source_for_chinese(md_path: Path | str) -> str:
    text = load_source_text(md_path)
    for pattern, repl in ((_RE_SHORTCODE, " "), (_RE_LINK, r"\1"),
                          (_RE_LABEL, " "), (_RE_CITE, " "),
                          (_RE_STYLE_LINE, r"\1"), (_RE_UNLISTED_ATTR, r"\1"),
                          (_RE_FENCE_INFO, "")):
        text = pattern.sub(repl, text)
    return text


def docx_text(docx_path: Path | str) -> str:
    """正文 + 脚注 + 尾注的文字。脚注不在 document.xml 里，漏了就会把注释里的数字误判为丢失。

    页眉页脚**不算**：它们的内容来自要求文件而不是稿件，算进来只会让「正文里真的丢了
    一个数字」被页眉上恰好相同的数字盖过去——这是把闸门放松，不是修误报。
    """
    parts = []
    with zipfile.ZipFile(docx_path) as z:
        for name in z.namelist():
            if name == "word/document.xml" or name.startswith(("word/footnotes", "word/endnotes")):
                try:
                    xml = z.read(name).decode("utf-8")
                    parts.extend(re.findall(r"<[wm]:t[^>]*>([^<]*)</[wm]:t>", xml))
                except Exception:
                    pass
    return " ".join(parts)


def verify_numeric_integrity(
    md_path: Path | str, docx_path: Path | str
) -> tuple[bool, list[str]]:
    """比对原稿与产物中的高精度小数。返回 (是否全部保留, 丢失的数字列表)。"""
    md_p, docx_p = Path(md_path), Path(docx_path)
    wanted = extract_numbers(load_source_text(md_p))
    if not wanted:
        return True, []

    rendered = docx_text(docx_p)
    missing = sorted(n for n in wanted if n not in rendered)
    return len(missing) == 0, missing
