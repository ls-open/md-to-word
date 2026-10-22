"""md_to_word.visual_qa.word_pdf — 驱动本机 Microsoft Word 展开域并渲染 PDF（macOS 专享）。"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Optional

from md_to_word.config import WORKSPACE_DIR


def _render_script() -> Path:
    """渲染脚本的位置：**包内资源优先**。

    它必须随 wheel 发布——pip 装的人也要能 `--pdf`。仓库根 `scripts/` 下那份只是转发，
    开发时的老用法照样能用。
    """
    packaged = Path(__file__).resolve().parents[1] / "resources" / "render_via_word.sh"
    if packaged.is_file():
        return packaged
    return WORKSPACE_DIR / "scripts" / "render_via_word.sh"


def can_render_word_pdf() -> tuple[bool, str]:
    """判断当前环境是否支持驱动 Word 渲染 PDF。"""
    if platform.system() != "Darwin":
        return False, "not-darwin"
    word_container = Path.home() / "Library/Containers/com.microsoft.Word/Data"
    if not word_container.is_dir():
        return False, "no-word"
    script = _render_script()
    if not script.is_file():
        return False, "no-render-script"
    return True, "ok"


def render_pdf_via_word(
    docx_path: Path | str, pdf_path: Optional[Path | str] = None
) -> tuple[bool, Optional[str]]:
    """在 macOS 上调用 Word 将 docx 展开域并保存为 PDF。"""
    supported, reason = can_render_word_pdf()
    if not supported:
        return False, reason

    docx_p = Path(docx_path).resolve()
    pdf_p = Path(pdf_path).resolve() if pdf_path else docx_p.with_suffix(".pdf")
    script = _render_script()

    res = subprocess.run(
        ["bash", str(script), str(docx_p), str(pdf_p)],
        capture_output=True,
        text=True,
    )
    if res.returncode == 0 and pdf_p.exists():
        return True, None
    return False, res.stderr or res.stdout
