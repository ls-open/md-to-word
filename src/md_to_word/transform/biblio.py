"""md_to_word.transform.biblio — 文献库入口：BibTeX / BibLaTeX 与 CSL-JSON。

`.bib` 与 CSL-JSON 在 YAML 里是同一个键（`bibliography:`），区别只在文件内容。
判断放这里一处：管道、预检、引文引擎都走同一个入口，不各认各的扩展名——
扩展名不可靠（`.json` 里放 BibTeX、`.bib` 里放 JSON 都见过），内容才可靠。

CSL-JSON 是 Zotero / Mendeley / Crossref 直接导出的格式；本工具内部本来就把 `.bib`
转成 CSL-JSON 条目，所以这条输入路径只是把「转换」换成「直接读」。
"""

from __future__ import annotations

import json
from typing import Any, Optional

from md_to_word.i18n import t
from md_to_word.transform.bibtex import parse_bibtex


class BiblioError(ValueError):
    """文献库无法解析。消息已按语言排好，可直接给用户看。"""


def looks_like_csl_json(text: str) -> bool:
    """JSON 的顶层只可能是数组或对象；BibTeX 以 `@` 开头，两者不会混。"""
    stripped = (text or "").lstrip()
    return stripped.startswith("[") or stripped.startswith("{")


def parse_csl_json(text: str, lang: str = "en") -> list[dict[str, Any]]:
    """CSL-JSON → 条目列表。接受裸数组，也接受 `{"items": [...]}` 包装。"""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BiblioError(t("biblio.json_invalid", lang, reason=str(exc))) from exc

    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise BiblioError(t("biblio.json_shape", lang))

    entries: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise BiblioError(t("biblio.json_item", lang))
        key = item.get("id")
        if not isinstance(key, str) or not key.strip():
            raise BiblioError(t("biblio.json_id", lang))
        entry = dict(item)
        entry["id"] = key.strip()
        entry.setdefault("type", "article")
        entries.append(entry)

    # 空库不在这里拦：没有引用时它无害，有引用时由预检报「文献库里没有条目」。
    # 空 `.bib` 走的是同一条路，两种格式不能一个静默通过、一个直接失败。
    return entries


def parse_bibliography(text: str, lang: str = "en") -> list[dict[str, Any]]:
    """按内容分派：JSON 走 CSL-JSON，其余按 BibTeX/BibLaTeX。"""
    if looks_like_csl_json(text):
        return parse_csl_json(text, lang)
    return parse_bibtex(text)


def bibliography_problem(text: str, lang: str = "en") -> Optional[str]:
    """能读就说 None，不能读就返回一句可显示的原因。

    预检与导出共用：同一种坏文献库不该在一个出口是「文献库为空」、另一个是 traceback。
    JSON 解析会真正失败；两种格式都要检查**重复 key**——引擎只会保留其中一条，
    而 `[1]` 到底指向哪一条，用户从成品上看不出来。
    """
    try:
        entries = parse_bibliography(text, lang)
    except BiblioError as exc:
        return str(exc)
    except Exception:
        # BibTeX 解析器是宽容的：读不动就交给后续的「键不存在」等检查，
        # 不在这里把它误报成格式错误。
        return None
    seen: set[str] = set()
    duplicates: list[str] = []
    for entry in entries:
        key = str(entry.get("id") or "")
        if not key:
            continue
        if key in seen and key not in duplicates:
            duplicates.append(key)
        seen.add(key)
    if duplicates:
        return t("biblio.duplicate_keys", lang, keys=", ".join(duplicates[:5]))
    return None


def bibliography_keys(text: str, lang: str = "en") -> set[str]:
    """文献库里全部可引用的 key（CSL-JSON 的 `id`；BibTeX 走正则，容忍语法小瑕疵）。"""
    if looks_like_csl_json(text):
        try:
            return {entry["id"] for entry in parse_csl_json(text, lang)}
        except BiblioError:
            return set()
    # 与 `parse_bibliography` 共用同一个解析器：括号式条目、`@comment`/`@string`
    # 的取舍都在 `_iter_entries` 里定过一次，这里不能再写一套更窄的正则。
    return {entry["id"] for entry in parse_bibtex(text)}
