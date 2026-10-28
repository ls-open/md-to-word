"""md-to-word Web Playground - 独立展示与交互后端。

完全独立于核心 Python 包，仅通过标准 API import 核心引擎。
提供：
1. 在线 PDF 实时多页预览 API (/api/preview)
2. 真实 Word (.docx) 下载 API (/api/export)
3. 规范模板与默认内容 API (/api/templates)
4. 健康检查 API (/api/health)
"""

import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

# 确保能 import 上层项目中的 md_to_word
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR / "src") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "src"))

from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from md_to_word import export

app = FastAPI(
    title="md-to-word Web Playground",
    description="Deterministic Markdown to Word (.docx) Compilation Playground",
    version="2.1.0",
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>md-to-word Web Playground</h1><p>Static index.html not found.</p>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "service": "md-to-word-web", "version": "2.1.0"}


# 预置的三套高品质标准模板（结构固定、排版参数最优、内容可编辑）
TEMPLATES = {
    "zh-thesis": {
        "id": "zh-thesis",
        "name": "🎓 中文学位论文规范",
        "name_en": "Chinese Academic Thesis",
        "preset": "zh-academic",
        "doc_title": "基于深度神经网络的确定性排版架构与自愈编译研究",
        "abstract": "本文探讨了将非结构化文稿确定性编译为严格规范出版级 Word（.docx）的核心挑战。传统基于大模型的直接排版脚本极易引发样式漂移、公式失真与跨页表格走样。本文构建了一套声明式排版契约与双向质量门禁管线，在真实学位论文场景下实现了产物的逐字节一致性与全自动自愈对账。",
        "keywords": "确定性排版；智能体技能；自愈门禁；原生OMML；三线表",
        "intro_heading": "1. 引言与背景",
        "intro_body": "学术出版物与学位论文对排版规范具有极高要求。从中文首行缩进两字符、西文字体 Times New Roman 分离，到三线表的顶底线线宽，以及按章编号的数学公式居中靠右对齐，传统排版过程往往耗费大量科研人员的时间。\n\n本引擎保证：同一份源文件在任何环境重跑产物逐字节完全一致，所有格式不符合规范的地方在导出前直接中断并报出行号，杜绝大模型手写脚本产生的格式幻觉。",
        "equation": "E = mc^2 + \\int_0^\\infty e^{-x^2} dx",
        "table_caption": "**表 1** 典型学术论文排版方案对比",
        "table_header": "| 方案 | 端到端耗时 | 公式可编辑性 | 表头跨页重复 | 格式自愈能力 |\n|:---|:---:|:---:|:---:|:---:|",
        "table_rows": "| 手工 Word 排版 | 2~4 小时 | 是 | 需逐表手工设置 | 无 |\n| 传统脚本导出 | 1~3 秒 | 否 (转为位图) | 否 | 容易静默走样 |\n| **本项目 (md-to-word)** | **0.2 秒** | **是 (原生 OMML)** | **是 (自动重复)** | **带行号自愈** |",
        "table_note": "注：测试数据基于学术论文标准样例，硬件环境为通用云服务器，连续导出 5 次取中位数。",
        "conclusion_heading": "2. 结论与展望",
        "conclusion_body": "通过将排版样式与文章内容完全解耦为独立声明文件，我们解决了 AI Agent 在文档交付环节的最后一公里难题。",
        "references": "[1] 张三, 李四. 基于深度学习的高性能文档排版系统[J]. 计算机学报, 2024, 47(3): 120-132.\n[2] Vaswani A, Shazeer N, Parmar N, et al. Attention is all you need[J]. NeurIPS, 2017, 30: 5998-6008.\n[3] Knuth D E. The TeXbook[M]. Addison-Wesley, 1984.",
    },
    "zh-report": {
        "id": "zh-report",
        "name": "📄 现代技术白皮书",
        "name_en": "Technical White Paper",
        "preset": "zh-academic",
        "doc_title": "2026 年度智能体自主交付与确定性文档编译技术白皮书",
        "abstract": "本白皮书系统梳理了新一代自主智能体（AI Agents）在企业数字化办公场景中的落地实践。重点分析了从自然语言草稿到合规企业级报告、技术规范书的自动化交付体系，并提供了端到端确定性排版的最佳实践。",
        "keywords": "AI Agent；技术白皮书；数字化转型；确定性交付",
        "intro_heading": "一、行业背景与核心诉求",
        "intro_body": "随着多模态大模型与自主执行智能体的成熟，传统的“人工起草、人工排版、人工校对”流水线正迎来深刻重构。企业内部的技术文档、项目汇报与合规白皮书对专业性、品牌规范的一致性提出了极高要求。",
        "equation": "\\mathcal{L}_{\\text{total}} = \\alpha \\mathcal{L}_{\\text{content}} + \\beta \\mathcal{L}_{\\text{typography}}",
        "table_caption": "**表 1** 关键业务流程耗时对比（人天）",
        "table_header": "| 业务环节 | 传统交付流程 | 智能体 + 编译底座 | 效能提升倍数 |\n|:---|:---:|:---:|:---:|",
        "table_rows": "| 需求文档初稿 | 3.5 | 0.2 | 17.5x |\n| 合规与排版审核 | 2.0 | 0.05 | 40.0x |\n| 最终版式交付 | 1.0 | 0.01 | 100.0x |",
        "table_note": "注：数据基于 50 份企业真实技术交付件抽样统计。",
        "conclusion_heading": "二、实施建议与规划",
        "conclusion_body": "将格式规则声明为纯文本（如 format.txt）并纳入企业知识库与版本控制系统，是确保大模型生成内容不失真、不走样、可审计的基石。",
        "references": "[1] 中国信息通信研究院. 人工智能智能体发展报告[R]. 2025.\n[2] Vercel Labs. Agent Skills Standard Specification[R]. 2025.",
    },
    "en-paper": {
        "id": "en-paper",
        "name": "🔬 英文学术期刊 (Nature 规范)",
        "name_en": "English Academic Paper (Nature)",
        "preset": "en-nature",
        "doc_title": "Deterministic Compilation of Markdown Manuscripts into Compliant Word Documents",
        "abstract": "Automating document preparation for journal submissions has long been hindered by the non-deterministic nature of large language models and fragile ad-hoc scripts. In this paper, we introduce a declarative compilation pipeline that guarantees byte-identical Word (.docx) outputs from standard Markdown sources.",
        "keywords": "Document compilation; Agent Skills; Deterministic typography; OMML",
        "intro_heading": "1. Introduction",
        "intro_body": "Academic typography imposes stringent typographic and structural rules. In particular, equations must align in the center while their numbering sits hard against the right margin. Tables require three-line borders with repeating header rows across page breaks.",
        "equation": "\\nabla \\times \\mathbf{B} = \\mu_0 \\mathbf{J} + \\mu_0 \\varepsilon_0 \\frac{\\partial \\mathbf{E}}{\\partial t}",
        "table_caption": "**Table 1** Benchmark of Manuscript Compilation Methods",
        "table_header": "| Method | Compile Time | Native OMML | Repeating Header | Quality Gates |\n|:---|:---:|:---:|:---:|:---:|",
        "table_rows": "| Manual Word Editing | > 120 min | Yes | Manual | None |\n| Standard Pandoc | ~ 1.2 s | Partial | Needs filter | Silent errors |\n| **md-to-word (Ours)** | **~ 0.2 s** | **Yes** | **Automatic** | **Line-accurate** |",
        "table_note": "Note: Measured on an 8-page IEEE-style paper. Compile time is wall-clock time over 10 repeated trials.",
        "conclusion_heading": "2. Conclusion",
        "conclusion_body": "Our approach effectively decouples layout declarations from manuscript prose, enabling automated publication delivery.",
        "references": "[1] Knuth D E. The TeXbook[M]. Addison-Wesley, 1984.\n[2] Lamport L. LaTeX: a document preparation system[M]. Addison-Wesley, 1994.",
    },
}


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
) -> tuple[str, str]:
    """将用户填写的结构化表单组装为严格符合 md-to-word 规范的 Markdown。"""
    is_en = template_id == "en-paper"
    preset = "en-nature" if is_en else "zh-academic"

    title_tag = "%% Title" if is_en else "%% 文档标题"
    abstract_tag = "%% Abstract" if is_en else "%% 摘要"
    keywords_tag = "%% Keywords" if is_en else "%% 关键词"
    table_cap_tag = "%% Table Caption" if is_en else "%% 表题"
    table_note_tag = "%% Table Note" if is_en else "%% 表注"
    ref_title = "References" if is_en else "参考文献"

    tpl = TEMPLATES.get(template_id, TEMPLATES["zh-thesis"])

    table_block = f"{table_cap_tag} {tpl['table_caption']}\n\n{tpl['table_header']}\n{tpl['table_rows']}\n\n{table_note_tag} {tpl['table_note']}"

    # 处理段落
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
    return md_content, preset


@app.post("/api/preview")
async def preview_manuscript(
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
    """编译用户内容为 Word，并在服务端使用 LibreOffice 无头引擎渲染为多页 PDF 返回供前端展示。"""
    start_time = time.time()

    clean_md, preset = _assemble_markdown(
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

    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        md_path = temp_dir / "manuscript.md"
        md_path.write_text(clean_md, encoding="utf-8")

        docx_path = temp_dir / "output.docx"

        # 1. 调用确定性引擎编译 docx
        res = export(
            manuscript=md_path,
            output=docx_path,
            preset=preset,
        )

        if not res.ok:
            return JSONResponse(
                status_code=422,
                content={
                    "ok": False,
                    "errors": res.errors,
                    "messages": res.messages,
                },
            )

        # 2. 将 docx 转换为 PDF (Linux 无头 soffice)
        pdf_path = temp_dir / "output.pdf"
        try:
            subprocess.run(
                ["soffice", "--headless", "--convert-to", "pdf", str(docx_path)],
                cwd=str(temp_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=15,
                check=True,
            )
        except Exception as e:
            # 如果没有 soffice，回退友好提示
            return JSONResponse(
                status_code=500,
                content={"ok": False, "detail": f"服务端 PDF 转换服务异常: {str(e)}"},
            )

        if not pdf_path.exists():
            return JSONResponse(
                status_code=500,
                content={"ok": False, "detail": "PDF 文件生成失败"},
            )

        pdf_bytes = pdf_path.read_bytes()
        elapsed = round((time.time() - start_time) * 1000, 1)

        headers = {
            "Content-Type": "application/pdf",
            "X-Compile-Ok": "true",
            "X-Compile-Elapsed-Ms": str(elapsed),
            "Access-Control-Expose-Headers": "X-Compile-Ok, X-Compile-Elapsed-Ms",
        }

        return Response(content=pdf_bytes, media_type="application/pdf", headers=headers)


@app.post("/api/export")
async def export_manuscript(
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
    """编译用户修改的内容，直接返回可下载的 Word (.docx) 文件。"""
    start_time = time.time()

    clean_md, preset = _assemble_markdown(
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

    with tempfile.TemporaryDirectory() as td:
        temp_dir = Path(td)
        md_path = temp_dir / "manuscript.md"
        md_path.write_text(clean_md, encoding="utf-8")

        docx_path = temp_dir / "output.docx"

        res = export(
            manuscript=md_path,
            output=docx_path,
            preset=preset,
        )

        elapsed = round((time.time() - start_time) * 1000, 1)

        if not res.ok:
            return JSONResponse(
                status_code=422,
                content={
                    "ok": False,
                    "errors": res.errors,
                    "messages": res.messages,
                    "elapsed_ms": elapsed,
                },
            )

        docx_bytes = docx_path.read_bytes()

        # 生成友好下载文件名
        safe_title = re.sub(r'[\\/*?:"<>|]', "", doc_title.strip())[:30] or "document"
        filename = f"{safe_title}.docx"
        quoted_filename = urllib.parse.quote(filename)

        headers = {
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted_filename}",
            "X-Compile-Ok": "true",
            "X-Compile-Elapsed-Ms": str(elapsed),
            "Access-Control-Expose-Headers": "Content-Disposition, X-Compile-Ok, X-Compile-Elapsed-Ms",
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
