"""md-to-word Web Playground - 独立展示与交互后端。

完全独立于核心 Python 包，仅通过标准 API import 核心引擎。
特性：
1. 三套差异化标准模板（中文学术期刊、现代技术白皮书、英文 Nature 期刊）
2. 静态预生成与内存缓存（默认内容 0 毫秒秒开，零计算负载）
3. IP 限流 (Rate Limiting) + 并发信号量控制 (防服务器打爆)
4. 真实多页 PDF 在线预览 API (/api/preview)
5. 真实 Word (.docx) 下载 API (/api/export)
"""

import asyncio
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path
from typing import Dict, List, Tuple

# 确保能 import 上层项目中的 md_to_word
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import md_to_word
from md_to_word import export

app = FastAPI(
    title="md-to-word Web Playground",
    description="Deterministic Markdown to Word (.docx) Compilation Playground",
    version=getattr(md_to_word, "__version__", "3.2.0"),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
CACHE_DIR = Path(__file__).resolve().parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# 并发限制：同一时间最多 2 个 soffice 渲染进程在跑，保护服务器内存
CONVERT_SEMAPHORE = asyncio.Semaphore(2)

# IP 限流字典：{ ip: [timestamp, ...] }
IP_REQUESTS: Dict[str, List[float]] = {}
MAX_REQUESTS_PER_MINUTE = 20


def check_rate_limit(client_ip: str):
    """简易滑动窗口限流：每 IP 每 60 秒最多 20 次动态编译。"""
    now = time.time()
    timestamps = IP_REQUESTS.get(client_ip, [])
    valid_timestamps = [t for t in timestamps if now - t < 60]
    if len(valid_timestamps) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="生成过于频繁，请稍候再试（每个 IP 每分钟限制 20 次动态生成）。",
        )
    valid_timestamps.append(now)
    IP_REQUESTS[client_ip] = valid_timestamps


# 三套示例场景模板（学术/技术内容，控制在 1~2 页，内容为虚构，不涉及第三方实体）
from catalog import TEMPLATES, _assemble_markdown, _build_dynamic_format

# 兼顾 specs 字段向后兼容
for _k, _tpl in TEMPLATES.items():
    _tpl["specs"] = _tpl["specs_zh"]


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>md-to-word Web Playground</h1><p>Static index.html not found.</p>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "service": "md-to-word-web",
        "version": getattr(md_to_word, "__version__", "3.2.0"),
    }


@app.get("/api/templates")
async def get_templates():
    return TEMPLATES


def _get_content_hash(template_id: str, md_content: str, header_content: str) -> str:
    """计算模板 ID、正文与页眉的唯一哈希值，作为静态缓存 Key。"""
    raw = f"{template_id}:{header_content.strip()}:{md_content.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _compile_docx_and_pdf(
    md_content: str,
    format_text: str,
    output_docx_path: Path,
    output_pdf_path: Path,
) -> Tuple[bool, list, bool]:
    """同步编译生成 docx，并在装了 LibreOffice 时顺带转一份 pdf。

    返回 `(稿件是否编译成功, 错误列表, pdf 是否可用)`。
    """
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        md_file = temp_dir / "manuscript.md"
        md_file.write_text(md_content, encoding="utf-8")

        fmt_file = temp_dir / "format.txt"
        fmt_file.write_text(format_text, encoding="utf-8")

        tmp_docx = temp_dir / "output.docx"

        res = export(
            manuscript=md_file,
            output=tmp_docx,
            format=fmt_file,
        )

        if not res.ok:
            return False, res.errors, False

        # 复制到目标 docx 路径
        output_docx_path.write_bytes(tmp_docx.read_bytes())

        # PDF 只是在线预览用的副产品：**docx 下载不该依赖 LibreOffice**。
        # 把「PDF 转不出来」当成整体失败，等于要求每台机器都装 soffice，
        # 没装就 500（实测过一次），而用户要的 docx 其实已经生成好了。
        pdf_ok = _convert_to_pdf(tmp_docx, temp_dir / "output.pdf", output_pdf_path)
        return True, [], pdf_ok


def _convert_to_pdf(src: Path, tmp_pdf: Path, dst: Path) -> bool:
    """用 LibreOffice 把 docx 转成 pdf；转不了返回 False（不抛异常）。"""
    soffice = shutil.which("soffice")
    if not soffice:
        return False
    try:
        subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", str(src)],
            cwd=str(src.parent),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if not tmp_pdf.exists():
        return False
    dst.write_bytes(tmp_pdf.read_bytes())
    return True


# 启动时预热生成 3 个默认模板的缓存文件
def warmup_default_caches():
    print("==> 正在预热生成 3 个官方标准模板的静态缓存...")
    for tpl_id, tpl in TEMPLATES.items():
        md = _assemble_markdown(
            template_id=tpl_id,
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
        fmt_text = _build_dynamic_format(tpl_id, tpl["header_content"])
        chash = _get_content_hash(tpl_id, md, tpl["header_content"])
        docx_cache = CACHE_DIR / f"{chash}.docx"
        pdf_cache = CACHE_DIR / f"{chash}.pdf"

        if not (docx_cache.exists() and pdf_cache.exists()):
            try:
                ok, errs, pdf_ok = _compile_docx_and_pdf(md, fmt_text, docx_cache, pdf_cache)
                if ok:
                    note = "" if pdf_ok else "（未装 LibreOffice，跳过 PDF）"
                    print(f"  ✓ 模板 {tpl_id} 静态缓存就绪{note} ({chash})")
                else:
                    print(f"  ✗ 模板 {tpl_id} 预热失败: {errs}")
            except Exception as e:
                print(f"  ✗ 模板 {tpl_id} 预热异常: {e}")
        else:
            print(f"  ✓ 模板 {tpl_id} 缓存已存在 ({chash})")


@app.on_event("startup")
async def on_startup():
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, warmup_default_caches)


@app.post("/api/preview")
async def preview_manuscript(
    request: Request,
    template_id: str = Form("zh-journal"),
    header_content: str = Form(""),
    doc_title: str = Form(...),
    abstract: str = Form(...),
    keywords: str = Form(""),
    intro_heading: str = Form("1. 引言"),
    intro_body: str = Form(...),
    equation: str = Form(""),
    table_caption: str = Form(""),
    table_content: str = Form(""),
    table_note: str = Form(""),
    conclusion_heading: str = Form("2. 结论"),
    conclusion_body: str = Form(""),
    references: str = Form(""),
):
    """在线多页 PDF 预览：命中缓存 0ms 秒开；未命中时排队动态生成。"""
    if template_id == "zh-thesis":
        template_id = "zh-journal"

    client_ip = request.client.host if request.client else "unknown"

    clean_md = _assemble_markdown(
        template_id=template_id,
        doc_title=doc_title,
        abstract=abstract,
        keywords=keywords,
        intro_heading=intro_heading,
        intro_body=intro_body,
        equation=equation,
        table_caption=table_caption,
        table_content=table_content,
        table_note=table_note,
        conclusion_heading=conclusion_heading,
        conclusion_body=conclusion_body,
        references=references,
    )

    clean_header = header_content.strip() or TEMPLATES.get(template_id, {}).get("header_content", "")
    fmt_text = _build_dynamic_format(template_id, clean_header)

    chash = _get_content_hash(template_id, clean_md, clean_header)
    pdf_cache = CACHE_DIR / f"{chash}.pdf"
    docx_cache = CACHE_DIR / f"{chash}.docx"

    # 1. 命中缓存直接秒级返回（0 毫秒响应，零 CPU 消耗）
    if pdf_cache.exists():
        pdf_bytes = pdf_cache.read_bytes()
        headers = {
            "Content-Type": "application/pdf",
            "X-Compile-Ok": "true",
            "X-Compile-Cache": "hit",
            "X-Compile-Hash": chash,
            "Access-Control-Expose-Headers": "X-Compile-Ok, X-Compile-Cache, X-Compile-Hash",
        }
        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)

    # 2. 未命中缓存，触发限流与并发保护
    check_rate_limit(client_ip)
    start_time = time.time()

    async with CONVERT_SEMAPHORE:
        loop = asyncio.get_event_loop()
        ok, errors, pdf_ok = await loop.run_in_executor(
            None,
            _compile_docx_and_pdf,
            clean_md,
            fmt_text,
            docx_cache,
            pdf_cache,
        )

    elapsed = round((time.time() - start_time) * 1000, 1)

    if not ok:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "errors": errors, "elapsed_ms": elapsed},
        )

    if not pdf_ok:
        # 稿件本身编译通过了，只是这台机器没装 LibreOffice，出不了 PDF。
        # 说清楚，别让用户以为是自己稿子写错了。
        return JSONResponse(
            status_code=503,
            content={
                "ok": True,
                "errors": [],
                "preview_unavailable": "在线预览需要服务器安装 LibreOffice（soffice）；"
                                       "稿件的 .docx 已生成，可直接下载后在 Word 里查看。",
                "elapsed_ms": elapsed,
            },
        )

    pdf_bytes = pdf_cache.read_bytes()
    headers = {
        "Content-Type": "application/pdf",
        "X-Compile-Ok": "true",
        "X-Compile-Cache": "miss",
        "X-Compile-Elapsed-Ms": str(elapsed),
        "X-Compile-Hash": chash,
        "Access-Control-Expose-Headers": "X-Compile-Ok, X-Compile-Cache, X-Compile-Elapsed-Ms, X-Compile-Hash",
    }
    return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.post("/api/export")
async def export_manuscript(
    request: Request,
    template_id: str = Form("zh-journal"),
    header_content: str = Form(""),
    doc_title: str = Form(...),
    abstract: str = Form(...),
    keywords: str = Form(""),
    intro_heading: str = Form("1. 引言"),
    intro_body: str = Form(...),
    equation: str = Form(""),
    table_caption: str = Form(""),
    table_content: str = Form(""),
    table_note: str = Form(""),
    conclusion_heading: str = Form("2. 结论"),
    conclusion_body: str = Form(""),
    references: str = Form(""),
):
    """下载真正的规范 Word (.docx) 文件。"""
    if template_id == "zh-thesis":
        template_id = "zh-journal"

    clean_md = _assemble_markdown(
        template_id=template_id,
        doc_title=doc_title,
        abstract=abstract,
        keywords=keywords,
        intro_heading=intro_heading,
        intro_body=intro_body,
        equation=equation,
        table_caption=table_caption,
        table_content=table_content,
        table_note=table_note,
        conclusion_heading=conclusion_heading,
        conclusion_body=conclusion_body,
        references=references,
    )

    clean_header = header_content.strip() or TEMPLATES.get(template_id, {}).get("header_content", "")
    fmt_text = _build_dynamic_format(template_id, clean_header)

    chash = _get_content_hash(template_id, clean_md, clean_header)
    docx_cache = CACHE_DIR / f"{chash}.docx"
    pdf_cache = CACHE_DIR / f"{chash}.pdf"

    if not docx_cache.exists():
        async with CONVERT_SEMAPHORE:
            loop = asyncio.get_event_loop()
            ok, errors, _pdf_ok = await loop.run_in_executor(
                None,
                _compile_docx_and_pdf,
                clean_md,
                fmt_text,
                docx_cache,
                pdf_cache,
            )
            if not ok:
                return JSONResponse(status_code=422, content={"ok": False, "errors": errors})

    docx_bytes = docx_cache.read_bytes()

    safe_title = re.sub(r'[\\/*?:"<>|]', "", doc_title.strip())[:30] or "document"
    filename = f"{safe_title}.docx"
    quoted_filename = urllib.parse.quote(filename)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
        "X-Compile-Ok": "true",
        "X-Compile-Hash": chash,
        "Access-Control-Expose-Headers": "Content-Disposition, X-Compile-Ok, X-Compile-Hash",
    }
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers=headers,
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
