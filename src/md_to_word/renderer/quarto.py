"""md_to_word.renderer.quarto — Quarto / Pandoc 渲染后端适配器。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from md_to_word.renderer.base import BaseRenderer

# 支持策略：不锁死单版本，只声明「最低」与「已在本仓验证到哪一版」。
#   < 最低版本      → 硬失败（用到的 crossref / 短代码行为在那之前不存在）
#   > 已验证版本    → 只警告，不阻断（对更新的版本拒跑，等于把用户挡在门外）
MIN_QUARTO_VERSION = (1, 4)
TESTED_QUARTO_VERSION = (1, 10)


class QuartoRenderError(RuntimeError):
    """Quarto 渲染异常。"""


def _parse_version(text: str) -> Optional[tuple[int, ...]]:
    m = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", (text or "").strip())
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def read_quarto_version() -> Optional[tuple[int, ...]]:
    """读 `quarto --version`；读不到返回 None（调用方据此报环境问题）。"""
    try:
        res = subprocess.run(["quarto", "--version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return _parse_version(res.stdout)


def check_quarto_environment() -> tuple[Optional[tuple[int, ...]], list[str], list[str]]:
    """渲染引擎的版本体检 → (版本号, 错误, 警告)。

    错误会让导出以「环境问题」退出（退出码 2），警告只提示、不阻断。
    """
    if shutil.which("quarto") is None:
        return None, [
            "未在系统 PATH 中找到 quarto。请先安装 Quarto "
            f">= {'.'.join(map(str, MIN_QUARTO_VERSION))}: https://quarto.org"
        ], []

    version = read_quarto_version()
    if version is None:
        return None, ["找到了 quarto，但读不出版本号（`quarto --version` 无输出）；安装可能不完整。"], []

    # 只比 major.minor：补丁号不改变排版行为，拿它来判「未验证过」只会天天报警
    major_minor = version[:2]
    errors: list[str] = []
    warnings: list[str] = []
    if major_minor < MIN_QUARTO_VERSION:
        errors.append(
            f"Quarto 版本 {'.'.join(map(str, version))} 低于最低要求 "
            f"{'.'.join(map(str, MIN_QUARTO_VERSION))}；请升级后再导出。"
        )
    elif major_minor > TESTED_QUARTO_VERSION:
        warnings.append(
            f"Quarto {'.'.join(map(str, version))} 比本技能验证过的 "
            f"{'.'.join(map(str, TESTED_QUARTO_VERSION))} 新；如遇到排版差异，请附版本号回报。"
        )
    return version, errors, warnings


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
        metadata_file: Optional[Path | str] = None,
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

        # 只补稿件没有显式声明的默认值：Pandoc 里稿件 YAML 的优先级高于本文件，
        # 用户写了就以用户的为准（实测：稿件有 crossref 块时，文件里的同名块被整块覆盖）
        if metadata_file:
            cmd.extend(["--metadata-file", str(metadata_file)])

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
