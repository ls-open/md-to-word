"""md-to-word Web Playground - 独立展示与交互后端。

完全独立于核心 Python 包，仅通过标准 API import 核心引擎。
特性：
1. 三套差异化标准模板（学位论文、技术白皮书、英文 Nature 期刊）
2. 静态预生成与内存缓存（默认内容 0 毫秒秒开，零计算负载）
3. IP 限流 (Rate Limiting) + 并发信号量控制 (防服务器打爆)
4. 真实多页 PDF 在线预览 API (/api/preview)
5. 真实 Word (.docx) 下载 API (/api/export)
"""

import asyncio
import hashlib
import os
import re
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

from md_to_word import export

app = FastAPI(
    title="md-to-word Web Playground",
    description="Deterministic Markdown to Word (.docx) Compilation Playground",
    version="2.2.0",
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

# 并发限制：同一时间最多 2 个 soffice 渲染进程在跑，保护 2G 服务器内存
CONVERT_SEMAPHORE = asyncio.Semaphore(2)

# IP 限流字典：{ ip: [timestamp, ...] }
IP_REQUESTS: Dict[str, List[float]] = {}
MAX_REQUESTS_PER_MINUTE = 15


def check_rate_limit(client_ip: str):
    """简易滑动窗口限流：每 IP 每 60 秒最多 15 次动态编译。"""
    now = time.time()
    timestamps = IP_REQUESTS.get(client_ip, [])
    # 保留 60 秒以内的请求
    valid_timestamps = [t for t in timestamps if now - t < 60]
    if len(valid_timestamps) >= MAX_REQUESTS_PER_MINUTE:
        raise HTTPException(
            status_code=429,
            detail="生成过于频繁，请稍候再试（每个 IP 每分钟限制 15 次动态生成）。",
        )
    valid_timestamps.append(now)
    IP_REQUESTS[client_ip] = valid_timestamps


# 三套精挑细选的场景模板（篇幅精准控制在 1~2 页，结构完全差异化）
TEMPLATES = {
    "zh-thesis": {
        "id": "zh-thesis",
        "name": "🎓 中文学位论文规范",
        "name_en": "Chinese Academic Thesis",
        "preset_file": str(BASE_DIR / "presets" / "zh-academic.txt"),
        "preset_name": "zh-academic",
        "doc_title": "基于深度神经网络的确定性排版架构研究",
        "abstract": "本文探讨了将非结构化文稿确定性编译为严格规范出版级 Word（.docx）的核心挑战。通过声明式排版契约与双向质量门禁，实现了产物的逐字节一致性与全自动自愈对账。",
        "keywords": "确定性排版；智能体技能；自愈门禁；原生OMML；三线表",
        "intro_heading": "1. 引言与研究背景",
        "intro_body": "学位论文对排版规范具有严苛要求：中文首行缩进两字符、西文字体 Times New Roman 分离、三线表顶底线线宽，以及按章编号数学公式居中靠右对齐。\n\n本引擎保证：同一份源文件在任何环境重跑产物逐字节完全一致，所有格式不符合规范的地方在导出前直接中断并报出行号。",
        "equation": "E = mc^2 + \\int_0^\\infty e^{-x^2} dx",
        "table_caption": "**表 1** 典型学术论文排版方案对比",
        "table_header": "| 方案 | 耗时 | 公式可编辑性 | 跨页重复 | 自愈能力 |\n|:---|:---:|:---:|:---:|:---:|",
        "table_rows": "| 手工 Word | 2~4h | 是 | 需逐表设置 | 无 |\n| 传统脚本 | 1~3s | 否 (位图) | 否 | 容易走样 |\n| **md-to-word** | **0.2s** | **是 (OMML)** | **是 (自动)** | **带行号自愈** |",
        "table_note": "注：测试数据基于学术论文标准样例，连续导出 5 次取中位数。",
        "conclusion_heading": "2. 结论",
        "conclusion_body": "将排版样式与文章内容完全解耦为独立声明文件，解决了 AI Agent 在文档交付环节的最后一公里难题。",
        "references": "[1] 张三, 李四. 基于深度学习的高性能文档排版系统[J]. 计算机学报, 2024, 47(3): 120-132.\n[2] Vaswani A, et al. Attention is all you need[J]. NeurIPS, 2017: 5998-6008.",
        # 各字段完整排版规格说明（写给用户看）
        "specs": {
            "title": "黑体/Times New Roman 二号(22pt) · 加粗 · 居中 · 行距1.5倍 · 段前0/段后12磅",
            "abstract": "宋体/Times New Roman 五号(10.5pt) · 两端对齐 · 行距1.5倍 · 首行缩进2字符",
            "body": "宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行缩进2字符 · 段前0/段后0",
            "table": "标准三线表 · 顶底线1.5磅 · 表头线0.75磅 · 跨页自动重复表头 · 单元格垂直居中",
            "equation": "原生 OMML 数学公式(非图片，可双击编辑) · 居中对齐 · 编号 (1) 严格靠右对齐",
            "header": "双线章名页眉 · 上实线下细线 · 奇偶页不同 · 内容自动映射当前章名",
            "references": "宋体/Times New Roman 五号(10.5pt) · 两端对齐 · 悬挂缩进0.5英寸(2字符)",
        },
    },
    "zh-report": {
        "id": "zh-report",
        "name": "📄 现代技术白皮书",
        "name_en": "Technical White Paper",
        "preset_file": str(BASE_DIR / "presets" / "zh-report.txt"),
        "preset_name": "zh-report",
        "doc_title": "2026 年度企业智能体交付技术白皮书",
        "abstract": "本白皮书系统梳理了自主智能体（AI Agents）在企业数字化办公场景中的落地实践，分析了从草稿到合规级报告的自动化交付体系，并提供确定性排版最佳实践。",
        "keywords": "AI Agent；技术白皮书；数字化转型；确定性交付",
        "intro_heading": "一、核心架构与效能评估",
        "intro_body": "随着多模态大模型与自主执行智能体的成熟，传统的“人工起草、排版、校对”流水线正迎来深刻重构。企业内部的技术文档对专业性、品牌规范的一致性提出了极高要求。",
        "equation": "\\mathcal{L}_{\\text{total}} = \\alpha \\mathcal{L}_{\\text{content}} + \\beta \\mathcal{L}_{\\text{typography}}",
        "table_caption": "**表 1** 关键业务流程耗时对比（人天）",
        "table_header": "| 业务环节 | 传统交付流程 | 智能体 + 编译底座 | 效能提升 |\n|:---|:---:|:---:|:---:|",
        "table_rows": "| 需求文档初稿 | 3.5 | 0.2 | 17.5x |\n| 合规与排版审核 | 2.0 | 0.05 | 40.0x |\n| 最终版式交付 | 1.0 | 0.01 | 100.0x |",
        "table_note": "注：数据基于 50 份企业真实技术交付件抽样统计。",
        "conclusion_heading": "二、实施规划",
        "conclusion_body": "将格式规则声明为纯文本并纳入版本控制系统，是确保大模型生成内容不失真、不走样、可审计的基石。",
        "references": "[1] 中国信息通信研究院. 人工智能智能体发展报告[R]. 2025.\n[2] Vercel Labs. Agent Skills Standard Specification[R]. 2025.",
        "specs": {
            "title": "黑体/Times New Roman 二号(22pt) · 加粗 · 居中 · 颜色#1F4E79 · 段前0/段后12磅",
            "abstract": "宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行缩进0字符 · 段后6磅",
            "body": "宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行不缩进(0字符) · 段后6磅",
            "table": "全网格数据表 · 顶底线0.75磅 · 内部网格线0.5磅 · 跨页自动重复表头",
            "equation": "原生 OMML 数学公式 · 居中对齐 · 编号靠右对齐",
            "header": "单线极简页眉 · 下边框单线0.75磅 · 右对齐 · 内容：企业级智能体与数字化交付技术白皮书",
            "references": "Times New Roman 五号(10.5pt) · 两端对齐 · 行距1.25倍 · 悬挂缩进0.5英寸",
        },
    },
    "en-paper": {
        "id": "en-paper",
        "name": "🔬 英文学术期刊 (Nature 规范)",
        "name_en": "English Academic Paper (Nature)",
        "preset_file": str(BASE_DIR / "presets" / "en-nature.txt"),
        "preset_name": "en-nature",
        "doc_title": "Deterministic Compilation of Markdown Manuscripts into Compliant Word Documents",
        "abstract": "Automating document preparation for journal submissions has long been hindered by non-deterministic language models and fragile scripts. In this paper, we introduce a declarative compilation pipeline that guarantees byte-identical Word (.docx) outputs from standard Markdown sources.",
        "keywords": "Document compilation; Agent Skills; Deterministic typography; OMML",
        "intro_heading": "1. Introduction",
        "intro_body": "Academic typography imposes stringent typographic and structural rules. In particular, equations must align in the center while their numbering sits hard against the right margin. Tables require three-line borders with repeating header rows across page breaks.",
        "equation": "\\nabla \\times \\mathbf{B} = \\mu_0 \\mathbf{J} + \\mu_0 \\varepsilon_0 \\frac{\\partial \\mathbf{E}}{\\partial t}",
        "table_caption": "**Table 1** Benchmark of Manuscript Compilation Methods",
        "table_header": "| Method | Compile Time | Native OMML | Repeating Header | Quality Gates |\n|:---|:---:|:---:|:---:|:---:|",
        "table_rows": "| Manual Word | > 120 min | Yes | Manual | None |\n| Standard Pandoc | ~ 1.2 s | Partial | Needs filter | Silent errors |\n| **md-to-word (Ours)** | **~ 0.2 s** | **Yes** | **Automatic** | **Line-accurate** |",
        "table_note": "Note: Measured on an IEEE-style paper. Compile time is wall-clock time over 10 repeated trials.",
        "conclusion_heading": "2. Conclusion",
        "conclusion_body": "Our approach effectively decouples layout declarations from manuscript prose, enabling automated publication delivery.",
        "references": "[1] Knuth D E. The TeXbook[M]. Addison-Wesley, 1984.\n[2] Lamport L. LaTeX: a document preparation system[M]. Addison-Wesley, 1994.",
        "specs": {
            "title": "Times New Roman 18pt bold · left/center · line spacing 1.5 · space after 12pt",
            "abstract": "Times New Roman 10pt · justify · line spacing 1.2 · indent 0",
            "body": "Times New Roman 12pt · justify · line spacing 1.5 · indent 0",
            "table": "Three-line border · top 1pt · bottom 1pt · header 0.5pt · repeat header row",
            "equation": "Native OMML equation · centered · equation number aligned hard right",
            "header": "Clean header · rule beneath · odd/even distinction",
            "references": "Times New Roman 10pt · hanging indent 0.5 in · APA citation style",
        },
    },
}


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>md-to-word Web Playground</h1><p>Static index.html not found.</p>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "md-to-word-web", "version": "2.2.0"}


@app.get("/api/templates")
async def get_templates():
    return TEMPLATES


def _assemble_markdown(
    template_id: str,
    doc_title: str,
    abstract: str,
    keywords: str,
    intro_heading: str,
    intro_body: str,
    equation: str,
    conclusion_heading: str,
    conclusion_body: str,
    references: str,
) -> Tuple[str, str, str]:
    """将表单组装为标准 Markdown，并返回 (markdown_text, preset_name, requirements_path_or_none)。"""
    is_en = template_id == "en-paper"
    tpl = TEMPLATES.get(template_id, TEMPLATES["zh-thesis"])

    title_tag = "%% Title" if is_en else "%% 文档标题"
    abstract_tag = "%% Abstract" if is_en else "%% 摘要"
    keywords_tag = "%% Keywords" if is_en else "%% 关键词"
    table_cap_tag = "%% Table Caption" if is_en else "%% 表题"
    table_note_tag = "%% Table Note" if is_en else "%% 表注"
    ref_title = "References" if is_en else "参考文献"

    table_block = f"{table_cap_tag} {tpl['table_caption']}\n\n{tpl['table_header']}\n{tpl['table_rows']}\n\n{table_note_tag} {tpl['table_note']}"

    body_paras = "\n\n".join(p.strip() for p in intro_body.splitlines() if p.strip())
    conclusion_paras = "\n\n".join(p.strip() for p in conclusion_body.splitlines() if p.strip())

    md_content = f"""{title_tag} {doc_title.strip()}

{abstract_tag} {abstract.strip()}

{keywords_tag} {keywords.strip()}

# {intro_heading.strip()}

{body_paras}

$${equation.strip()}$$ {{#eq-1}}

{table_block}

# {conclusion_heading.strip()}

{conclusion_paras}

# {ref_title}

{references.strip()}
"""
    return md_content, tpl["preset_name"], tpl["preset_file"]


def _get_content_hash(template_id: str, md_content: str) -> str:
    """计算模板 ID 与正文内容的哈希值，作为静态缓存 Key。"""
    raw = f"{template_id}:{md_content}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _compile_docx_and_pdf(
    md_content: str,
    preset_name: str,
    requirements_file: str,
    output_docx_path: Path,
    output_pdf_path: Path,
) -> Tuple[bool, list]:
    """同步编译生成 docx，并调用 soffice 转换为 pdf。"""
    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        md_file = temp_dir / "manuscript.md"
        md_file.write_text(md_content, encoding="utf-8")
        tmp_docx = temp_dir / "output.docx"

        res = export(
            manuscript=md_file,
            output=tmp_docx,
            requirements=requirements_file if requirements_file else None,
            preset=preset_name if not requirements_file else None,
        )

        if not res.ok:
            return False, res.errors

        # 复制到目标 docx 路径
        output_docx_path.write_bytes(tmp_docx.read_bytes())

        # 调用 soffice 转 pdf
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", str(tmp_docx)],
            cwd=str(temp_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=12,
            check=True,
        )

        tmp_pdf = temp_dir / "output.pdf"
        if not tmp_pdf.exists():
            return False, ["PDF 文件转换输出失败"]

        output_pdf_path.write_bytes(tmp_pdf.read_bytes())
        return True, []


# 启动时预热生成 3 个默认模板的缓存文件
def warmup_default_caches():
    print("==> 正在预热生成 3 个标准模板的静态缓存...")
    for tpl_id, tpl in TEMPLATES.items():
        md, preset_name, req_file = _assemble_markdown(
            template_id=tpl_id,
            doc_title=tpl["doc_title"],
            abstract=tpl["abstract"],
            keywords=tpl["keywords"],
            intro_heading=tpl["intro_heading"],
            intro_body=tpl["intro_body"],
            equation=tpl["equation"],
            conclusion_heading=tpl["conclusion_heading"],
            conclusion_body=tpl["conclusion_body"],
            references=tpl["references"],
        )
        chash = _get_content_hash(tpl_id, md)
        docx_cache = CACHE_DIR / f"{chash}.docx"
        pdf_cache = CACHE_DIR / f"{chash}.pdf"

        if not (docx_cache.exists() and pdf_cache.exists()):
            try:
                ok, errs = _compile_docx_and_pdf(md, preset_name, req_file, docx_cache, pdf_cache)
                if ok:
                    print(f"  ✓ 模板 {tpl_id} 静态缓存就绪 ({chash})")
                else:
                    print(f"  ✗ 模板 {tpl_id} 预热失败: {errs}")
            except Exception as e:
                print(f"  ✗ 模板 {tpl_id} 预热异常: {e}")
        else:
            print(f"  ✓ 模板 {tpl_id} 缓存已存在 ({chash})")


@app.on_event("startup")
async def on_startup():
    # 异步预热，不阻塞服务启动
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, warmup_default_caches)


@app.post("/api/preview")
async def preview_manuscript(
    request: Request,
    template_id: str = Form("zh-thesis"),
    doc_title: str = Form(...),
    abstract: str = Form(...),
    keywords: str = Form(""),
    intro_heading: str = Form("1. 引言"),
    intro_body: str = Form(...),
    equation: str = Form("E = mc^2"),
    conclusion_heading: str = Form("2. 结论"),
    conclusion_body: str = Form(""),
    references: str = Form(""),
):
    """在线多页 PDF 预览：命中缓存 0ms 秒开；未命中时排队动态生成。"""
    client_ip = request.client.host if request.client else "unknown"

    clean_md, preset_name, req_file = _assemble_markdown(
        template_id=template_id,
        doc_title=doc_title,
        abstract=abstract,
        keywords=keywords,
        intro_heading=intro_heading,
        intro_body=intro_body,
        equation=equation,
        conclusion_heading=conclusion_heading,
        conclusion_body=conclusion_body,
        references=references,
    )

    chash = _get_content_hash(template_id, clean_md)
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
        ok, errors = await loop.run_in_executor(
            None,
            _compile_docx_and_pdf,
            clean_md,
            preset_name,
            req_file,
            docx_cache,
            pdf_cache,
        )

    elapsed = round((time.time() - start_time) * 1000, 1)

    if not ok:
        return JSONResponse(
            status_code=422,
            content={"ok": False, "errors": errors, "elapsed_ms": elapsed},
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
    template_id: str = Form("zh-thesis"),
    doc_title: str = Form(...),
    abstract: str = Form(...),
    keywords: str = Form(""),
    intro_heading: str = Form("1. 引言"),
    intro_body: str = Form(...),
    equation: str = Form("E = mc^2"),
    conclusion_heading: str = Form("2. 结论"),
    conclusion_body: str = Form(""),
    references: str = Form(""),
):
    """下载真正的规范 Word (.docx) 文件。"""
    clean_md, preset_name, req_file = _assemble_markdown(
        template_id=template_id,
        doc_title=doc_title,
        abstract=abstract,
        keywords=keywords,
        intro_heading=intro_heading,
        intro_body=intro_body,
        equation=equation,
        conclusion_heading=conclusion_heading,
        conclusion_body=conclusion_body,
        references=references,
    )

    chash = _get_content_hash(template_id, clean_md)
    docx_cache = CACHE_DIR / f"{chash}.docx"
    pdf_cache = CACHE_DIR / f"{chash}.pdf"

    if not docx_cache.exists():
        async with CONVERT_SEMAPHORE:
            loop = asyncio.get_event_loop()
            ok, errors = await loop.run_in_executor(
                None,
                _compile_docx_and_pdf,
                clean_md,
                preset_name,
                req_file,
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
