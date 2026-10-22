"""四份 demo 必须每次都导得出来，且不带一条门禁错误。

demo 是「常见稿件形态」的样本：最小样例、中文学位论文、技术白皮书、英文期刊。
它们同时是回归网——某个改动让其中任何一种形态跑不通，这里会先红，而不是等用户
拿着一份真实稿件撞上。单元测试盯的是单点行为，这一组盯的是**整条链路对常见形态成立**。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from md_to_word.pipeline import ExportOptions, run_export_pipeline

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO = REPO_ROOT / "demo"

# (样例目录, 稿件, 要求文件；None 表示用内置预设)
CASES = [
    ("00_quickstart", "hello.md", "requirements.txt", None),
    ("01_chinese_thesis", "thesis_sample.md", "requirements.txt", None),
    ("02_modern_report", "report_sample.md", "requirements.txt", None),
    ("03_english_paper", "paper.md", None, "en-nature"),
]


@pytest.mark.parametrize(("folder", "manuscript", "requirements", "preset"), CASES)
def test_demo_exports_cleanly(
    tmp_path: Path, folder: str, manuscript: str, requirements: str | None, preset: str | None
) -> None:
    demo_dir = DEMO / folder
    out = tmp_path / "out.docx"
    result = run_export_pipeline(
        ExportOptions(
            input_path=demo_dir / manuscript,
            output_path=out,
            requirements_path=demo_dir / requirements if requirements else None,
            preset=preset,
            # 产物落到 tmp_path：demo 目录里那份是给人看的，不该被测试改动
        )
    )

    assert result.returncode == 0, result.errors
    assert out.is_file()
    with zipfile.ZipFile(out) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert xml.count("<w:p ") + xml.count("<w:p>") > 5, "产出的正文段落数不合常理"


def test_every_demo_has_a_readme_and_manuscript() -> None:
    """目录形态本身也是一条约束：样例缺了说明或稿件，读文档的人就会撞空。"""
    for folder, manuscript, _, _ in CASES:
        demo_dir = DEMO / folder
        assert (demo_dir / manuscript).is_file(), f"{folder} 缺 {manuscript}"
        assert (demo_dir / "README.md").is_file(), f"{folder} 缺 README.md"
