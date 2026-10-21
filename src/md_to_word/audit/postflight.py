"""md_to_word.audit.postflight — 产物数值防丢完整性检查。

确定性比对原稿中的每个三位以上小数，确保在导出的 DOCX 中完整保留，杜绝后处理丢段。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from skill_utils import split_frontmatter

_RE_NUMBER = re.compile(r"\b\d+\.\d{3,}\b")
_RE_YEAR_LIKE = re.compile(r"^20\d{2}\.\d+$")
_RE_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RE_OPENXML_FENCE = re.compile(
    r"^(?:```|~~~)\{=openxml\}.*?^(?:```|~~~)\s*$", re.DOTALL | re.MULTILINE
)


def load_source_text(md_path: Path | str) -> str:
    text = Path(md_path).read_text(encoding="utf-8")
    _, text = split_frontmatter(text)
    text = _RE_HTML_COMMENT.sub(" ", text)
    text = _RE_OPENXML_FENCE.sub(" ", text)
    return text


def extract_numbers(text: str) -> set[str]:
    return {n for n in _RE_NUMBER.findall(text) if not _RE_YEAR_LIKE.match(n)}


def docx_text(docx_path: Path | str) -> str:
    with zipfile.ZipFile(docx_path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    return " ".join(re.findall(r"<[wm]:t[^>]*>([^<]*)</[wm]:t>", xml))


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
