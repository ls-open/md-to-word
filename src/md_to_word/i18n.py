"""md_to_word.i18n — 面向用户的少量消息双语。

只覆盖「人直接看到」的那一层：命令行帮助、流水线进度与结论、导出后的核对提醒。
门禁逐条的细节仍是中文——它们服务于改稿，Agent 会转述给用户。

语种判定复用 `config.looks_chinese`：数正文汉字占比，跳过 `%%` 样式行。所以同一份
英文稿不会因为 `%% 表题` 这类词表写法被认成中文稿。
"""

from __future__ import annotations

from md_to_word.config import looks_chinese

SUPPORTED = ("zh", "en")

_MESSAGES: dict[str, tuple[str, str]] = {
    # ── 命令行 ──────────────────────────────────────────────────────
    "cli.description": (
        "现代学术 Markdown 到期刊/学位规范 Word (.docx) 编译引擎",
        "Compile Markdown into publication-ready Word (.docx)",
    ),
    "cli.exit_codes": (
        "退出码: 0=成功 / 1=稿件或门禁问题 / 3=docx 已生成但 PDF 未渲染",
        "Exit codes: 0=ok / 1=manuscript or gate failure / 3=docx written, PDF skipped",
    ),
    "cli.input": ("输入的 Markdown 稿件 (.md)", "Input Markdown manuscript (.md)"),
    "cli.output": ("输出的 Word 文档路径 (.docx)", "Output .docx path"),
    "cli.requirements": (
        "格式要求文件 (.txt)；未传时优先按同目录唯一 .txt 或内置预设",
        "Format requirements (.txt); falls back to the only .txt beside the manuscript or a preset",
    ),
    "cli.preset": (
        "内置格式预设：zh-academic（中文学术默认）或 en-nature（英文国际期刊）",
        "Built-in preset: zh-academic (Chinese thesis) or en-nature (international journal)",
    ),
    "cli.template": (
        "可选：指定现成 Word 样式模板 (.docx)",
        "Optional: an existing .docx to take styles from",
    ),
    "cli.lang": ("消息语言：auto=按稿件语种 / zh / en", "Message language: auto / zh / en"),
    "cli.no_check": ("跳过导前语法与排版契约预检（不推荐）", "Skip the pre-flight check (not recommended)"),
    "cli.no_postflight": ("跳过产物数值防丢检查（不推荐）", "Skip the numeric-integrity check (not recommended)"),
    "cli.no_audit": ("跳过产物与格式要求逐条对账抽查", "Skip the post-export audit against requirements"),
    "cli.pdf": ("导出后再渲染一份 PDF 供核对（macOS + 本机 Word）", "Also render a PDF for review (macOS + local Word)"),
    "cli.input_required": ("缺少稿件路径：md-to-word 稿件.md", "Missing manuscript path: md-to-word paper.md"),
    "cli.contract": ("打印稿件契约速查后退出（不导出）", "Print the manuscript contract cheatsheet and exit"),
    # ── 流水线：路径与配置 ──────────────────────────────────────────
    "pipeline.input_missing": ("输入稿件不存在: {path}", "Input manuscript not found: {path}"),
    "pipeline.requirements_missing": ("指定的格式要求文件不存在: {path}", "Requirements file not found: {path}"),
    "pipeline.preset_missing": ("未找到预设: {name}", "Preset not found: {name}"),
    "pipeline.many_txt": (
        "{dir} 下存在多个 .txt 文件，无法判定哪一份是格式要求。\n"
        "  请用 -r 指定其中一份，或改用 --preset zh-academic/en-nature。",
        "Several .txt files in {dir}; cannot tell which one is the requirements.\n"
        "  Pass -r to select one, or use --preset zh-academic/en-nature.",
    ),
    "pipeline.txt_auto": (
        "未指定格式要求，自动使用同目录唯一的 {path}（要换一份就加 -r）。",
        "No requirements given; using the only .txt beside the manuscript: {path} (pass -r to choose another).",
    ),
    "pipeline.template_missing": ("指定的模板文件不存在: {path}", "Template file not found: {path}"),
    "pipeline.no_spec": ("未提供格式要求或模板，无法生成样式文档。", "No requirements or template: cannot build the style template."),
    "pipeline.csl_error": ("文献库或 CSL 样式无法使用：{reason}", "Bibliography or CSL style unusable: {reason}"),
    "pipeline.csl_normalized": (
        "引文样式 {name} 里的 {attrs} 已忽略：段落格式（悬挂缩进、行距）由要求文件的「参考文献」样式决定，"
        "否则同一份要求换个 CSL，排版就会变。",
        "Ignored {attrs} in citation style {name}: paragraph formatting (hanging indent, line spacing) "
        "comes from the Bibliography style in the requirements file, otherwise the same requirements "
        "would lay out differently under a different CSL.",
    ),
    # ── 流水线：进度与结论 ──────────────────────────────────────────
    "pipeline.precheck": ("执行导出前语法与排版契约预检…", "Running the pre-flight check…"),
    "pipeline.rejected": (
        "稿件共有 {count} 处不符合契约，导出已中止。请按下列行号修改后重新导出。",
        "The manuscript violates the contract in {count} place(s); export stopped. "
        "Amend the lines below and export again.",
    ),
    "pipeline.success": ("Word 文档导出成功: {path}", "Word document written: {path}"),
    "pipeline.numeric_ok": ("产物数值完整性检查通过。", "Numeric integrity check passed."),
    "pipeline.numeric_failed": (
        "产物完整性检查未通过：原稿中 {count} 处数值未在产物中找到（{sample}）。",
        "Numeric integrity check failed: {count} value(s) from the manuscript are missing ({sample}).",
    ),
    "pipeline.audit_ok": ("产物与格式要求逐条对账通过。", "Post-export audit against requirements passed."),
    "pipeline.audit_failed": (
        "导出后抽查未通过：产物与格式要求存在 {count} 处不符。",
        "Post-export audit failed: {count} mismatch(es) against the requirements.",
    ),
    "pipeline.unsupported": ("稿件包含当前无法写出的结构：{reason}", "A structure could not be written: {reason}"),
    "pipeline.pdf_ok": ("PDF 核对版已生成: {path}", "Review PDF written: {path}"),
    "pipeline.pdf_skipped": ("docx 已正常生成；PDF 渲染未执行或未完成。", "docx written; the PDF step was skipped or did not finish."),
    "pipeline.reminder": (
        "导出完成。请在 Word 中打开该文档并核对以下各项：表格的行高与列宽由内容自适应；"
        "公式、三线表、图片与题注的位置；页眉与页脚。以上各项均需在 Word 中目视确认。",
        "Export complete. Open the document in Word and verify the following: table row heights "
        "and column widths adapt to content; the placement of equations, three-line tables, "
        "figures and captions; and the headers and footers. Each of these can be confirmed "
        "visually only.",
    ),
    # ── 模板生成 ────────────────────────────────────────────────────
    "template.styles_only": (
        "该模板只提供样式（styles.xml）。导出命令：md-to-word 稿件.md -o 输出.docx",
        "This template carries styles only (styles.xml). Export with: md-to-word paper.md -o out.docx",
    ),
}


def resolve_lang(manuscript: str | None = None, override: str | None = None) -> str:
    """决定消息语言。`override` 是 `--lang` 的原值；`auto`/None 时按稿件语种。"""
    if override in SUPPORTED:
        return override
    return "zh" if looks_chinese(manuscript or "") else "en"


def t(key: str, lang: str, **kwargs) -> str:
    """取一条消息。缺 key 直接抛——静默回退到另一种语言更难查。"""
    zh, en = _MESSAGES[key]
    text = en if lang == "en" else zh
    return text.format(**kwargs) if kwargs else text
