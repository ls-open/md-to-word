"""样式行里的段落属性：行距「最小值」、以及「**左缩进** + 悬挂缩进」并存。

两条都是同一类失败：要求文件写的是一个合法组合，产物却不是那个组合，而且都不安静——
最小值让模板生成直接抛 TypeError（3.2.0 实测），悬挂缩进把写在同一行的左缩进删掉，
要等导出后对账才报出来。

判据是「**写什么就落成什么**」：属性落进 styles.xml，且导出后对账能把它们认回来。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from md_to_word.pipeline import ExportOptions, run_export_pipeline
from md_to_word.template.builder import build_template

REPO_ROOT = Path(__file__).resolve().parents[1]
PRESET = (REPO_ROOT / "src" / "md_to_word" / "presets" / "zh-academic.txt").read_text(encoding="utf-8")

MIN_LINE_SPACING = (
    "正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 "
    "行距最小值20磅 段前0磅 段后0磅 首行缩进2字符"
)
HANGING_WITH_LEFT = (
    "表注：宋体/Times New Roman 五号 不加粗 不倾斜 两端对齐 "
    "行距1.0倍 段前0磅 段后7.8磅 悬挂缩进0.29英寸 左缩进2字符"
)


def _spec_with(prefix: str, replacement: str) -> str:
    """把预设里的某一行换掉，其余原样——从预设起步，才只改被测的那一项。"""
    rows = [replacement if line.startswith(prefix) else line for line in PRESET.splitlines()]
    return "\n".join(rows) + "\n"


def _style_xml(spec: str, style_id: str, tmp_path: Path) -> str:
    out = tmp_path / "t.docx"
    build_template(spec, out)
    with zipfile.ZipFile(out) as archive:
        styles = archive.read("word/styles.xml").decode("utf-8")
    match = re.search(rf'<w:style [^>]*w:styleId="{style_id}".*?</w:style>', styles, re.S)
    assert match is not None, f"styles.xml 里没有 {style_id}"
    return match.group(0)


def _export(spec: str, tmp_path: Path) -> object:
    """跑完整流水线：模板 → 写出 → 导出后对账，结果就是作者会经历的整条路。"""
    (tmp_path / "m.md").write_text("---\n---\n\n# 一 引言\n\n正文。\n", encoding="utf-8")
    (tmp_path / "f.txt").write_text(spec, encoding="utf-8")
    return run_export_pipeline(
        ExportOptions(
            input_path=tmp_path / "m.md",
            output_path=tmp_path / "o.docx",
            format_path=tmp_path / "f.txt",
        )
    )


def test_min_line_spacing_reaches_at_least(tmp_path: Path) -> None:
    """「行距最小值20磅」→ `line=400 / lineRule=atLeast`，不是倍数也不是固定值。"""
    body = _style_xml(_spec_with("正文：", MIN_LINE_SPACING), "BodyText", tmp_path)

    assert 'w:line="400"' in body
    assert 'w:lineRule="atLeast"' in body


def test_min_line_spacing_exports_cleanly(tmp_path: Path) -> None:
    """最小值行距要能导出成功，并且导出后对账自己也要认得出 atLeast。"""
    result = _export(_spec_with("正文：", MIN_LINE_SPACING), tmp_path)

    assert result.returncode == 0, result.errors


def test_hanging_keeps_the_left_indent_written_beside_it(tmp_path: Path) -> None:
    """左缩进和悬挂缩进是 `w:ind` 上的两个属性，同一行都写时必须都留下。"""
    note = _style_xml(_spec_with("表注：", HANGING_WITH_LEFT), "TableNote", tmp_path)

    assert 'w:leftChars="200"' in note, "「左缩进2字符」被悬挂缩进删掉了"
    assert 'w:hanging="418"' in note, "0.29 英寸 = 20.88 磅 = 417.6 twips，按 418 落"


def test_hanging_with_left_indent_passes_the_audit(tmp_path: Path) -> None:
    """两个缩进同时声明时，产物与要求文件要对得上——不能等到对账才失败。"""
    result = _export(_spec_with("表注：", HANGING_WITH_LEFT), tmp_path)

    assert result.returncode == 0, result.errors
