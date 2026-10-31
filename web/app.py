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


# 三套精挑细选的标准场景模板（严谨学术/技术内容，篇幅精准控制在 1~2 页，彻底中立不侵犯第三方实体）
TEMPLATES = {
    "zh-journal": {
        "id": "zh-journal",
        "name": "📰 中文学术期刊",
        "name_en": "📰 Chinese Academic Journal",
        "badge": "GB/T 学术期刊",
        "badge_en": "GB/T Journal",
        "desc": "宋体/Times New Roman · 1.5倍行距 · 首行缩进2字符 · 双线页眉 · 规范三线表",
        "desc_en": "SongTi/Times New Roman · 1.5x line space · 2-char indent · Double rule header · Three-line table",
        "preset_file": str(BASE_DIR / "presets" / "zh-academic.txt"),
        "preset_name": "zh-academic",
        "header_content": "中文学术期刊样稿 · 学术文档确定性排版与双向门禁技术研究",
        "doc_title": "学术文档确定性排版与双向质量门禁编译技术研究",
        "abstract": "【摘要】针对大模型在学术出版物交付中版式失真的问题，提出声明式排版契约与双向门禁编译方法，实现跨平台一致交付与规范违例拦截。",
        "keywords": "文档编译器；确定性排版；质量门禁；原生OMML；三线表",
        "intro_heading": "1. 引言与系统架构",
        "intro_body": "学术出版物对排版有着严苛指标。本引擎通过声明式契约在编译前后执行对账，保证产物逐字节完全一致，公式自动转为原生矢量并靠右编号。",
        "equation": r"\iint_{\Omega} \left( \nabla \times \mathbf{u} \right) \cdot d\mathbf{S} = \oint_{\partial \Omega} \mathbf{u} \cdot d\mathbf{r} \quad \Longleftrightarrow \quad \det \begin{pmatrix} \frac{\partial^2 \Phi}{\partial x^2} - \lambda & \frac{\partial^2 \Phi}{\partial x \partial y} \\ \frac{\partial^2 \Phi}{\partial y \partial x} & \frac{\partial^2 \Phi}{\partial y^2} - \lambda \end{pmatrix} = 0",
        "table_caption": "**表 1** 论文排版方案对比",
        "table_content": "| 编译方案 | 交付耗时 | 公式矢量 | 跨页重复 | 门禁对账 |\n|:---|:---:|:---:|:---:|:---:|\n| 手工 Word | > 2h | 是 | 手工设置 | 人工肉眼 |\n| **md-to-word** | **0.2s** | **原生 OMML** | **全自动** | **行号级对账** |",
        "table_note": "注：基准测试连续运行 10 次取耗时中位数。",
        "conclusion_heading": "2. 结论",
        "conclusion_body": "将排版规则声明化并纳入 Git 管理，解决了 AI 交付最后一公里难题。",
        "references": "[1] Knuth D E. The TeXbook[M]. Addison-Wesley, 1984.\n[2] 张三, 李四. 确定性排版体系[J]. 计算机工程与科学技术, 2025.",
        "specs_zh": {
            "header": "页眉：宋体/Times New Roman 小五(9pt) · 居中对齐 · 行距1.0倍 · 下边框双线(上粗下细双实线) · 距顶端1.5cm",
            "title": "文档标题：黑体/Times New Roman 二号(22pt) · 加粗 · 居中 · 行距1.5倍 · 段前0磅 / 段后12磅 · 首行缩进0字符 · 无边框",
            "abstract": "摘要内容：宋体/Times New Roman 五号(10.5pt) · 两端对齐 · 行距1.5倍 · 首行缩进2字符 · 段前0磅 / 段后6磅",
            "keywords": "关键词：宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行不缩进 · 段前0磅 / 段后12磅",
            "intro_heading": "章节标题：黑体/Times New Roman 三号(16pt) · 加粗 · 居中 · 行距1.5倍 · 段前18磅 / 段后12磅 · 与下段同页(防孤行)",
            "body": "正文段落：宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行缩进2字符 · 段前0磅 / 段后0磅",
            "equation": "数学公式：原生 Office Open XML (OMML) 矢量公式 · 居中对齐 · 编号 (#eq-1) 严格靠右对齐 · 双击直接编辑",
            "table_caption": "表题：宋体/Times New Roman 五号(10.5pt) · 加粗 · 居中 · 行距1.5倍 · 段前6磅 / 段后6磅 · 与下段同页",
            "table": "表格网格：标准三线表(顶线1.5磅/底线1.5磅/表头线0.75磅) · 表头加粗居中 · 单元格垂直居中 · 跨页自动重复表头",
            "table_note": "表注：宋体/Times New Roman 小五(9pt) · 居中 · 行距1.0倍 · 段前0磅 / 段后6磅",
            "conclusion_heading": "结论标题：黑体/Times New Roman 三号(16pt) · 加粗 · 居中 · 行距1.5倍 · 段前18磅 / 段后12磅 · 与下段同页",
            "conclusion_body": "结论正文：宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行缩进2字符 · 段前0磅 / 段后0磅",
            "references": "参考文献：宋体/Times New Roman 五号(10.5pt) · 两端对齐 · 行距1.25倍 · 悬挂缩进0.5英寸(2字符) · GB/T 7714 顺序编码制",
        },
        "specs_en": {
            "header": "Header: SongTi/Times New Roman 9pt · Center · Line spacing 1.0 · Double bottom border · Top 1.5cm",
            "title": "Title: SimHei/Times New Roman 22pt · Bold · Center · 1.5 line spacing · Space before 0pt / Space after 12pt · Indent 0",
            "abstract": "Abstract: SongTi/Times New Roman 10.5pt · Justified · 1.5 line spacing · Indent 2 chars · Space before 0pt / Space after 6pt",
            "keywords": "Keywords: SongTi/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 0 · Space after 12pt",
            "intro_heading": "Section Heading: SimHei/Times New Roman 16pt · Bold · Center · Space before 18pt / Space after 12pt · Keep with next",
            "body": "Body Text: SongTi/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 2 chars · Space before 0pt / Space after 0pt",
            "equation": "Equation: Native OMML math equation · Centered · Numbering (#eq-1) aligned hard right · Double-click editable",
            "table_caption": "Table Caption: SongTi/Times New Roman 10.5pt · Bold · Center · Space before 6pt / Space after 6pt · Keep with next",
            "table": "Table: Three-line publication table (Top 1.5pt / Bottom 1.5pt / Header 0.75pt) · Center · Repeating header row",
            "table_note": "Table Note: SongTi/Times New Roman 9pt · Center · Line spacing 1.0 · Space before 0pt / Space after 6pt",
            "conclusion_heading": "Conclusion Heading: SimHei/Times New Roman 16pt · Bold · Center · Space before 18pt / Space after 12pt · Keep with next",
            "conclusion_body": "Conclusion Body: SongTi/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 2 chars · Space 0pt",
            "references": "References: SongTi/Times New Roman 10.5pt · Justified · Line spacing 1.25 · Hanging indent 0.5 in · GB/T 7714 numeric",
        },
    },
    "zh-report": {
        "id": "zh-report",
        "name": "📄 现代技术白皮书",
        "name_en": "📄 Technical White Paper",
        "badge": "企业级技术报告",
        "badge_en": "Enterprise White Paper",
        "desc": "彩色标题(#1F4E79) · 全网格商务表 · 首行不缩进 · 单线企业页眉 · 极简1页",
        "desc_en": "Color heading (#1F4E79) · Grid table · 0 indent · Single rule header · Compact 1 page",
        "preset_file": str(BASE_DIR / "presets" / "zh-report.txt"),
        "preset_name": "zh-report",
        "header_content": "企业级智能体自主交付技术白皮书",
        "doc_title": "2026 年度企业级智能体自主交付技术白皮书",
        "abstract": "【摘要】本白皮书梳理自主智能体在企业数字化场景落地实践，提出基于版本化约束文件的确定性排版架构。",
        "keywords": "智能体；数字化交付；技术白皮书；确定性排版",
        "intro_heading": "一、核心架构与效能评估",
        "intro_body": "自主智能体深入企业生产业务，传统的“起草-排版-核验”流程面临全面重塑。将品牌规范抽象为声明式配置，可在数十毫秒内交付出版级技术报告。",
        "equation": r"\mathbf{x}_{k+1} = \mathbf{A}\mathbf{x}_k + \mathbf{B}\mathbf{u}_k + \mathbf{w}_k, \quad \min_{\{\mathbf{u}_k\}} \sum_{k=0}^{K-1} \left( \mathbf{x}_k^T \mathbf{Q} \mathbf{x}_k + \mathbf{u}_k^T \mathbf{R} \mathbf{u}_k \right)",
        "table_caption": "**表 1** 核心环节效率提升测算（人天）",
        "table_content": "| 交付环节 | 传统人工 | 智能体底座 | 效能提升 |\n|:---|:---:|:---:|:---:|\n| 需求初稿 | 3.5 | 0.2 | 17.5x |\n| 版式核验 | 2.0 | 0.05 | 40.0x |\n| 最终交付 | 1.0 | 0.01 | 100.0x |",
        "table_note": "注：基于企业真实技术交付件样本测算。",
        "conclusion_heading": "二、交付建议",
        "conclusion_body": "建议将排版规范纳入企业版本控制，生成内容经双向门禁拦截后分发。",
        "references": "[1] 数字化智能交付技术联盟. 企业智能体交付标准规范[R]. 2025.\n[2] Agent Skills. Declarative Typography Specification[R]. 2025.",
        "specs_zh": {
            "header": "页眉：宋体/Times New Roman 小五(9pt) · 右对齐 · 行距1.0倍 · 下边框单线(0.75磅) · 距顶端1.5cm",
            "title": "文档标题：黑体/Times New Roman 二号(22pt) · 加粗 · 居中 · 品牌色#1F4E79 · 行距1.5倍 · 段前0磅 / 段后12磅 · 首行不缩进",
            "abstract": "执行摘要：宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行不缩进(0字符) · 段前0磅 / 段后6磅",
            "keywords": "关键词：宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行不缩进 · 段前0磅 / 段后12磅",
            "intro_heading": "章节标题：黑体/Times New Roman 三号(16pt) · 加粗 · 居中 · 品牌色#1F4E79 · 行距1.5倍 · 段前18磅 / 段后12磅 · 与下段同页",
            "body": "正文段落：宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行不缩进(0字符) · 段前0磅 / 段后6磅(现代报告段落间距)",
            "equation": "数学公式：原生 OMML 矢量数学公式 · 居中对齐 · 编号 (#eq-1) 靠右对齐 · 状态转移优化方程",
            "table_caption": "表题：宋体/Times New Roman 五号(10.5pt) · 加粗 · 居中 · 行距1.5倍 · 段前6磅 / 段后6磅 · 与下段同页",
            "table": "全网格商务数据表：顶底线0.75磅 · 内部网格线0.5磅 · 单元格文字垂直居中 · 跨页自动重复表头",
            "table_note": "表注：宋体/Times New Roman 小五(9pt) · 居中 · 行距1.0倍 · 段前0磅 / 段后6磅",
            "conclusion_heading": "结论标题：黑体/Times New Roman 三号(16pt) · 加粗 · 居中 · 品牌色#1F4E79 · 行距1.5倍 · 段前18磅 / 段后12磅 · 与下段同页",
            "conclusion_body": "结论正文：宋体/Times New Roman 小四(12pt) · 两端对齐 · 行距1.5倍 · 首行不缩进(0字符) · 段前0磅 / 段后6磅",
            "references": "参考文献：Times New Roman 五号(10.5pt) · 两端对齐 · 行距1.25倍 · 悬挂缩进0.5英寸",
        },
        "specs_en": {
            "header": "Header: SongTi/Times New Roman 9pt · Right align · Line spacing 1.0 · Single rule border (0.75pt) · Top 1.5cm",
            "title": "Title: SimHei/Times New Roman 22pt · Bold · Center · Color #1F4E79 · 1.5 line spacing · Indent 0",
            "abstract": "Executive Summary: SongTi/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 0 · Space after 6pt",
            "keywords": "Keywords: SongTi/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 0 · Space after 12pt",
            "intro_heading": "Section Heading: SimHei/Times New Roman 16pt · Bold · Center · Color #1F4E79 · Space before 18pt / Space after 12pt",
            "body": "Body Text: SongTi/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 0 · Space after 6pt",
            "equation": "Equation: Native OMML math equation · Centered · Numbering (#eq-1) aligned hard right · State optimization",
            "table_caption": "Table Caption: SongTi/Times New Roman 10.5pt · Bold · Center · Space before 6pt / Space after 6pt · Keep with next",
            "table": "Grid Table: Top/Bottom 0.75pt · Inside grid 0.5pt · Centered text · Repeating header row",
            "table_note": "Table Note: SongTi/Times New Roman 9pt · Center · Line spacing 1.0 · Space before 0pt / Space after 6pt",
            "conclusion_heading": "Conclusion Heading: SimHei/Times New Roman 16pt · Bold · Center · Color #1F4E79 · Space before 18pt / Space after 12pt",
            "conclusion_body": "Conclusion Body: SongTi/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 0 · Space after 6pt",
            "references": "References: Times New Roman 10.5pt · Justified · Line spacing 1.25 · Hanging indent 0.5 in",
        },
    },
    "en-paper": {
        "id": "en-paper",
        "name": "🔬 英文学术期刊",
        "name_en": "🔬 English Academic Paper (Nature)",
        "badge": "Nature / IEEE",
        "badge_en": "Nature / IEEE",
        "desc": "Times New Roman · APA 规范 · 居中公式靠右编号 · 规范三线表 · 紧凑1页",
        "desc_en": "Times New Roman · APA citation · Centered equation with right number · Three-line table · Compact 1 page",
        "preset_file": str(BASE_DIR / "presets" / "en-nature.txt"),
        "preset_name": "en-nature",
        "header_content": "NATURE COMPUTATIONAL SCIENCE | RESEARCH ARTICLE",
        "doc_title": "Deterministic Compilation of Markdown Manuscripts into Compliant Word Documents",
        "abstract": "Automating publication-grade document preparation has long been challenged by non-deterministic large language models. Here, we demonstrate a declarative document compiler that maps standard Markdown to strictly compliant Word (.docx) documents with byte-identical reproducibility and bidirectional quality gates.",
        "keywords": "Document compilation; Agent Skills; Deterministic typography; Native OMML; Quality gates",
        "intro_heading": "1. Introduction",
        "intro_body": "Scientific manuscripts require rigorous typographic consistency. Equations must align centrally with numbering pinned hard to the right margin, while tables demand standard three-line borders with repeating header rows across page splits.",
        "equation": r"i\hbar \frac{\partial}{\partial t} \Psi(\mathbf{r}, t) = \left[ -\frac{\hbar^2}{2m} \nabla^2 + V(\mathbf{r}, t) \right] \Psi(\mathbf{r}, t) \quad \Longleftrightarrow \quad \mathcal{H} = \sum_{k} \varepsilon_k c_k^\dagger c_k + \frac{1}{2} \sum_{ijkl} V_{ijkl} c_i^\dagger c_j^\dagger c_l c_k",
        "table_caption": "**Table 1** Benchmark of Manuscript Compilation Methods",
        "table_content": "| Method | Compile Time | Native OMML | Repeating Header | Quality Gates |\n|:---|:---:|:---:|:---:|:---:|\n| Manual Word | > 120 min | Yes | Manual Setup | Manual |\n| Standard Pandoc | ~ 1.2 s | Partial | Filter Required | Silent Failure |\n| **md-to-word (Ours)** | **~ 0.2 s** | **Yes (Vector)** | **Fully Automatic** | **Line-accurate** |",
        "table_note": "Note: Measured on an IEEE-style paper across 10 repeated trials.",
        "conclusion_heading": "2. Conclusion",
        "conclusion_body": "Decoupling style contracts from manuscript content bridges the last mile of autonomous AI delivery.",
        "references": "[1] Knuth D E. The TeXbook[M]. Addison-Wesley, 1984.\n[2] Lamport L. LaTeX: a document preparation system[M]. Addison-Wesley, 1994.",
        "specs_zh": {
            "header": "页眉：Times New Roman 小五(9pt) · 右对齐 · 单倍行距 · 下边框单线 · 距顶端1.5cm",
            "title": "文档标题：Times New Roman 18pt · 加粗 · 居中 · 1.5倍行距 · 段前0磅 / 段后12磅",
            "abstract": "摘要：Times New Roman 10pt · 两端对齐 · 行距1.2倍 · 首行不缩进 · 段前6磅 / 段后6磅",
            "keywords": "关键词：Times New Roman 10pt · 两端对齐 · 行距1.2倍 · 段后12磅",
            "intro_heading": "章节标题：Times New Roman 14pt · 加粗 · 居中 · 段前18磅 / 段后12磅 · 与下段同页",
            "body": "正文段落：Times New Roman 11pt · 两端对齐 · 行距1.3倍 · 首行不缩进 · 段后6磅",
            "equation": "数学公式：原生 OMML 矢量公式 · 居中对齐 · 编号 (#eq-1) 靠右对齐 · 双击直接编辑",
            "table_caption": "表题：Times New Roman 9pt · 加粗 · 居中 · 段前6磅 / 段后6磅 · 与下段同页",
            "table": "表格网格：标准三线表(顶线1.5磅/底线1.5磅/表头线0.75磅) · 居中 · 跨页自动重复表头",
            "table_note": "表注：Times New Roman 8.5pt · 居中 · 段前0磅 / 段后6磅",
            "conclusion_heading": "结论标题：Times New Roman 14pt · 加粗 · 居中 · 段前18磅 / 段后12磅 · 与下段同页",
            "conclusion_body": "结论正文：Times New Roman 11pt · 两端对齐 · 行距1.3倍 · 首行不缩进 · 段后6磅",
            "references": "参考文献：Times New Roman 9pt · 两端对齐 · 悬挂缩进0.5英寸 · APA 引用标准",
        },
        "specs_en": {
            "header": "Header: Times New Roman 9pt · Right align · Single spacing · Clean rule border beneath",
            "title": "Title: Times New Roman 18pt · Bold · Centered · 1.5 line spacing · Space before 0pt / Space after 12pt",
            "abstract": "Abstract: Times New Roman 10pt · Justified · Line spacing 1.2 · Indent 0 · Space before 6pt / Space after 6pt",
            "keywords": "Keywords: Times New Roman 10pt · Justified · Line spacing 1.2 · Space after 12pt",
            "intro_heading": "Section Heading: Times New Roman 14pt · Bold · Centered · Space before 18pt / Space after 12pt · Keep with next",
            "body": "Body Text: Times New Roman 11pt · Justified · Line spacing 1.3 · Indent 0 · Space after 6pt",
            "equation": "Equation: Native OMML math equation · Centered · Numbering (#eq-1) aligned hard right · Double-click editable",
            "table_caption": "Table Caption: Times New Roman 9pt · Bold · Centered · Space before 6pt / Space after 6pt · Keep with next",
            "table": "Table: Three-line publication table (Top 1.5pt / Bottom 1.5pt / Header 0.75pt) · Centered · Repeating header row",
            "table_note": "Table Note: Times New Roman 8.5pt · Centered · Space before 0pt / Space after 6pt",
            "conclusion_heading": "Conclusion Heading: Times New Roman 14pt · Bold · Centered · Space before 18pt / Space after 12pt · Keep with next",
            "conclusion_body": "Conclusion Body: Times New Roman 11pt · Justified · Line spacing 1.3 · Space after 6pt",
            "references": "References: Times New Roman 9pt · Justified · Hanging indent 0.5 in · APA citation style",
        },
    },
}

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


def _assemble_markdown(
    template_id: str,
    doc_title: str,
    abstract: str,
    keywords: str,
    intro_heading: str,
    intro_body: str,
    equation: str,
    table_caption: str,
    table_content: str,
    table_note: str,
    conclusion_heading: str,
    conclusion_body: str,
    references: str,
) -> str:
    """将表单组装为标准 Markdown 文本。"""
    is_en = template_id == "en-paper"

    title_tag = "%% Title" if is_en else "%% 文档标题"
    abstract_tag = "%% Abstract" if is_en else "%% 摘要"
    keywords_tag = "%% Keywords" if is_en else "%% 关键词"
    table_cap_tag = "%% Table Caption" if is_en else "%% 表题"
    table_note_tag = "%% Table Note" if is_en else "%% 表注"
    ref_title = "References" if is_en else "参考文献"

    table_block = f"{table_cap_tag} {table_caption.strip()}\n\n{table_content.strip()}\n\n{table_note_tag} {table_note.strip()}"

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
    return md_content


def _build_dynamic_format(template_id: str, header_content: str) -> str:
    """基于底层官方预设文件，动态注入用户指定的页眉规则与页眉文字。"""
    tpl = TEMPLATES.get(template_id, TEMPLATES["zh-journal"])
    base_file = Path(tpl["preset_file"])
    base_text = base_file.read_text(encoding="utf-8") if base_file.exists() else ""

    clean_header = header_content.strip() or "md-to-word"

    if template_id == "zh-journal":
        # 中文学术期刊：双线页眉，居中对齐
        header_rule = f"页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 下边框双线\n页眉内容：{clean_header}"
    elif template_id == "zh-report":
        # 现代技术白皮书：单线页眉，右对齐
        header_rule = f"页眉：宋体/Times New Roman 小五 不加粗 不倾斜 右对齐 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 下边框单线\n页眉内容：{clean_header}"
    else:
        # 英文 Nature：单线页眉，右对齐
        header_rule = f"页眉：Times New Roman 小五 不加粗 不倾斜 右对齐 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 下边框单线\n页眉内容：{clean_header}"

    # 如果已有页眉声明，则替换；否则追加
    if "页眉内容：" in base_text:
        base_text = re.sub(r"页眉内容：[^\n]*", f"页眉内容：{clean_header}", base_text)
        return base_text
    else:
        return f"{base_text}\n\n{header_rule}\n"


def _get_content_hash(template_id: str, md_content: str, header_content: str) -> str:
    """计算模板 ID、正文与页眉的唯一哈希值，作为静态缓存 Key。"""
    raw = f"{template_id}:{header_content.strip()}:{md_content.strip()}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _compile_docx_and_pdf(
    md_content: str,
    format_text: str,
    output_docx_path: Path,
    output_pdf_path: Path,
) -> Tuple[bool, list]:
    """同步编译生成 docx，并调用 soffice 转换为 pdf。"""
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
            return False, res.errors

        # 复制到目标 docx 路径
        output_docx_path.write_bytes(tmp_docx.read_bytes())

        # 调用 soffice 转 pdf
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", str(tmp_docx)],
            cwd=str(temp_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=True,
        )

        tmp_pdf = temp_dir / "output.pdf"
        if not tmp_pdf.exists():
            return False, ["PDF 文件转换输出失败"]

        output_pdf_path.write_bytes(tmp_pdf.read_bytes())
        return True, []


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
                ok, errs = _compile_docx_and_pdf(md, fmt_text, docx_cache, pdf_cache)
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
        ok, errors = await loop.run_in_executor(
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
            ok, errors = await loop.run_in_executor(
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
