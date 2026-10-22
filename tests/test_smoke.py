"""Smoke tests for nature-paper2word.

Two layers:

- preset/template checks that run anywhere (python-docx only);
- one end-to-end export over the whole pipeline (no external binary involved).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from docx import Document

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
FIXTURES = Path(__file__).resolve().parent / "fixtures"

import sys

sys.path.insert(0, str(SCRIPTS_DIR))

from md_to_word.spec.parser import parse_requirements  # noqa: E402
from md_to_word.template.generator import generate_template  # noqa: E402


@pytest.mark.parametrize("preset", ["zh-academic.txt", "en-nature.txt"])
def test_preset_parses_and_generates_template(preset: str, tmp_path: Path) -> None:
    """Every shipped preset must be a valid requirements file and build a template."""
    text = (SKILL_DIR / "presets" / preset).read_text(encoding="utf-8")
    spec = parse_requirements(text)
    names = {style["style_name"] for style in spec.styles}

    # Required skeleton plus the structures a real manuscript commonly uses.
    for required in ("Title", "Heading 1", "Body Text", "First Paragraph", "Normal"):
        assert required in names
    for structural in ("Compact", "Block Text", "Footnote Text", "Captioned Figure"):
        assert structural in names
    assert spec.table is not None, "the table configuration row must be present"
    assert spec.table_header is not None, "the table header row must be present"

    out = tmp_path / f"{preset}.docx"
    generate_template(text, str(out))
    assert out.exists()

    document = Document(str(out))
    style_names = {style.name for style in document.styles}
    assert {"Body Text", "First Paragraph", "Normal", "Table"} <= style_names


def _styles_xml(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as archive:
        return archive.read("word/styles.xml").decode("utf-8")


def _document_xml(docx_path: Path) -> str:
    with zipfile.ZipFile(docx_path) as archive:
        return archive.read("word/document.xml").decode("utf-8")


def test_export_end_to_end(tmp_path: Path) -> None:
    """The full pipeline must produce equations, a three-line table, and a citation."""
    for name in ("manuscript.md", "refs.bib"):
        shutil.copy(FIXTURES / name, tmp_path / name)
    output = tmp_path / "manuscript.docx"

    result = subprocess.run(
        ["bash", str(SCRIPTS_DIR / "export.sh"), "manuscript.md", "-o", output.name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.exists()

    xml = _document_xml(output)
    assert "<m:oMath" in xml, "display equation must be native OMML"
    assert "<w:tbl>" in xml, "the manuscript table must survive as a Word table"
    assert "<w:tblBorders" in xml or "tblBorders" in _styles_xml(output), (
        "三线表边框要么写在表格属性里，要么写在 Table 样式里"
    )

    text = " ".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", xml))
    assert "smith2024" not in text, "raw citation keys must not leak into the document"
    assert 'w:vertAlign w:val="superscript"' in xml, "Nature style renders citations as superscripts"
    assert "SMITH" in text.upper(), "bibliography entry must be rendered"
