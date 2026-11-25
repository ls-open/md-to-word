"""CSL-JSON 文献库输入。

Zotero / Mendeley / Crossref 直接导出的就是 CSL-JSON。`bibliography:` 只认一个键，
文件内容决定解析方式——扩展名不可靠，内容才可靠。这里锁三件事：能读、能渲染、
坏文件有带位置的明确错误而不是 traceback。
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.transform.biblio import (
    bibliography_keys,
    bibliography_problem,
    parse_bibliography,
)

REFS = [
    {
        "id": "smith2024",
        "type": "article-journal",
        "title": "Reading speed and spacing",
        "author": [{"family": "Smith", "given": "John"}],
        "container-title": "Journal of Reading",
        "issued": {"date-parts": [[2024]]},
        "volume": "12",
        "issue": "3",
        "page": "45-67",
    },
    {
        "id": "lee2023",
        "type": "book",
        "title": "Typography for Students",
        "author": [{"family": "Lee", "given": "Anna"}],
        "publisher": "Example Press",
        "issued": {"date-parts": [[2023]]},
    },
]


def _write_paper(tmp_path: Path, refs_text: str, refs_name: str = "refs.json") -> Path:
    (tmp_path / refs_name).write_text(refs_text, encoding="utf-8")
    (tmp_path / "format.txt").write_text(
        (Path(__file__).resolve().parents[1]
         / "src/md_to_word/presets/zh-academic.txt").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    paper = tmp_path / "paper.md"
    paper.write_text(
        "---\nbibliography: refs.json\ncsl: apa.csl\n---\n\n"
        "# 引言\n\n阅读速度受行距影响 [@smith2024]，排版基础见 [@lee2023]。\n\n"
        "%% 参考文献标题 参考文献\n",
        encoding="utf-8",
    )
    return paper


def _doc_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return "".join(ch for ch in xml if ch.isprintable())


def test_csl_json_array_renders_end_to_end(tmp_path: Path) -> None:
    paper = _write_paper(tmp_path, json.dumps(REFS, ensure_ascii=False))
    out = tmp_path / "paper.docx"

    result = run_export_pipeline(ExportOptions(input_path=paper, output_path=out))

    assert result.ok, result.errors
    text = _doc_text(out)
    assert "Smith" in text and "Lee" in text
    assert "Reading speed and spacing" in text


def test_csl_json_items_wrapper_is_accepted(tmp_path: Path) -> None:
    paper = _write_paper(tmp_path, json.dumps({"items": REFS}, ensure_ascii=False))
    out = tmp_path / "paper.docx"

    result = run_export_pipeline(ExportOptions(input_path=paper, output_path=out))

    assert result.ok, result.errors
    assert "Smith" in _doc_text(out)


def test_biblio_helpers_agree_on_keys() -> None:
    text = json.dumps(REFS)
    assert bibliography_keys(text) == {"smith2024", "lee2023"}
    assert {entry["id"] for entry in parse_bibliography(text)} == {"smith2024", "lee2023"}
    assert bibliography_problem(text) is None


def test_malformed_csl_json_is_a_gate_error_with_a_code(tmp_path: Path) -> None:
    paper = _write_paper(tmp_path, "[{not json")

    result = run_export_pipeline(ExportOptions(
        input_path=paper, output_path=tmp_path / "paper.docx",
    ))

    assert result.returncode == 1
    assert "gate.bib.json" in [d.code for d in result.diagnostics]
    assert any("CSL-JSON" in error for error in result.errors)
    assert not (tmp_path / "paper.docx").exists()


def test_malformed_csl_json_is_reported_by_preflight(tmp_path: Path) -> None:
    from md_to_word.validator.check import validate_manuscript

    paper = _write_paper(tmp_path, json.dumps({"items": "not-a-list"}))
    report = validate_manuscript(paper, lang="zh")

    assert not report.valid
    assert any(d.code == "gate.bib.json" for d in report.diagnostics), report.diagnostics


def test_bibtex_parentheses_and_comments_use_the_same_parser() -> None:
    """括号式条目与 `@comment` 的取舍必须与引文引擎一致，否则键集会分叉。"""
    text = (
        "@comment{@article{fake, title={Not an entry}}}\n"
        "@article(real2020, author={Ann Author}, title={Real}, year={2020})\n"
    )

    assert bibliography_keys(text) == {"real2020"}
    assert {entry["id"] for entry in parse_bibliography(text)} == {"real2020"}


def test_empty_csl_json_behaves_like_an_empty_bib(tmp_path: Path) -> None:
    """空文献库没有引用时无害；有引用时由预检统一报「文献库里没有条目」。"""
    paper = tmp_path / "plain.md"
    (tmp_path / "refs.json").write_text("[]", encoding="utf-8")
    paper.write_text(
        "---\nbibliography: refs.json\n---\n\n# 引言\n\n只有正文。\n",
        encoding="utf-8",
    )
    ok = run_export_pipeline(ExportOptions(
        input_path=paper, output_path=tmp_path / "ok.docx",
        preset="zh-academic",
    ))
    assert ok.ok, ok.errors

    (tmp_path / "cited.md").write_text(
        "---\nbibliography: refs.json\n---\n\n# 引言\n\n引用 [@nobody]。\n",
        encoding="utf-8",
    )
    bad = run_export_pipeline(ExportOptions(
        input_path=tmp_path / "cited.md", output_path=tmp_path / "bad.docx",
        preset="zh-academic",
    ))
    assert bad.returncode == 1
    assert "gate.bib.empty" in [d.code for d in bad.diagnostics]
