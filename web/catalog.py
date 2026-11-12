"""展示页四套样张的内容源：模板目录、稿件拼装、格式文件生成。只有纯函数。

`web/build.py` 拿它去编译 `docs/assets/` 里的成品；`tests/test_web_templates.py` 直接
导入它做检查。两边都不需要任何 Web 框架——展示页是静态的，没有后端。

这里是预设的第四份真相源（CLI / MCP / 包里 / 展示页）：新增一个预设，这里必须跟上，
否则页面上的样张与真正能用的格式就对不上了。
"""

from __future__ import annotations

import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

TEMPLATES = {
    "zh-journal": {
        "id": "zh-journal",
        "name": "中文学术期刊",
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
    "zh-tw-journal": {
        "id": "zh-tw-journal",
        "name": "繁體中文學術期刊",
        "name_en": "📘 Traditional Chinese Academic Journal",
        "badge": "臺灣 / 香港 學位論文",
        "badge_en": "Taiwan / HK Thesis",
        "desc": "新細明體 · 微軟正黑體 · 1.5 倍行距 · 首行縮進 2 字元 · 全形標點不壓縮 · 規範三線表",
        "desc_en": "PMingLiU · Microsoft JhengHei · 1.5x spacing · 2-char indent · Full-width punctuation uncompressed · Three-line table",
        "preset_file": str(BASE_DIR / "presets" / "zh-tw-academic.txt"),
        "preset_name": "zh-tw-academic",
        "header_content": "繁體中文學術期刊樣稿 · 學術文件確定性排版與雙向品質閘門技術研究",
        "doc_title": "學術文件確定性排版與雙向品質閘門編譯技術研究",
        "abstract": "【摘要】針對大型語言模型在學術出版交付中版式失真的問題，提出宣告式排版契約與雙向閘門編譯方法，實現跨平臺一致交付與規範違例攔截。",
        "keywords": "文件編譯器；確定性排版；品質閘門；原生 OMML；三線表",
        "intro_heading": "一、研究背景與系統架構",
        "intro_body": "學術出版對排版有嚴苛指標。本引擎透過宣告式契約，於編譯前後各執行一道對帳，保證產物逐位元組一致，公式自動轉為原生向量並靠右編號。",
        "equation": r"\iint_{\Omega} \left( \nabla \times \mathbf{u} \right) \cdot d\mathbf{S} = \oint_{\partial \Omega} \mathbf{u} \cdot d\mathbf{r} \quad \Longleftrightarrow \quad \det \begin{pmatrix} \frac{\partial^2 \Phi}{\partial x^2} - \lambda & \frac{\partial^2 \Phi}{\partial x \partial y} \\ \frac{\partial^2 \Phi}{\partial y \partial x} & \frac{\partial^2 \Phi}{\partial y^2} - \lambda \end{pmatrix} = 0",
        "table_caption": "**表 1** 論文排版方案比較",
        "table_content": "| 編譯方案 | 交付耗時 | 公式向量 | 跨頁重複 | 閘門對帳 |\n|:---|:---:|:---:|:---:|:---:|\n| 人工 Word | > 2h | 是 | 手動設定 | 人工目視 |\n| **md-to-word** | **0.2s** | **原生 OMML** | **全自動** | **行號級對帳** |",
        "table_note": "註：基準測試連續執行 10 次，取耗時中位數。",
        "conclusion_heading": "二、結論",
        "conclusion_body": "將排版規則宣告化並納入版本控制，解決了 AI 交付的最後一哩路。",
        "references": "[1] Knuth D E. The TeXbook[M]. Addison-Wesley, 1984.\n[2] 張三, 李四. 確定性排版體系[J]. 計算機工程與科學技術, 2025.",
        "specs_zh": {
            "header": "頁眉：微軟正黑體/Times New Roman 小五(9pt) · 置中對齊 · 行距1.0倍 · 下邊框單線 · 距頂端1.5cm",
            "title": "文件標題：微軟正黑體/Times New Roman 二號(22pt) · 加粗 · 置中 · 行距1.5倍 · 段前0磅 / 段後12磅 · 首行縮進0字元",
            "abstract": "摘要內容：新細明體/Times New Roman 小四(12pt) · 兩端對齊 · 行距1.5倍 · 首行縮進2字元 · 段前0磅 / 段後6磅",
            "keywords": "關鍵詞：新細明體/Times New Roman 小四(12pt) · 兩端對齊 · 行距1.5倍 · 首行不縮進 · 段前0磅 / 段後12磅",
            "intro_heading": "章節標題：微軟正黑體/Times New Roman 三號(16pt) · 加粗 · 置中 · 行距1.5倍 · 段前18磅 / 段後12磅 · 與下段同頁",
            "body": "正文段落：新細明體/Times New Roman 小四(12pt) · 兩端對齊 · 行距1.5倍 · 首行縮進2字元 · 段前0磅 / 段後0磅",
            "equation": "數學公式：原生 OMML 向量公式 · 置中對齊 · 編號 (#eq-1) 靠右對齊 · 可直接雙擊編輯",
            "table_caption": "表題：新細明體/Times New Roman 五號(10.5pt) · 加粗 · 置中 · 行距1.5倍 · 段前6磅 / 段後6磅 · 與下段同頁",
            "table": "表格：標準三線表(頂線1.5磅 / 底線1.5磅 / 表頭線0.75磅) · 表頭加粗置中 · 儲存格垂直置中 · 跨頁自動重複表頭",
            "table_note": "表註：新細明體/Times New Roman 小五(9pt) · 置中 · 行距1.0倍 · 段前0磅 / 段後6磅",
            "conclusion_heading": "結論標題：微軟正黑體/Times New Roman 三號(16pt) · 加粗 · 置中 · 行距1.5倍 · 段前18磅 / 段後12磅 · 與下段同頁",
            "conclusion_body": "結論正文：新細明體/Times New Roman 小四(12pt) · 兩端對齊 · 行距1.5倍 · 首行縮進2字元 · 段前0磅 / 段後0磅",
            "references": "參考文獻：新細明體/Times New Roman 五號(10.5pt) · 左對齊 · 行距1.25倍 · 懸掛縮進0.5英寸",
        },
        "specs_en": {
            "header": "Header: Microsoft JhengHei/Times New Roman 9pt · Center · Line spacing 1.0 · Single bottom border · Top 1.5cm",
            "title": "Title: Microsoft JhengHei/Times New Roman 22pt · Bold · Center · 1.5 line spacing · Space after 12pt · Indent 0",
            "abstract": "Abstract: PMingLiU/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 2 chars · Space after 6pt",
            "keywords": "Keywords: PMingLiU/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 0 · Space after 12pt",
            "intro_heading": "Section Heading: Microsoft JhengHei/Times New Roman 16pt · Bold · Center · Space before 18pt / Space after 12pt · Keep with next",
            "body": "Body Text: PMingLiU/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 2 chars · Space 0pt",
            "equation": "Equation: Native OMML math equation · Centered · Numbering (#eq-1) aligned hard right · Double-click editable",
            "table_caption": "Table Caption: PMingLiU/Times New Roman 10.5pt · Bold · Center · Space before 6pt / Space after 6pt · Keep with next",
            "table": "Table: Three-line table (Top 1.5pt / Bottom 1.5pt / Header 0.75pt) · Center · Repeating header row",
            "table_note": "Table Note: PMingLiU/Times New Roman 9pt · Center · Line spacing 1.0 · Space after 6pt",
            "conclusion_heading": "Conclusion Heading: Microsoft JhengHei/Times New Roman 16pt · Bold · Center · Space before 18pt / Space after 12pt",
            "conclusion_body": "Conclusion Body: PMingLiU/Times New Roman 12pt · Justified · 1.5 line spacing · Indent 2 chars · Space 0pt",
            "references": "References: PMingLiU/Times New Roman 10.5pt · Left · Line spacing 1.25 · Hanging indent 0.5 in",
        },
    },
    "zh-report": {
        "id": "zh-report",
        "name": "现代技术白皮书",
        "name_en": "📄 Technical White Paper",
        "badge": "技术报告",
        "badge_en": "Technical White Paper",
        "desc": "彩色标题(#1F4E79) · 全网格商务表 · 首行不缩进 · 单线企业页眉 · 极简1页",
        "desc_en": "Color heading (#1F4E79) · Grid table · 0 indent · Single rule header · Compact 1 page",
        "preset_file": str(BASE_DIR / "presets" / "zh-report.txt"),
        "preset_name": "zh-report",
        "header_content": "智能体自主交付技术白皮书",
        "doc_title": "2026 年度智能体自主交付技术白皮书",
        "abstract": "【摘要】本白皮书梳理自主智能体在企业数字化场景落地实践，提出基于版本化约束文件的确定性排版架构。",
        "keywords": "智能体；数字化交付；技术白皮书；确定性排版",
        "intro_heading": "一、核心架构与效能评估",
        "intro_body": "自主智能体承担了越来越多文档起草工作，传统的“起草-排版-核验”流程面临重塑。把排版规范抽象成一份随稿件入库的声明式配置后，编译一次即可得到符合该规范的 Word 文档。",
        "equation": r"\mathbf{x}_{k+1} = \mathbf{A}\mathbf{x}_k + \mathbf{B}\mathbf{u}_k + \mathbf{w}_k, \quad \min_{\{\mathbf{u}_k\}} \sum_{k=0}^{K-1} \left( \mathbf{x}_k^T \mathbf{Q} \mathbf{x}_k + \mathbf{u}_k^T \mathbf{R} \mathbf{u}_k \right)",
        "table_caption": "**表 1** 交付环节对照",
        "table_content": "| 交付环节 | 传统人工 | 声明式编译 |\n|:---|:---|:---|\n| 版式来源 | 手工设置或套用模板 | 一份随稿件入库的 `format.txt` |\n| 核验方式 | 逐页目检 | 导出前后各一道门禁，报行号 |\n| 返工 | 改一处、查全文 | 改配置重编译，产物可逐字节比对 |",
        "table_note": "注：本表只作流程对照，不含实测数据。",
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
        "name": "英文学术期刊",
        "name_en": "🔬 English Academic Paper (Nature)",
        "badge": "Nature / IEEE",
        "badge_en": "Nature / IEEE",
        "desc": "Times New Roman · APA 规范 · 居中公式靠右编号 · 规范三线表 · 紧凑1页",
        "desc_en": "Times New Roman · APA citation · Centered equation with right number · Three-line table · Compact 1 page",
        "preset_file": str(BASE_DIR / "presets" / "en-nature.txt"),
        "preset_name": "en-nature",
        "header_content": "NATURE COMPUTATIONAL SCIENCE | RESEARCH ARTICLE",
        "doc_title": "Deterministic Compilation of Markdown Manuscripts into Compliant Word Documents",
        "abstract": "Preparing document submission formats programmatically is often undermined by non-deterministic large language models. Here we demonstrate a declarative compiler that maps standard Markdown to Word (.docx) documents that follow a declared format, with byte-identical reproducibility and pre- and post-export quality gates.",
        "keywords": "Document compilation; Agent Skills; Deterministic typography; Native OMML; Quality gates",
        "intro_heading": "1. Introduction",
        "intro_body": "Scientific manuscripts require rigorous typographic consistency. Equations must align centrally with numbering pinned hard to the right margin, while tables demand standard three-line borders with repeating header rows across page splits.",
        "equation": r"i\hbar \frac{\partial}{\partial t} \Psi(\mathbf{r}, t) = \left[ -\frac{\hbar^2}{2m} \nabla^2 + V(\mathbf{r}, t) \right] \Psi(\mathbf{r}, t) \quad \Longleftrightarrow \quad \mathcal{H} = \sum_{k} \varepsilon_k c_k^\dagger c_k + \frac{1}{2} \sum_{ijkl} V_{ijkl} c_i^\dagger c_j^\dagger c_l c_k",
        "table_caption": "**Table 1** Where each declared setting ends up",
        "table_content": "| Aspect | Declared in `format.txt` | Checked after export |\n|:---|:---|:---:|\n| Typography | font, size, spacing, indent per style | yes |\n| Equations | numbering and cross-references | yes |\n| Tables | three-line or grid, repeating header | yes |",
        "table_note": "Note: this table describes the declared format, not benchmark results.",
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
    ref_title = "References" if is_en else (
        "參考文獻" if template_id == "zh-tw-journal" else "参考文献"
    )

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
    elif template_id == "zh-tw-journal":
        # 繁體中文學術期刊：單線頁眉、置中，標楷/正黑體
        header_rule = f"页眉：微軟正黑體/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 下边框单线\n页眉内容：{clean_header}"
    else:
        # 英文 Nature：单线页眉，右对齐
        header_rule = f"页眉：Times New Roman 小五 不加粗 不倾斜 右对齐 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 下边框单线\n页眉内容：{clean_header}"

    # 如果已有页眉声明，则替换；否则追加
    if "页眉内容：" in base_text:
        base_text = re.sub(r"页眉内容：[^\n]*", f"页眉内容：{clean_header}", base_text)
        return base_text
    else:
        return f"{base_text}\n\n{header_rule}\n"
