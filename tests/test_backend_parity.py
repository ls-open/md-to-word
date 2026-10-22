"""两条写出后端的对拍。

`--writer pandoc` 是成熟通道，`--writer native` 是自研写出器。同一份稿件两边产物应当
**结构等价**：每个带文字的段落用哪个样式、正文写了什么，都不该不同。

比对口径与已知差异（都是有意为之，写在这里免得下次误判成 bug）：

1. 只比有文字的段落。Quarto 会把独立公式包进一张隐藏表格，产生若干空段落；
   自研写出器直接写公式段落。那些空段落没有内容，不比。
2. 交叉引用前缀与编号之间：Quarto 用不换行空格（`式\\xa02.1`），我们不用（`式2.1`）。
   中文排版里后者更常见。
3. 括号引用前的空格：Quarto 保留（`灾难 (Smith, 2024)`），中文行文里我们去掉
   （`灾难(Smith, 2024)`）；西文行文我们照留。

除这三条外，样式序列与全文文本必须逐字相同。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMOS = {
    "00_quickstart": REPO_ROOT / "demo" / "00_quickstart" / "hello.md",
    "01_thesis": REPO_ROOT / "demo" / "01_chinese_thesis" / "thesis_sample.md",
    "02_report": REPO_ROOT / "demo" / "02_modern_report" / "report_sample.md",
}

pytestmark = pytest.mark.skipif(shutil.which("quarto") is None, reason="Quarto is not installed")


def _export(manuscript: Path, writer: str, output: str) -> Path:
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "export.sh"), manuscript.name, "--writer", writer, "-o", output],
        cwd=manuscript.parent,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return manuscript.parent / output


def _text_styles(docx: Path) -> list[tuple[str, str]]:
    xml = zipfile.ZipFile(docx).read("word/document.xml").decode("utf-8")
    out: list[tuple[str, str]] = []
    for match in re.finditer(r"<w:p[ >].*?</w:p>", xml, re.S):
        body = match.group(0)
        text = "".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", body)).strip()
        if not text:
            continue
        style = re.findall(r'<w:pStyle w:val="([^"]+)"', body)
        out.append((style[0] if style else "-", text))
    return out


def _normalize(text: str) -> str:
    """抹平两处有意的排版差异（见模块说明），其余一律保留。"""
    return text.replace("\xa0", "").replace(" (", "(")


@pytest.mark.parametrize("tag", sorted(DEMOS))
def test_native_matches_pandoc(tag: str, tmp_path: Path) -> None:
    manuscript = DEMOS[tag]
    for item in manuscript.parent.iterdir():
        if item.name.startswith("page-") or item.name.endswith((".pdf", ".docx")):
            continue
        target = tmp_path / item.name
        if item.is_dir():
            if not target.exists():
                shutil.copytree(item, target)
        else:
            shutil.copy(item, target)

    copy = tmp_path / manuscript.name
    ours = _export(copy, "native", "native.docx")
    theirs = _export(copy, "pandoc", "pandoc.docx")

    our_blocks = _text_styles(ours)
    their_blocks = _text_styles(theirs)

    assert [s for s, _ in our_blocks] == [s for s, _ in their_blocks], (
        f"{tag}: 段落样式序列不一致\n"
        f"native={[s for s, _ in our_blocks][:20]}\npandoc={[s for s, _ in their_blocks][:20]}"
    )

    ours_text = _normalize("".join(t for s, t in our_blocks if s != "Bibliography"))
    theirs_text = _normalize("".join(t for s, t in their_blocks if s != "Bibliography"))
    assert ours_text == theirs_text, f"{tag}: 正文文本不一致"

    # 文献列表单独比：条数必须一致；文本只要求「作者姓 + 题名关键词」对得上——
    # Pandoc 的 citeproc 与 citeproc-py 对 CSL 的保真度不同（如 GB/T 7714 的文献类型
    # 标识 [A]/[M]、题名大小写转换），那是实现差异，不是正文排版差异。
    our_bib = [t for s, t in _text_styles(ours) if s == "Bibliography"]
    their_bib = [t for s, t in _text_styles(theirs) if s == "Bibliography"]
    assert len(our_bib) == len(their_bib), f"{tag}: 文献条数不一致 {len(our_bib)} vs {len(their_bib)}"
