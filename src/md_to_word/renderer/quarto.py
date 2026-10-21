"""md_to_word.renderer.quarto — Quarto / Pandoc 渲染后端适配器。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from md_to_word.renderer.base import BaseRenderer


class QuartoRenderError(RuntimeError):
    """Quarto 渲染异常。"""


class QuartoRenderer(BaseRenderer):
    """基于 Quarto CLI 的渲染器实现。"""

    def is_available(self) -> bool:
        return shutil.which("quarto") is not None

    def render(
        self,
        input_md: Path | str,
        template_docx: Path | str,
        output_docx: Path | str,
        *,
        csl_path: Optional[Path | str] = None,
        link_citations: bool = True,
        resource_path: Optional[str] = None,
    ) -> Path:
        if not self.is_available():
            raise QuartoRenderError(
                "未在系统 PATH 中找到 quarto 可执行程序。请先安装 Quarto >= 1.4: https://quarto.org"
            )

        in_p = Path(input_md).resolve()
        tpl_p = Path(template_docx).resolve()
        out_p = Path(output_docx).resolve()

        if not in_p.exists():
            raise FileNotFoundError(f"输入稿件不存在: {in_p}")
        if not tpl_p.exists():
            raise FileNotFoundError(f"模板文件不存在: {tpl_p}")

        work_dir = out_p.parent
        work_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            "quarto",
            "render",
            str(in_p),
            "--to",
            "docx",
            "--reference-doc",
            str(tpl_p),
            "-o",
            out_p.name,
        ]

        if csl_path:
            cmd.extend(["-M", f"csl={csl_path}"])

        if link_citations:
            cmd.extend(["-M", "link-citations=true"])

        res_paths = []
        if resource_path:
            res_paths.append(str(resource_path))
        # 默认加上稿件所在目录和根目录支持
        res_paths.append(str(in_p.parent))
        if os.name != "nt":
            res_paths.append("/")
        cmd.extend(["--resource-path", os.pathsep.join(res_paths)])

        result = subprocess.run(
            cmd,
            cwd=str(work_dir),
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            error_msg = (result.stderr or result.stdout or "").strip()
            raise QuartoRenderError(f"Quarto 编译失败 (exit {result.returncode}):\n{error_msg}")

        if not out_p.exists():
            raise QuartoRenderError(f"Quarto 编译未报错，但未找到输出产物: {out_p}")

        return out_p
