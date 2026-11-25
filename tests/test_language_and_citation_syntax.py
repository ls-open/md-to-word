"""两个底层判据只能有一份：引文 key 的字符集，与文档语言的判定。

- 预检与读取器对 `[@k+5]` 的 key 理解必须一致，否则「预检通过、产物引错条目」；
- 交叉引用前缀与公式编号看的是**整篇稿件**的语言，不是「前 800 字」——
  中文论文前面放一段英文摘要，不该把「式 1」变成「Equation 1」。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.utils.citation_syntax import CITE_KEY_RE

REPO = Path(__file__).resolve().parents[1]
ZH_PRESET = REPO / "src/md_to_word/presets/zh-academic.txt"


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    import re

    return "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))


def test_citation_key_pattern_keeps_symbols() -> None:
    assert CITE_KEY_RE.search("@k+5").group(1) == "k+5"
    assert CITE_KEY_RE.search("@k%7").group(1) == "k%7"
    assert CITE_KEY_RE.search("user@example.com") is None


def test_symbol_keys_survive_preflight_and_render(tmp_path: Path) -> None:
    bib = tmp_path / "refs.bib"
    bib.write_text(
        "@article{k+5, author={Smith, John}, title={Plus Key}, journal={J}, year={2024}}\n"
        "@article{k%7, author={Lee, Ann}, title={Percent Key}, journal={J}, year={2023}}\n",
        encoding="utf-8",
    )
    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        "---\nbibliography: refs.bib\ncsl: apa.csl\n---\n\n"
        "# 引言\n\n符号键引用 [@k+5] 与 [@k%7]。\n\n"
        "%% 参考文献标题 参考文献\n",
        encoding="utf-8",
    )

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "out.docx",
        format_path=ZH_PRESET,
    ))

    assert result.ok, result.errors
    text = _docx_text(tmp_path / "out.docx")
    assert "Smith" in text and "Lee" in text
    assert "[@k+5]" not in text and "[@k%7]" not in text


def test_crossref_prefix_follows_the_whole_manuscript_not_the_first_page(tmp_path: Path) -> None:
    english = (
        "This study examines deterministic document compilation in depth. " * 12
    )  # 约 800+ 字符，占满「前 800 字」的启发式窗口
    chinese = (
        "本文讨论确定性文档编译。中文正文足够长，确保整篇稿件按中文判定。"
        "交叉引用应当使用中文前缀，而不是英文前缀。"
    ) * 6
    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        f"# Introduction\n\n{english}\n\n"
        f"# 正文\n\n{chinese}\n\n"
        "$$x = y$$ {#eq-a}\n\n"
        "见 @eq-a。\n",
        encoding="utf-8",
    )

    result = run_export_pipeline(ExportOptions(
        input_path=manuscript,
        output_path=tmp_path / "out.docx",
        format_path=ZH_PRESET,
        lang="zh",  # 消息语言也是中文，但判定不该依赖它
    ))

    assert result.ok, result.errors
    assert result.doc_lang == "zh"
    text = _docx_text(tmp_path / "out.docx")
    assert "式" in text
    assert "Equation" not in text
