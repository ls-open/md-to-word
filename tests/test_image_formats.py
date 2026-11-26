"""图片格式矩阵：文档承诺支持的每一种位图都要真的能嵌入。

同时守住两条边界：不支持的格式和远程图片必须在预检拦下，而不是到 python-docx
深处才抛 traceback，更不能尝试联网。
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

import pytest
from docx import Document

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.validator.check import validate_manuscript

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt"
IMAGES = REPO_ROOT / "tests" / "fixtures" / "images"

# 每种扩展名都用真实可解码的图片，不靠改后缀：改后缀正是 python-docx 会失败的那条路。
SUPPORTED = [
    ("png", "tiny.png"),
    ("jpg", "tiny.jpeg"),
    ("jpeg", "tiny.jpeg"),
    ("jpe", "tiny.jpeg"),
    ("jfif", "tiny.jpeg"),
    ("gif", "tiny.gif"),
    ("bmp", "tiny.bmp"),
    ("tif", "tiny.tiff"),
    ("tiff", "tiny.tiff"),
]


@pytest.mark.parametrize(("extension", "fixture"), SUPPORTED)
def test_a_supported_raster_embeds(
    extension: str, fixture: str, tmp_path: Path,
) -> None:
    image = tmp_path / f"pic.{extension}"
    shutil.copyfile(IMAGES / fixture, image)
    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        "# 一\n\n![](pic.%s){width=2cm}\n\n%%%% 图片题注 图 1 示意图\n" % extension,
        encoding="utf-8",
    )
    out = tmp_path / "paper.docx"
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=out, format_path=PRESET,
    ))
    assert result.returncode == 0, (extension, result.errors)
    assert len(Document(out).inline_shapes) == 1
    with zipfile.ZipFile(out) as archive:
        assert any(name.startswith("word/media/") for name in archive.namelist())


@pytest.mark.parametrize("value", [".", "1.2.3", "abc", "13cmx", "cm"])
def test_a_malformed_width_is_a_gate_error_not_an_internal_error(
    value: str, tmp_path: Path,
) -> None:
    shutil.copyfile(IMAGES / "tiny.png", tmp_path / "pic.png")
    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        "# 一\n\n![](pic.png){width=%s}\n\n%%%% 图片题注 图 1 示意图\n" % value,
        encoding="utf-8",
    )
    report = validate_manuscript(manuscript, spec_path=PRESET)
    assert not report.valid
    assert any(d.code == "gate.image_width.malformed" for d in report.diagnostics), report.errors

    # `--no-check` 跳过预检时，读取器也不能因此抛 ValueError；退回默认宽度正常导出。
    result = run_export_pipeline(ExportOptions(
        input_path=manuscript, output_path=tmp_path / "out.docx",
        format_path=PRESET, check_md=False,
    ))
    assert result.returncode == 0, (value, result.errors)


@pytest.mark.parametrize("extension", ["svg", "webp", "eps", "emf", "wmf"])
def test_an_unsupported_format_is_a_gate_error(extension: str, tmp_path: Path) -> None:
    (tmp_path / f"pic.{extension}").write_text("not an image", encoding="utf-8")
    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        "# 一\n\n![](pic.%s){width=2cm}\n\n%%%% 图片题注 图 1 示意图\n" % extension,
        encoding="utf-8",
    )
    report = validate_manuscript(manuscript, spec_path=PRESET)
    assert not report.valid
    assert any(d.code == "gate.image.unsupported" for d in report.diagnostics), report.errors


@pytest.mark.parametrize(
    "target",
    ["https://example.com/figure.png", "http://example.com/figure.png", "data:image/png;base64,AAAA"],
)
def test_remote_images_are_rejected_without_touching_the_network(
    target: str, tmp_path: Path,
) -> None:
    manuscript = tmp_path / "paper.md"
    manuscript.write_text(
        "# 一\n\n![](%s){width=2cm}\n\n%%%% 图片题注 图 1 示意图\n" % target,
        encoding="utf-8",
    )
    report = validate_manuscript(manuscript, spec_path=PRESET)
    assert not report.valid
    assert any(d.code == "gate.image.remote" for d in report.diagnostics), report.errors
