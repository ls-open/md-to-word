#!/usr/bin/env python3
"""生成官网展示页：四套样张的成品（`docs/assets/`）与页面本身（`docs/index.html`）。

展示页没有后端、没有服务器、也不在运行时编译。但页面上那四份成品**照样是真导出的**：
这条脚本就是那条命令。产物提交进仓库，页面只负责展示与下载——所以页面里看到的每一张
预览图、每一个 .docx，都和用户自己跑出来的是同一份东西。

用法（仓库根目录）：

    python3 web/build.py                # 全建
    python3 web/build.py zh-report      # 只重建一套（页面照旧整页重渲染）

产物：

    docs/index.html          由 web/page.html 填内容生成，别手改
    docs/assets/<id>.docx    可直接下载，用 Word 打开就是成品
    docs/assets/<id>.pdf     Word 渲染出来的分页（域已展开）
    docs/assets/<id>.png     首页图，页面里当预览用

`--pdf` 走本机 Microsoft Word 渲染（macOS）。没装 Word 时 docx 照样生成，PDF 与首页图跳过，
退出码会告诉你哪些没出。PDF 不进测试的逐字节比对——它是 Word 的产物，不是我们的。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent
ROOT = WEB_DIR.parent
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
PNG_DPI = "110"


def _templates() -> dict:
    """延迟导入：`catalog.py` 会去读预设文件，import 成功不代表预设都在。"""
    sys.path.insert(0, str(WEB_DIR))
    sys.path.insert(0, str(ROOT / "src"))
    from catalog import TEMPLATES

    return TEMPLATES


def _assemble(tpl: dict) -> str:
    sys.path.insert(0, str(WEB_DIR))
    from catalog import _assemble_markdown

    return _assemble_markdown(
        template_id=tpl["id"],
        doc_title=tpl["doc_title"],
        abstract=tpl["abstract"],
        keywords=tpl["keywords"],
        intro_heading=tpl["intro_heading"],
        intro_body=tpl["intro_body"],
        equation=tpl["equation"],
        table_caption=tpl["table_caption"],
        table_content=tpl["table_content"],
        table_note=tpl["table_note"],
        conclusion_heading=tpl["conclusion_heading"],
        conclusion_body=tpl["conclusion_body"],
        references=tpl["references"],
    )


def _export(
    md_text: str, format_text: str, docx_path: Path, pdf: bool = True
) -> tuple[bool, bool]:
    """导出一套；返回 `(docx 是否成功, pdf 是否出得来)`。

    临时文件名固定为 `manuscript.md` / `format.txt`：格式文件的**名字**会写进 docx 的
    `docProps/core.xml`（`… · format.txt · sha256:…`），换名字就换字节。测试拿这个函数
    重导一遍再逐字节比对，所以两边必须走同一条路径、用同一批文件名。

    `pdf=False` 供测试用：docx 的字节与带 `--pdf` 时完全一样，只是不渲染 PDF。
    """
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        md_file = tmp / "manuscript.md"
        fmt_file = tmp / "format.txt"
        md_file.write_text(md_text, encoding="utf-8")
        fmt_file.write_text(format_text, encoding="utf-8")

        env = dict(os.environ)
        env["PYTHONPATH"] = str(ROOT / "src")
        cmd = [
            sys.executable, "-m", "md_to_word",
            str(md_file), "-f", str(fmt_file), "-o", str(docx_path),
        ]
        if pdf:
            cmd.append("--pdf")
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        # 3 = docx 已生成但 PDF 没渲染（没装 Word / 渲染失败），不算稿件有问题
        if proc.returncode not in (0, 3):
            sys.stderr.write(proc.stdout + proc.stderr)
            return False, False
        return True, pdf and proc.returncode == 0


def _pdf_to_png(pdf_path: Path, png_path: Path) -> bool:
    pdftoppm = shutil.which("pdftoppm")
    if not pdftoppm:
        print("  ! 没找到 pdftoppm（poppler），跳过首页图")
        return False
    with tempfile.TemporaryDirectory() as td:
        stem = Path(td) / "page"
        proc = subprocess.run(
            [pdftoppm, "-png", "-r", PNG_DPI, "-f", "1", "-l", "1",
             "-singlefile", str(pdf_path), str(stem)],
            capture_output=True,
        )
        page = Path(f"{stem}.png")
        if proc.returncode != 0 or not page.exists():
            return False
        png_path.write_bytes(page.read_bytes())
        return True


def _page_count(pdf_path: Path) -> int | None:
    if not pdf_path.exists():
        return None
    try:
        import pypdfium2 as pdfium

        doc = pdfium.PdfDocument(str(pdf_path))
        try:
            return len(doc)
        finally:
            doc.close()
    except Exception:
        return None


# ---------------------------------------------------------------- 页面渲染


def _esc(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _spec_rows(tpl: dict) -> str:
    """`规格：说明` 拆成 dt/dd；页面上逐条列出来，比一段话好扫。"""
    rows = []
    for value in tpl.get("specs_zh", {}).values():
        label, _, detail = str(value).partition("：")
        if not detail:
            label, detail = "说明", str(value)
        rows.append(f"<dt>{_esc(label)}</dt><dd>{_esc(detail)}</dd>")
    return "\n".join(rows)


def _render_page(templates: dict, built: set[str]) -> str:
    inputs, labels, panels = [], [], []

    for i, (tpl_id, tpl) in enumerate(templates.items()):
        checked = " checked" if i == 0 else ""
        inputs.append(
            f'      <input type="radio" name="tpl" id="tab-{tpl_id}"{checked}>'
        )
        labels.append(
            f'        <label for="tab-{tpl_id}">{_esc(tpl["name"])}</label>'
        )

        png = ASSETS / f"{tpl_id}.png"
        if tpl_id in built and png.exists():
            figure = (
                f'<img src="assets/{tpl_id}.png" alt="{_esc(tpl["name"])}样张首页" '
                f'loading="lazy">'
            )
        else:
            figure = (
                '<p style="padding:60px 20px;text-align:center;color:#7d8794;font-size:13px">'
                "这份预览图还没生成：装好 Word 后跑 <code>python3 web/build.py</code></p>"
            )

        pages = _page_count(ASSETS / f"{tpl_id}.pdf")
        page_note = f"Word 渲染 · {pages} 页" if pages else "Word 渲染"

        panels.append(
            f"""        <article class="panel" id="panel-{tpl_id}">
          <div class="panel-inner">
            <figure class="shot">
              {figure}
              <figcaption><span>{page_note}</span><span>{_esc(tpl["preset_name"])}</span></figcaption>
            </figure>
            <div class="meta">
              <h3>{_esc(tpl["name"])}</h3>
              <span class="badge">{_esc(tpl["badge"])}</span>
              <p class="desc">{_esc(tpl["desc"])}</p>
              <div class="dl">
                <a class="btn primary" href="assets/{tpl_id}.docx" download>下载 .docx</a>
                <a class="btn" href="assets/{tpl_id}.pdf" download>下载 .pdf</a>
              </div>
              <div class="specs">
                <h4>这一份的排版契约</h4>
                <dl>
{_spec_rows(tpl)}
                </dl>
              </div>
            </div>
          </div>
        </article>"""
        )

    tab_css = []
    for tpl_id in templates:
        tab_css.append(
            f'  #tab-{tpl_id}:checked ~ .tabbar label[for="tab-{tpl_id}"]'
            "{background:var(--ink);border-color:var(--ink);color:#fff}"
        )
        tab_css.append(
            f"  #tab-{tpl_id}:checked ~ .panels #panel-{tpl_id}{{display:block}}"
        )

    version = _version()
    template = (WEB_DIR / "page.html").read_text(encoding="utf-8")
    return (
        template.replace("{{VERSION}}", version)
        .replace("{{TAB_CSS}}", "\n".join(tab_css))
        .replace("{{INPUTS}}", "\n".join(inputs))
        .replace("{{LABELS}}", "\n".join(labels))
        .replace("{{PANELS}}", "\n".join(panels))
    )


def _version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    try:
        import md_to_word

        return getattr(md_to_word, "__version__", "")
    except Exception:
        return ""


# ---------------------------------------------------------------- 主流程


def build(template_ids: list[str], page_only: bool = False) -> int:
    templates = _templates()
    ASSETS.mkdir(parents=True, exist_ok=True)
    missing_pdf, failed = [], []

    for tpl_id in ([] if page_only else template_ids):
        tpl = templates[tpl_id]
        docx_path = ASSETS / f"{tpl_id}.docx"
        pdf_path = ASSETS / f"{tpl_id}.pdf"
        png_path = ASSETS / f"{tpl_id}.png"

        sys.path.insert(0, str(WEB_DIR))
        from catalog import _build_dynamic_format

        fmt_text = _build_dynamic_format(tpl_id, tpl["header_content"])
        ok, pdf_ok = _export(_assemble(tpl), fmt_text, docx_path)
        if not ok:
            failed.append(tpl_id)
            print(f"  ✗ {tpl_id}：导出失败")
            continue

        size_kb = docx_path.stat().st_size // 1024
        if not pdf_ok:
            missing_pdf.append(tpl_id)
            print(f"  ✓ {tpl_id}.docx（{size_kb} KB）· PDF 未渲染")
            continue

        if _pdf_to_png(pdf_path, png_path):
            print(f"  ✓ {tpl_id}.docx（{size_kb} KB）· .pdf · .png")
        else:
            print(f"  ✓ {tpl_id}.docx（{size_kb} KB）· .pdf（首页图失败）")

    built = {t for t in templates if (ASSETS / f"{t}.docx").exists()}
    html = _render_page(templates, built)
    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / ".nojekyll").write_text("", encoding="utf-8")
    print(f"  ✓ docs/index.html（{len(html) // 1024} KB）")

    if missing_pdf:
        print(
            f"\n{len(missing_pdf)} 套没有 PDF：{', '.join(missing_pdf)}\n"
            "  页面上的预览图与 PDF 下载会缺失。PDF 由本机 Microsoft Word 渲染，"
            "在这台机器上装好 Word 后重跑本脚本。"
        )
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("templates", nargs="*", help="只重建指定的模板，默认全部")
    parser.add_argument("--page-only", action="store_true",
                        help="只按现有产物重渲染 docs/index.html，不重新导出")
    args = parser.parse_args()
    templates = _templates()
    unknown = [t for t in args.templates if t not in templates]
    if unknown:
        parser.error(f"没有这些模板：{', '.join(unknown)}（可选：{', '.join(templates)}）")
    ids = args.templates or list(templates)
    if args.page_only:
        print("==> 只重渲染页面 ...")
    else:
        print(f"==> 生成 {len(ids)} 套样张到 {ASSETS.relative_to(ROOT)}/ ...")
    return build(ids, page_only=args.page_only)


if __name__ == "__main__":
    raise SystemExit(main())
