"""md_to_word.i18n — 面向用户的全部消息双语，唯一真相源。

覆盖「人直接看到」的每一层：命令行帮助、流水线进度与结论、导出后的核对提醒，
以及**导前预检门禁**的逐条说明（`gate.*`）。门禁细节不只是转述给用户的旁注——
英文作者被拦下时读到的必须是英文，举的样式名也得是 `Abstract` 而不是「摘要」。

两条记账规则：

- `t(key, lang, **kw)` 只在给了 `kw` 时才 `.format()`。所以带占位符的消息里，
  字面量花括号要写成 `{{`/`}}`；不带占位符的消息按原样写（`{{< pagebreak >}}`
  这种语法字面量本来就双花括号）。
- 词表里不写中文提示语，只写「这条讲什么」的 key；写法一律 `t(key, lang, ...)`。

语种判定复用 `config.looks_chinese`：数正文汉字占比，跳过 `%%` 样式行。所以同一份
英文稿不会因为 `%% 表题` 这类词表写法被认成中文稿。
"""

from __future__ import annotations

from md_to_word.config import looks_chinese

SUPPORTED = ("zh", "en")

_MESSAGES: dict[str, tuple[str, str]] = {
    # ── 命令行 ──────────────────────────────────────────────────────
    "cli.description": (
        "把 Markdown 编译成符合声明格式的 Word（.docx）",
        "Compile Markdown into Word (.docx) that matches a declared format",
    ),
    "cli.epilog": (
        "退出码: 0=成功 / 1=稿件或门禁问题 / 2=参数用法错误 / 3=docx 已生成但 PDF 未渲染\n"
        "快速起步：`md-to-word init` 生成一份格式声明与样例稿件；\n"
        "第一次用先过一遍 `md-to-word --guide`（流程、门禁、边界）。",
        "Exit codes: 0=ok / 1=manuscript or gate failure / 2=usage error / 3=docx written, PDF skipped\n"
        "To start quickly: `md-to-word init` writes a format file and a sample manuscript;\n"
        "read `md-to-word --guide` once (workflow, gates, boundaries).",
    ),
    "cli.help": ("显示本帮助后退出", "show this help message and exit"),
    "cli.version": ("显示版本号后退出", "show program's version number and exit"),
    "cli.input": ("输入的 Markdown 稿件 (.md)", "Input Markdown manuscript (.md)"),
    "cli.output": ("输出的 Word 文档路径 (.docx)", "Output .docx path"),
    "cli.requirements": (
        "格式要求文件 (.txt)；未传时只认同目录的 format.txt，没有则用内置预设",
        "Format requirements (.txt); without it, only a format.txt beside the manuscript is used, else a preset",
    ),
    "cli.preset": (
        "内置格式预设：zh-academic（中文学术默认）或 en-nature（英文国际期刊）",
        "Built-in preset: zh-academic (Chinese thesis) or en-nature (international journal)",
    ),
    "cli.template": (
        "可选：指定现成 Word 样式模板 (.docx)，仅支持单节模板",
        "Optional: an existing .docx to take styles from (single section only)",
    ),
    "cli.lang": ("消息语言：auto=按稿件语种 / zh / en", "Message language: auto / zh / en"),
    "cli.no_check": ("跳过导前语法与排版契约预检（不推荐）", "Skip the pre-flight check (not recommended)"),
    "cli.no_postflight": ("跳过产物数值防丢检查（不推荐）", "Skip the numeric-integrity check (not recommended)"),
    "cli.no_audit": ("跳过产物与格式要求逐条对账抽查", "Skip the post-export audit against requirements"),
    "cli.pdf": ("导出后再渲染一份 PDF 供核对（macOS + 本机 Word）", "Also render a PDF for review (macOS + local Word)"),
    "cli.brief": (
        "md-to-word {version} — 把 Markdown 编译成符合声明格式的 Word（.docx）\n\n"
        "  md-to-word init                            生成一份格式声明与可直接导出的样例稿件\n"
        "  md-to-word 稿件.md -o 稿件.docx             按稿件语种选内置预设导出\n"
        "  md-to-word 稿件.md -o 稿件.docx --json      结果写成一行 JSON\n\n"
        "流程、门禁与全部写法：md-to-word --guide\n"
        "全部选项：md-to-word --help",
        "md-to-word {version} — compile Markdown into Word (.docx) that matches a declared format\n\n"
        "  md-to-word init                            write a format file and a sample manuscript\n"
        "  md-to-word paper.md -o paper.docx          export with the preset for the manuscript's language\n"
        "  md-to-word paper.md -o paper.docx --json   result as one JSON object\n\n"
        "Workflow, gates and full vocabulary: md-to-word --guide\n"
        "All options: md-to-word --help",
    ),
    "cli.verbose": (
        "输出逐样式明细（排查格式没生效时用）",
        "Log every style as it is applied (for diagnosing formats that did not take effect)",
    ),
    "cli.contract": (
        "打印稿件契约速查、手册与预设的路径后退出（--lang en 得英文版）",
        "Print the manuscript contract, manual and preset paths, then exit (--lang en for English)",
    ),
    "init.description": (
        "在当前目录生成一份格式声明与一份能直接导出的样例稿件",
        "Write a format file and a sample manuscript into a directory, ready to export",
    ),
    "init.directory": ("目标目录（默认当前目录）", "Target directory (default: current)"),
    "init.preset": ("用哪份内置预设（默认按语种：zh-academic / en-nature）", "Which built-in preset (default: by language)"),
    "init.force": ("覆盖已存在的同名文件", "Overwrite existing files"),
    "init.done": (
        "已生成：\n  {directory}/format.txt（{preset} 预设，整份都可以改）\n"
        "  {directory}/hello.md（能直接导出）\n\n下一步：{command}\n"
        "流程与全部写法：md-to-word --guide",
        "Created:\n  {directory}/format.txt (the {preset} preset — edit it in place)\n"
        "  {directory}/hello.md (exports as-is)\n\nNext: {command}\n"
        "Workflow and full vocabulary: md-to-word --guide",
    ),
    "init.preset_missing": (
        "未找到预设: {name}\n  内置预设是 zh-academic 与 en-nature；也可以直接给一份 --preset 之外的要求文件。",
        "Preset not found: {name}\n  The built-in presets are zh-academic and en-nature.",
    ),
    "init.exists": (
        "未覆盖已存在的文件：{paths}（要覆盖加 --force）",
        "Not overwriting existing files: {paths} (add --force to replace them)",
    ),
    "init.dir_failed": ("无法创建目录 {dir}：{err}", "Cannot create directory {dir}: {err}"),
    "cli.guide": (
        "打印入门文档后退出：按什么顺序做、门禁怎么读、边界在哪（第一次用先读它）",
        "Print the getting-started guide, then exit: order of work, how to read the gates, boundaries",
    ),
    "cli.json": (
        "把结果写成一行 JSON 到 stdout（给程序与 Agent 解析，键名不随版本变）",
        "Print the result as one JSON object on stdout (for programs and agents; keys are stable)",
    ),
    # ── 流水线：路径与配置 ──────────────────────────────────────────
    "pipeline.input_missing": ("输入稿件不存在: {path}", "Input manuscript not found: {path}"),
    "pipeline.write_failed": (
        "写出 {path} 失败：{err}\n  目录只读、磁盘已满、或文件正被 Word 打开时都会这样。",
        "Could not write {path}: {err}\n  This happens when the directory is read-only, the disk is full, or Word has the file open.",
    ),
    "pipeline.output_is_dir": (
        "输出路径是一个目录: {path}\n  用 -o 指到一个文件名，例如 -o 稿件.docx。",
        "The output path is a directory: {path}\n  Point -o at a file name, e.g. -o paper.docx.",
    ),
    "pipeline.output_dir_missing": (
        "输出目录不存在: {dir}\n  先建目录，或用 -o 指到已存在的目录里。",
        "Output directory does not exist: {dir}\n  Create it first, or point -o at an existing directory.",
    ),
    "pipeline.requirements_missing": ("指定的格式要求文件不存在: {path}", "Requirements file not found: {path}"),
    "pipeline.preset_missing": ("未找到预设: {name}", "Preset not found: {name}"),
    "pipeline.preset_auto": (
        "未指定格式要求，按稿件语种使用内置预设 {name}（要换就用 -r 或 --preset）。",
        "No requirements given; using the {name} preset for this manuscript's language (pass -r or --preset to override).",
    ),
    "pipeline.txt_named": (
        "未指定格式要求，取同目录的 format.txt（要换一份就加 -r）。",
        "No format file given; using the format.txt beside the manuscript (pass -r to use another).",
    ),
    "pipeline.txt_ignored": (
        "同目录有 {names}，但本工具只认 format.txt，未采用（要用其中一份请加 -r）。",
        "The manuscript's directory has {names}, but only a file named format.txt is picked up; "
        "pass -r to use one of them.",
    ),
    "pipeline.template_missing": ("指定的模板文件不存在: {path}", "Template file not found: {path}"),
    "pipeline.template_unreadable": (
        "底模读取失败（{path}）：{err}\n  底模必须是能正常打开的 .docx。",
        "Could not read the template ({path}): {err}\n  The base template must be a .docx that opens normally.",
    ),
    "pipeline.no_spec": ("未提供格式要求或模板，无法生成样式文档。", "No requirements or template: cannot build the style template."),
    "pipeline.csl_error": ("文献库或 CSL 样式无法使用：{reason}", "Bibliography or CSL style unusable: {reason}"),
    "pipeline.requirements_template_failed": (
        "格式要求无法生成样式模板：{reason}",
        "Could not build a style template from the requirements: {reason}",
    ),
    "pipeline.template_multiple_sections": (
        "模板必须是单节（当前 {count} 节）。多节模板的页面几何与页眉页脚无法逐节沿用，"
        "导出后会错位。请在 Word 里把模板合并成一节，或改用生成的模板（不传 -t）。",
        "The template must have a single section (this one has {count}). Page geometry and "
        "headers/footers cannot be carried over section by section, so the export would be "
        "misaligned. Merge the template into one section in Word, or drop -t and let the tool "
        "generate one.",
    ),
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
    # ── 写出器 / 公式 / 文献渲染：异常原文会经 `pipeline.unsupported` 漏给用户 ──
    "writer.unsupported_block": ("未支持的块类型：{type}", "unsupported block type: {type}"),
    "writer.equation_failed": (
        "独立公式「{snippet}」解析失败：{err}",
        "the display equation `{snippet}` could not be parsed: {err}",
    ),
    "writer.figure_pdf_failed": (
        "PDF 图「{path}」渲染成位图失败：{err}",
        "the PDF figure {path} could not be rasterised: {err}",
    ),
    "writer.quote_children": (
        "引用块里目前只支持段落、列表与代码块",
        "a blockquote currently supports only paragraphs, lists and code blocks",
    ),
    "writer.list_item_children": ("列表项里目前只支持段落", "a list item currently supports only paragraphs"),
    "writer.footnote_paragraph_only": (
        "脚注内容目前只支持段落",
        "footnote content currently supports only paragraphs",
    ),
    "writer.footnote_node": ("脚注里的 {type} 尚未支持", "{type} inside a footnote is not supported yet"),
    # 这条不带占位符，`{c}` 是公式编号格式里的语法字面量
    "writer.equation_chapter_without_yaml": (
        "要求文件的「公式编号格式」用了 {c}（章号），但稿件 YAML 的 crossref 下没有 chapters: true",
        "the equation number format uses {c} (chapter number), but the manuscript YAML has no "
        "chapters: true under crossref",
    ),
    "writer.crossref_type": (
        "交叉引用 {target} 的类型尚未支持",
        "cross-references to {target} are not supported yet",
    ),
    "writer.crossref_missing": ("交叉引用 {target} 指向的标签不存在", "the label {target} does not exist"),
    "writer.inline_equation_failed": (
        "行内公式「${snippet}$」解析失败：{err}",
        "the inline math `${snippet}$` could not be parsed: {err}",
    ),
    "writer.citation_without_bibliography": (
        "稿件声明了 citation，但未提供文献库或 CSL 样式；请检查 YAML 的 bibliography/csl",
        "the manuscript cites sources but no bibliography or CSL style was provided; "
        "check bibliography/csl in the YAML",
    ),
    "writer.link_child": ("超链接里放不下 {type}", "{type} cannot be placed inside a hyperlink"),
    "writer.inline_format_child": (
        "「{type}」还不能写在行内格式里",
        "{type} cannot be written inside inline formatting yet",
    ),
    "writer.inline_node": ("未支持的行内节点：{type}", "unsupported inline node: {type}"),
    "writer.toc_failed": ("目录域生成失败：{err}", "the table of contents could not be generated: {err}"),
    "markers.toc_depth": (
        "目录收录级数要在 1–{max} 之间，收到 {depth}",
        "the TOC depth must be between 1 and {max}; got {depth}",
    ),
    "mathml.unknown_element": (
        "尚未支持的 MathML 元素：{name}",
        "unsupported MathML element: {name}",
    ),
    "mathml.mtable_child": ("mtable 里出现了 {name}", "unexpected {name} inside mtable"),
    "mathml.latex_failed": ("LaTeX 语法解析失败（{err}）", "LaTeX could not be parsed ({err})"),
    "mathml.structure_invalid": (
        "公式结构不完整（{name}）：{err}",
        "the equation structure is incomplete ({name}): {err}",
    ),
    "mathml.malformed": (
        "公式转换失败（{err}）。多行公式请用 `cases`、`matrix` 或 `split` 环境，"
        "也可以拆成多条公式分别编号。",
        "equation conversion failed ({err}). For multi-line equations use the `cases`, `matrix` or "
        "`split` environment, or split it into separate numbered equations.",
    ),
    "citations.empty_library": ("文献库里没有可用条目", "the bibliography has no usable entries"),
    "citations.style_unparsable": (
        "CSL 样式无法解析：{path}（{err}）",
        "the CSL style could not be parsed: {path} ({err})",
    ),
    "citations.key_missing": ("文献库里没有条目：{key}", "the bibliography has no entry for {key}"),
    "pipeline.pdf_ok": ("PDF 核对版已生成: {path}", "Review PDF written: {path}"),
    "pipeline.pdf_skipped": ("docx 已正常生成；PDF 渲染未执行或未完成。", "docx written; the PDF step was skipped or did not finish."),
    "pipeline.reminder": (
        "导出完成。版面效果仍须在 Word 中人工核验。",
        "Export complete. The layout still requires a manual check in Word.",
    ),
    # ── 模板生成 ────────────────────────────────────────────────────
    "template.built": (
        "✓ 样式模板已生成：{count} 个样式",
        "Style template built: {count} styles",
    ),
    "template.styles_only": (
        "该模板只提供样式（styles.xml）。导出命令：md-to-word 稿件.md -o 输出.docx",
        "This template carries styles only (styles.xml). Export with: md-to-word paper.md -o out.docx",
    ),
    # 必填项诊断（`_check_required_fields`）
    "template.missing_styles_header": (
        "⚠️ 必填样式缺失（将沿用 Word 默认值，可能不符合期刊要求）:",
        "⚠️ Missing required styles (Word defaults are used, which may not meet the journal requirements):",
    ),
    "template.style_item": (" - {alias}（{style}）", " - {style}"),
    "template.missing_styles_hint": (
        " 建议在 format.txt 中补充这些样式的定义",
        " Add these style definitions to format.txt",
    ),
    "template.missing_rows_header": (
        "⚠️ 必填行缺失（不写就会套用默认样式）:",
        "⚠️ Missing required rows (the default style applies without them):",
    ),
    "template.row_item": (" - {name}: 应写「{example}」", " - {name}: write `{example}`"),
    "template.missing_fields_header": (
        "⚠️ 必填字段缺失（缺失会沿用 Word 默认值，可能导致格式不合规）:",
        "⚠️ Missing required fields (Word defaults are used, so the format may not comply):",
    ),
    "template.field_item": (" - {alias}: 缺少{field}", " - {alias}: missing {field}"),
    "template.field_fix": (" 应写: {hint}", " should be: {hint}"),
    "template.abort": (
        "❌ 必填项或必填字段缺失，终止生成。",
        "❌ Required styles or fields are missing; generation stopped.",
    ),
    "template.abort_hint": (
        " 请按上方提示补齐缺失项（不需要间距或缩进时，也须显式填 0，如「段前0磅」「首行缩进0字符」）。",
        " Fill in the items listed above (spacing and indent must be stated explicitly as 0 even when "
        "none is wanted, e.g. `space-before 0pt`, `indent 0`).",
    ),
    "template.check_ok": ("必填字段校验通过", "required-field check passed"),
    # 条件成套必填里「为什么也要它」的那半句
    "template.style.toc_group": (
        "{name}（已声明目录样式，须成套配齐）",
        "{name} (a TOC style is declared, so the whole TOC group must be declared)",
    ),
    "template.style.toc_prev_level": (
        "{name}（已声明{this}，须先有上一级）",
        "{name} (declared together with {this}, so the level above must come first)",
    ),
    "template.style.compact_group": (
        "{name}（已声明表格样式，须同时声明表内单元格文字样式）",
        "{name} (a table style is declared, so the cell-text style must be declared too)",
    ),
    "template.style.figure_group": (
        "{name}（已声明图片题注，须同时声明图片段落样式）",
        "{name} (an image-caption style is declared, so the figure paragraph style must be declared too)",
    ),
    "template.style.image_caption_group": (
        "{name}（已声明图样式，须同时声明图片题注样式）",
        "{name} (a figure style is declared, so the image caption style must be declared too)",
    ),
    "template.style.abstract_group": (
        "{name}（已声明摘要标题，须同时声明摘要正文样式）",
        "{name} (an abstract-title style is declared, so the abstract body style must be declared too)",
    ),
    "template.style.bibliography_group": (
        "{name}（已声明参考文献标题，须同时声明参考文献条目样式）",
        "{name} (a references-title style is declared, so the bibliography style must be declared too)",
    ),
    # 要求文件里「该写的那一行」的示例。英文一律用 parser 认得的英文词法，
    # 测试里真的过一遍 `parse_requirements`——教人写出解析不了的行比中文更糟。
    "template.example.table": (
        "表格：居中 三线表 线宽上1磅 线宽底1磅 线宽表头下0.25磅 单元格垂直居中",
        "Table: center three-line border-top 1pt border-bottom 1pt border-header 0.25pt valign-center",
    ),
    "template.example.table_header": (
        "表头：宋体/Times New Roman 五号 加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符",
        "Table Header: Times New Roman 10.5pt bold not-italic center line-spacing 1.0 "
        "space-before 0pt space-after 0pt indent 0",
    ),
    "template.example.header": (
        "页眉：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符",
        "Header: Times New Roman 9pt not-bold not-italic center line-spacing 1.0 "
        "space-before 0pt space-after 0pt indent 0",
    ),
    "template.example.footer": (
        "页脚：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符",
        "Footer: Times New Roman 9pt not-bold not-italic center line-spacing 1.0 "
        "space-before 0pt space-after 0pt indent 0",
    ),
    # 字段名
    "template.field.font_name": ("字体", "font"),
    "template.field.font_size": ("字号", "font size"),
    "template.field.alignment": ("对齐方式", "alignment"),
    "template.field.line_spacing": ("行距", "line spacing"),
    "template.field.space_before": ("段前", "space before"),
    "template.field.space_after": ("段后", "space after"),
    "template.field.indent": (
        "缩进（首行缩进/悬挂缩进，不需则填0）",
        "indent (first-line or hanging; write 0 if none)",
    ),
    "template.field.bold": ("加粗状态", "bold setting"),
    "template.field.italic": ("倾斜状态", "italic setting"),
    # 字段该怎么写。英文那栏是**能直接放进样式行**的片段，测试里逐个过 parse_requirements。
    "template.hint.font_name": (
        '字体（如"宋体"或"Times New Roman"或"宋体/Times New Roman"）',
        "Times New Roman",
    ),
    "template.hint.font_size": ('字号（如"12pt"或"小四"）', "12pt"),
    "template.hint.alignment": (
        '对齐方式（如"居中"/"左对齐"/"右对齐"/"两端对齐"）',
        "center",
    ),
    "template.hint.line_spacing": (
        '行距（"行距2倍" / "行距20磅" / "行距最小值25磅"，不能用0）',
        "line-spacing 1.5",
    ),
    "template.hint.space_before": ('段前（如"段前0磅"，不需段间距填0）', "space-before 0pt"),
    "template.hint.space_after": ('段后（如"段后6磅"，不需段间距填0）', "space-after 6pt"),
    "template.hint.indent": (
        '缩进（正文写"首行缩进2字符"，参考文献写"悬挂缩进0.5英寸"，表格写"首行缩进0字符"）',
        "indent 0",
    ),
    "template.hint.bold": ('加粗状态（如"加粗"或"不加粗"，标题类样式必须显式指定）', "bold"),
    "template.hint.italic": ('倾斜状态（如"倾斜"或"不倾斜"，标题类样式必须显式指定）', "not-italic"),
    # 模板生成过程中的报错
    "template.no_styles_parsed": (
        "未解析到任何样式要求；格式应为「样式名：属性」，"
        "如「一级标题：黑体 三号 加粗 不倾斜 左对齐 行距1.5倍 段前12磅 段后6磅 首行缩进0字符」。",
        "No style requirements were parsed; each line should read `Style: properties`, e.g. "
        "`Heading 1: SimHei 16pt bold not-italic left line-spacing 1.5 space-before 12pt "
        "space-after 6pt indent 0`.",
    ),
    "template.required_missing": (
        "必填样式或必填字段缺失，详见上方逐条提示。",
        "Required styles or fields are missing; see the items listed above.",
    ),
    "template.base_template_missing": (
        "未找到基础模板 {path}；请运行 scripts/create_pure_modern_base.py 重新生成。",
        "Base template not found: {path}; regenerate it with scripts/create_pure_modern_base.py.",
    ),
    "template.multiple_sections": (
        "模板必须是单节（当前 {count} 节），多节模板的页眉页脚会错位。",
        "The template must have a single section (this one has {count}); "
        "headers and footers would be misaligned.",
    ),
    "template.styleref_unknown": (
        "页眉/页脚域 {{样式标题:{name}}} 指向的样式在模板里不存在。"
        "STYLEREF 只认 Word 样式名（如 Heading 1）。{hint}",
        "The header/footer field {{styleref:{name}}} points to a style that is not in the template. "
        "STYLEREF only accepts Word style names (e.g. Heading 1).{hint}",
    ),
    "template.styleref_alias_hint": (
        "\n  「{name}」是本工具的中文写法，对应 Word 样式名「{cn}」——域里要写后者：{{样式标题:{cn}}}",
        "\n  `{name}` is this tool's Chinese spelling; the Word style name is `{cn}` — "
        "the field must use the latter: {{styleref:{cn}}}",
    ),
    # 这条不带占位符，`{页码}` / `{page}` 都是语法字面量，按原样写
    "template.page_number_without_field": (
        "写了「页码：」，但没有任何页眉/页脚内容带 {页码} 域。"
        "「页码：」只定格式与起始值，把页码画到纸上的是 {页码} 域；"
        "补一行「页脚内容：{页码}」，或删掉「页码：」这一行。",
        "A `Page Number:` row is declared, but no header/footer content carries the {page} field. "
        "`Page Number:` only sets the format and the starting value; what puts the number on paper is "
        "the {page} field. Add a `Footer Content: {page}` row, or drop the `Page Number:` row.",
    ),
    "template.table_style_unsupported": (
        '不支持的表格样式 "{style}"；可用：三线表 / 全网格线 / 顶底线 / 无边框。',
        'Unsupported table style "{style}"; use one of three-line / grid / top-bottom / none.',
    ),
    "template.table_widths_without_lines": (
        "表格样式为「无边框」，不画任何线，不能写线宽（收到 {widths}）；"
        "要保留某条线请改用「三线表」或「顶底线」。",
        'The table style is "none", which draws no lines at all, so widths cannot be set '
        '(got {widths}); to keep a line use "three-line" or "top-bottom".',
    ),
    "template.table_no_inside_line": (
        "表格样式为「{style}」，没有内部横线，不能写「线宽内」；三线表的表头下线请用「线宽表头下」。",
        'The table style is "{style}", which has no inside horizontal lines, so an inside width '
        "cannot be set; for a three-line table use the header-bottom width (`border-header`).",
    ),
    "template.theme_cleanup_failed": (
        "模板已写出，但「styles.xml 主题属性清理」失败，产物不合格：{err}",
        "the template was written, but cleaning the theme attributes in styles.xml failed, "
        "so the result is unusable: {err}",
    ),
    "template.table_style_missing": (
        '表格样式 "Table" 不存在（跳过表格边框和对齐设置）',
        'The "Table" style does not exist (skipping table borders and alignment)',
    ),
    # ── 反推参考 docx（template/extractor.py，控制台入口 md-to-word-template） ──
    # 只翻**给人看的消息**与「需人工确认」清单；草稿正文仍用本工具的（中文）词表写法，
    # 那是 format.txt 的合法语法，不随消息语言变。
    "extractor.not_docx": (
        "{path} 不是 Word 文档（.docx 是 zip 包）。请传一份 .docx 模板。",
        "{path} is not a Word document (.docx is a zip archive). Pass a .docx template.",
    ),
    "extractor.no_styles": (
        "{path} 里没有 word/styles.xml，读不出样式表。请换一份完整的 .docx。",
        "{path} has no word/styles.xml, so there is no style table to read. Use a complete .docx.",
    ),
    "extractor.cli.description": (
        "从参考 .docx 反推 format.txt 草稿（读不出的项单独列出，不猜值）",
        "Draft a format.txt from a reference .docx (unreadable items are listed, never guessed)",
    ),
    "extractor.cli.docx": ("参考 .docx 路径", "path to the reference .docx"),
    "extractor.cli.output": ("输出路径（默认打印到 stdout）", "output path (prints to stdout by default)"),
    "extractor.cli.lang": (
        "消息语言：auto=按参考文件语种 / zh / en",
        "Message language: auto (follows the reference file) / zh / en",
    ),
    "extractor.draft_written": (
        "已写出草稿: {path}（样式 {styled} 条，需确认 {notes} 项）",
        "draft written: {path} ({styled} style(s), {notes} item(s) to confirm)",
    ),
    "extractor.notes_header": ("需人工确认", "needs a human check"),
    "extractor.note.font_undefined": (
        "字体未定义（参考文件里这条样式没有设字体，生效值取决于打开它的软件）",
        "font undefined (this style sets none in the reference file; the effective font depends on "
        "the app that opens it)",
    ),
    "extractor.note.size_undefined": (
        "字号未定义（参考文件里这条样式没有设字号）",
        "font size undefined (this style sets none in the reference file)",
    ),
    "extractor.note.alignment_unsupported": (
        "对齐方式「{value}」本工具不支持（如分散对齐），已按左对齐处理",
        'alignment "{value}" is not supported by this tool (distributed, for example); '
        "left-aligned was assumed",
    ),
    "extractor.note.line_spacing_default": (
        "行距未显式设置，按单倍（未写 spacing 时的默认，内容更高也不会被裁）",
        "line spacing is not set explicitly, so single is assumed (the default when no spacing is "
        "written; taller content will not be clipped)",
    ),
    "extractor.note.line_unit_converted": (
        "{label}原文件用「行」为单位（{lines:g} 行），已折算为磅，请核对",
        "{label} the reference uses lines ({lines:g}), which was converted to points — please check",
    ),
    "extractor.note.hanging_chars_converted": (
        "悬挂缩进原文件用「字符」为单位，本工具只支持英寸，已换算",
        "the reference gives the hanging indent in characters; this tool only supports inches, "
        "so it was converted",
    ),
    "extractor.note.left_indent_converted": (
        "左缩进原文件用绝对值（磅）而非「字符」，本工具只支持字符，已按字号折算",
        "the reference gives the left indent as an absolute value (points) instead of characters; "
        "this tool only supports characters, so it was derived from the font size",
    ),
    "extractor.note.border_kind_unknown": (
        "下边框样式「{value}」不认识，已按单线处理",
        'bottom border style "{value}" is not recognised; a single line was assumed',
    ),
    "extractor.note.tabs_limited": (
        "用了 {count} 个制表位（{where}）——本工具的 `点线制表位` 只能表达"
        "「右对齐 + 点线 + 落在版心右边界」那一种，其余的草稿里没法表达，"
        "需要在 Word 里手工设（任意制表位见 manual.md §6）",
        "{count} tab stop(s) found ({where}) — this tool's `dot-leader-tab` can only express "
        "right-aligned + dot leader + at the right edge of the text block; the rest cannot be "
        "expressed in the draft and must be set by hand in Word (see manual.md §6)",
    ),
    "extractor.note.table_border_default": (
        "表格边框不是四种标准样式之一，已按三线表处理",
        "the table borders are not one of the four standard styles; a three-line table was assumed",
    ),
    "extractor.note.table_border_undefined": (
        "参考文件的 Table 样式没有边框定义（表格样式可能靠直接格式做的）",
        "the Table style in the reference file defines no borders (the table may be styled with "
        "direct formatting)",
    ),
    "extractor.note.multi_section": (
        "参考文件是 {count} 节的，页面设置只读了**正文节**那一份"
        "（与导出侧同一口径）；前置节（目录/摘要）的页码、页边距没读，需要的话自己补",
        "the reference file has {count} sections; page setup was read from the body section only "
        "(same convention as the export side). Page numbers and margins of the front sections "
        "(TOC/abstract) were not read — add them yourself if needed",
    ),
    "extractor.note.paper_unsupported": (
        "纸张尺寸 {width}×{height}cm 不在本工具的 A4/Letter 之内",
        "paper size {width}×{height}cm is not one of this tool's A4/Letter sizes",
    ),
    "extractor.note.page_number_format_unknown": (
        "页码格式「{value}」不在本工具词表里",
        'page number format "{value}" is not in this tool\'s vocabulary',
    ),
    "extractor.note.doc_grid_skipped": (
        "读到了文档网格（linePitch），但纸张不是 A4/Letter 或缺页边距，"
        "算不出「每页几行」，草稿已跳过这一行",
        "a document grid (linePitch) was found, but the paper is not A4/Letter or margins are "
        "missing, so lines-per-page cannot be computed; the draft skipped this row",
    ),
    "extractor.note.styles_skipped": (
        "参考文件里这些样式**没有定义属性**（字体/字号都没有），草稿已跳过：{names}",
        "these styles define no properties (no font, no size) in the reference file and were "
        "skipped in the draft: {names}",
    ),
    "extractor.note.styles_unmapped": (
        "参考文件里这些样式没映射到本工具词汇（要不要用请自行判断）：{names}",
        "these styles do not map to this tool's vocabulary (decide yourself whether you need "
        "them): {names}",
    ),
    # ── 导出后对账（audit/inspector.py） ───────────────────────────
    # 类别标签与逐条明细分成两类：pipeline 把明细拼成 `  [类别] 说明`，
    # 两栏都得跟语言走，否则英文稿会看到英文标题下跟着中文行。
    "audit.cat.style": ("样式", "style"),
    "audit.cat.font": ("字体", "font"),
    "audit.cat.font_size": ("字号", "font size"),
    "audit.cat.bold": ("加粗", "bold"),
    "audit.cat.italic": ("倾斜", "italic"),
    "audit.cat.alignment": ("对齐", "alignment"),
    "audit.cat.line_spacing": ("行距", "line spacing"),
    "audit.cat.space_before": ("段前", "space before"),
    "audit.cat.space_after": ("段后", "space after"),
    "audit.cat.indent": ("缩进", "indent"),
    "audit.cat.tabs": ("制表位", "tab stop"),
    "audit.cat.toc": ("目录", "TOC"),
    "audit.cat.keep_next": ("同页", "keep with next"),
    "audit.cat.border": ("边框", "border"),
    "audit.cat.latin_font": ("西文字体", "Latin font"),
    "audit.cat.char_spacing": ("字距", "letter spacing"),
    "audit.cat.keep_lines": ("段中不分页", "keep lines together"),
    "audit.cat.page_break_before": ("段前分页", "page break before"),
    "audit.cat.widow_control": ("孤行控制", "widow control"),
    "audit.cat.proofing_lang": ("校对语言", "proofing language"),
    "audit.cat.page_size": ("纸张", "paper size"),
    "audit.cat.page_margin": ("页边距", "page margin"),
    "audit.cat.doc_grid": ("文档网格", "document grid"),
    "audit.cat.header_distance": ("页眉距边界", "header distance"),
    "audit.cat.footer_distance": ("页脚距边界", "footer distance"),
    "audit.cat.page_number": ("页码", "page number"),
    "audit.cat.title_page": ("首页", "title page"),
    "audit.cat.table": ("表格", "table"),
    "audit.cat.even_odd": ("奇偶页", "odd/even pages"),
    # 页边距的四边（中文说「上边」）
    "audit.side.top": ("上", "top"),
    "audit.side.bottom": ("下", "bottom"),
    "audit.side.left": ("左", "left"),
    "audit.side.right": ("右", "right"),
    # 开关与缺省值
    "audit.flag.on": ("开", "on"),
    "audit.flag.off": ("关", "off"),
    "audit.flag.default_on": ("缺省(开)", "default (on)"),
    # 表格样式名
    "audit.table_style.three-line": ("三线表", "three-line table"),
    "audit.table_style.top-bottom": ("顶底线", "top-and-bottom rules"),
    "audit.table_style.grid": ("全网格线", "full grid"),
    # ── 逐条明细 ──
    "audit.msg.style_missing": (
        "{name}：产物里没有这个样式（要求文件写了，导出后不存在）",
        "{name}: the output has no such style (the requirements file declares it, but it does "
        "not exist after export)",
    ),
    "audit.msg.font": (
        "{name}：要求 {want}，产物 rFonts={got}",
        "{name}: expected {want}, but the output has rFonts={got}",
    ),
    "audit.msg.font_size": (
        "{name}：要求 {want}(半磅)，产物 {got}",
        "{name}: expected {want} (half-points), but the output is {got}",
    ),
    "audit.msg.bold_missing": (
        "{name}：要求加粗，产物没加粗（链上 b={src}）",
        "{name}: bold was required, but the output is not bold (chain b={src})",
    ),
    "audit.msg.bold_extra": (
        "{name}：要求不加粗，产物是加粗（b={src}——来自底模或继承，没被显式关闭）",
        "{name}: not-bold was required, but the output is bold (b={src} — inherited from the base "
        "template and never explicitly turned off)",
    ),
    "audit.msg.italic_missing": (
        "{name}：要求斜体，产物没斜体（链上 i={src}）",
        "{name}: italic was required, but the output is not italic (chain i={src})",
    ),
    "audit.msg.italic_extra": (
        "{name}：要求不倾斜，产物是斜体（i={src}）",
        "{name}: not-italic was required, but the output is italic (i={src})",
    ),
    "audit.msg.alignment": (
        "{name}：要求 {want}，产物 {got}",
        "{name}: expected {want}, but the output is {got}",
    ),
    "audit.msg.line_spacing": (
        "{name}：要求 line={want_line}/{want_rule}，产物 line={got_line}/{got_rule}",
        "{name}: expected line={want_line}/{want_rule}, but the output is "
        "line={got_line}/{got_rule}",
    ),
    "audit.msg.twips": (
        "{name}：要求 {want}(twips)，产物 {got}",
        "{name}: expected {want} (twips), but the output is {got}",
    ),
    "audit.msg.first_line_chars": (
        "{name}：要求首行缩进 {indent} 字符，产物 firstLineChars={got}",
        "{name}: expected a first-line indent of {indent} characters, but the output is "
        "firstLineChars={got}",
    ),
    "audit.msg.hanging_chars": (
        "{name}：要求悬挂缩进 {indent} 字符，产物 hangingChars={got}",
        "{name}: expected a hanging indent of {indent} characters, but the output is "
        "hangingChars={got}",
    ),
    "audit.msg.first_line_pt": (
        "{name}：要求首行缩进 {indent} pt(twips={want})，产物 firstLine={got}",
        "{name}: expected a first-line indent of {indent} pt (twips={want}), but the output is "
        "firstLine={got}",
    ),
    "audit.msg.hanging_pt": (
        "{name}：要求悬挂缩进 {indent} pt(twips={want})，产物 hanging={got}",
        "{name}: expected a hanging indent of {indent} pt (twips={want}), but the output is "
        "hanging={got}",
    ),
    "audit.msg.left_indent": (
        "{name}：要求左缩进 {indent} 字符，产物 leftChars={got}",
        "{name}: expected a left indent of {indent} characters, but the output is leftChars={got}",
    ),
    "audit.msg.dot_leader": (
        "{name}：要求点线制表位，产物缺少 right+dot 制表位",
        "{name}: a dot-leader tab stop was required, but the output has no right+dot tab",
    ),
    "audit.msg.join_toc": (
        "{name}：要求加入目录（outlineLvl），产物未设置大纲级别",
        "{name}: the style should join the TOC (outlineLvl), but the output sets no outline level",
    ),
    "audit.msg.keep_next": (
        "{name}：要求与下段同页（keepNext），产物未设置",
        "{name}: keep-with-next (keepNext) was required, but the output does not set it",
    ),
    "audit.msg.bottom_border": (
        "{name}：要求下边框 {want}，产物 {got}",
        "{name}: expected a {want} bottom border, but the output is {got}",
    ),
    "audit.msg.border_width": (
        "{name}：要求下边框粗 {pt}磅(sz={want})，产物 sz={got}",
        "{name}: expected a bottom border width of {pt}pt (sz={want}), but the output is sz={got}",
    ),
    "audit.msg.no_border_residue": (
        "{name}：要求无下边框，产物仍残留 bottom={got}",
        "{name}: no bottom border was required, but the output still has bottom={got}",
    ),
    "audit.msg.latin_font": (
        "{name}：要求全局西文字体 {want}，产物 ascii={got}",
        "{name}: expected the global Latin font {want}, but the output has ascii={got}",
    ),
    "audit.msg.char_spacing": (
        "{name}：要求 {pt}磅(val={want})，产物 {got}",
        "{name}: expected {pt}pt letter spacing (val={want}), but the output is {got}",
    ),
    "audit.msg.para_flag": (
        "{name}：要求{label}（{tag}），产物未设置",
        "{name}: {label} ({tag}) was required, but the output does not set it",
    ),
    "audit.msg.widow_control": (
        "{name}：要求 {flag}（val={val}），产物 {got}",
        "{name}: {flag} was required (val={val}), but the output is {got}",
    ),
    "audit.msg.proofing_lang": (
        "要求 eastAsia={want}，产物 {got}",
        "expected eastAsia={want}, but the output is {got}",
    ),
    "audit.msg.page_size": (
        "要求 {size}{want}，产物 {got}",
        "expected {size}{want}, but the output is {got}",
    ),
    "audit.msg.page_margin": (
        "{side}边：要求 {want}cm({twips})，产物 {got}",
        "{side} margin: expected {want}cm ({twips} twips), but the output is {got}",
    ),
    "audit.msg.doc_grid": (
        "要求每页 {lines} 行(linePitch={want})，产物 {got}",
        "expected {lines} lines per page (linePitch={want}), but the output is {got}",
    ),
    "audit.msg.distance": (
        "要求 {want}cm({twips})，产物 {got}",
        "expected {want}cm ({twips} twips), but the output is {got}",
    ),
    "audit.msg.page_number_format": (
        "格式：要求 {want}，产物 {got}",
        "format: expected {want}, but the output is {got}",
    ),
    "audit.msg.page_number_start": (
        "起始：要求 {want}，产物 {got}",
        "start: expected {want}, but the output is {got}",
    ),
    "audit.msg.title_pg_missing": (
        "产物没有 titlePg——「首页页眉/页脚内容」不会生效，首页会带出页眉页脚",
        "the output has no titlePg — the first-page header/footer content will not take effect, "
        "and the first page will carry the normal header/footer",
    ),
    "audit.msg.table_style_missing": (
        "产物里没有 Table 样式（表格边框与对齐无处落）",
        "the output has no Table style (table borders and alignment have nowhere to land)",
    ),
    "audit.msg.table_alignment": (
        "表格对齐：要求 {want}，产物 {got}",
        "table alignment: expected {want}, but the output is {got}",
    ),
    "audit.msg.table_border_side": (
        "{label} {side} 线：要求 sz={want}（{pt}磅），产物 sz={got}",
        "{label} {side} rule: expected sz={want} ({pt}pt), but the output is sz={got}",
    ),
    "audit.msg.table_header_border": (
        "{label}表头下线：要求 sz={want}（{pt}磅），产物 sz={got}",
        "{label} header bottom rule: expected sz={want} ({pt}pt), but the output is sz={got}",
    ),
    "audit.msg.table_border_residue": (
        "无边框表格残留 {side}={got}",
        "the borderless table still has {side}={got}",
    ),
    "audit.msg.table_valign": (
        "单元格垂直对齐：要求 {want}，产物 {got}",
        "cell vertical alignment: expected {want}, but the output is {got}",
    ),
    "audit.msg.table_cell_margin": (
        "单元格内边距{side}：要求 {want}(twips)，产物 {got}",
        "cell margin {side}: expected {want} (twips), but the output is {got}",
    ),
    "audit.msg.repeat_header": (
        "要求表头跨页重复（tblHeader），产物没有",
        "the header row should repeat across pages (tblHeader), but the output has none",
    ),
    "audit.msg.even_headers_missing": (
        "要求了偶数页页眉/页脚，但产物没开「奇偶页不同」",
        "even-page headers/footers are required, but the output does not enable "
        "different odd and even pages",
    ),
    # 对账脚本自己的命令行（`python -m md_to_word.audit.inspector`）
    "audit.cli.description": (
        "导出后抽查：产物 docx ↔ 格式要求文件",
        "Post-export audit: the output .docx vs. the requirements file",
    ),
    "audit.cli.docx": ("导出的产物 .docx", "the exported .docx"),
    "audit.cli.requirements": ("生成模板用的格式要求文件", "requirements file the template came from"),
    "audit.cli.quiet": ("只报结论，不逐条列", "report the verdict only, without the item list"),
    "audit.cli.lang": ("消息语言：auto=按要求文件语种 / zh / en", "Message language: auto / zh / en"),
    "audit.cli.file_missing": ("错误: 文件不存在 {path}", "error: file not found: {path}"),
    "audit.cli.not_a_docx": (
        "错误: 产物不是可解析的 docx（{err}）",
        "error: the output is not a readable .docx ({err})",
    ),
    "audit.cli.pass": (
        "✓ 导出后抽查通过：{docx} 与 {req} 逐条对上",
        "✓ Post-export audit passed: {docx} matches {req} item by item",
    ),
    "audit.cli.fail": (
        "⚠ 导出后抽查发现 {count} 处不符（{docx} ↔ {req}）：",
        "⚠ Post-export audit found {count} mismatch(es) ({docx} ↔ {req}):",
    ),
    "audit.msg.even_reference_missing": (
        "产物开了「奇偶页不同」但没有任何 even 页眉/页脚引用",
        "the output enables different odd and even pages but has no even header/footer reference",
    ),
    # ── 导前预检门禁 ────────────────────────────────────────────────
    # 行号前缀与方括号里的小标签各自成条：同一个「行 N [标签]: 说明」外壳被十几道门禁
    # 复用，标签也只翻一次，改口径时不会漏掉某一道。
    "gate.line": ("行 {line} [{tag}]: {why}", "Line {line} [{tag}]: {why}"),
    "gate.line_item": ("行 {line}", "line {line}"),
    "gate.line_grouped": (
        "「{tag}」{count} 处（行 {lines}）：{why}",
        "{count} × [{tag}] (lines {lines}): {why}",
    ),
    "gate.line_more": (" 等 {count} 处", " and {count} more"),
    "gate.list_sep": ("、", ", "),
    # 方括号里的标签
    "gate.tag.citation_key": ("引文 key 缺失", "citation key missing"),
    "gate.tag.unsupported_syntax": ("写法不支持", "unsupported syntax"),
    "gate.tag.block_marker": ("块级标记空行缺失", "blank line missing around a block marker"),
    "gate.tag.unknown_shortcode": ("未知短代码", "unknown shortcode"),
    "gate.tag.section_marker": ("分节标记", "section marker"),
    "gate.tag.heading": ("标题/分级", "heading level"),
    "gate.tag.crossref": ("交叉引用缺失目标", "cross-reference target missing"),
    "gate.tag.table": ("表格格式异常", "malformed table"),
    "gate.tag.caption_adjacency": ("图表题注邻近性", "caption adjacency"),
    "gate.tag.soft_wrap": ("折行段落", "wrapped paragraph"),
    "gate.tag.equation_brace": ("公式括号不配对", "unbalanced equation braces"),
    "gate.equation.brace": (
        "公式里的花括号不配对（「{snippet}」）：转换器不会报错，只会静默丢掉内容"
        "（如 `\\frac{{a}}{{b` 只剩 `ab`）。补上缺失的 `}}` 后重新导出。",
        "the braces in this equation do not pair up (\"{snippet}\"); the converter reports nothing "
        "and silently drops content (e.g. `\\frac{{a}}{{b` renders as `ab`). Add the missing `}}`.",
    ),
    "gate.tag.equation_number": ("公式编号", "equation number"),
    "gate.tag.image_width": ("图片宽度超过版心", "image wider than text block"),
    "gate.tag.style_missing": ("结构样式缺失", "missing structural style"),
    "gate.tag.style_line": ("段落样式", "paragraph style"),
    "gate.tag.caption_image": ("图片题注", "image caption"),
    # 短代码名（块级标记的提示里要点名是哪一个）
    "gate.marker.pagebreak": ("分页", "pagebreak"),
    "gate.marker.toc": ("目录", "toc"),
    "gate.marker.section": ("分节", "section"),
    # ── 稿件与要求文件本身 ──
    "gate.manuscript.missing": ("稿件文件不存在: {path}", "Manuscript file not found: {path}"),
    "gate.manuscript.unreadable": ("无法读取稿件 {path}: {err}", "Cannot read the manuscript {path}: {err}"),
    "gate.requirements.missing": ("格式要求文件不存在: {path}", "Requirements file not found: {path}"),
    "gate.requirements.parse_failed": (
        "格式要求文件解析失败（{path}）: {err}",
        "Could not parse the requirements file ({path}): {err}",
    ),
    "gate.yaml.parse_failed": ("YAML frontmatter 解析失败: {err}", "Could not parse the YAML frontmatter: {err}"),
    "gate.bib.missing": ("文献库不存在: {path}", "Bibliography file not found: {path}"),
    "gate.csl.missing": ("CSL 样式文件不存在: {path}", "CSL style file not found: {path}"),
    # YAML 里写了内容性字段：引擎只认正文的样式行，位置由作者定
    "gate.yaml.key_unused": (
        "YAML 的 `{key}` 不参与排版（YAML 管不住位置），正文要写成：{form}。"
        "请把内容移到正文，或删掉这个键。",
        "`{key}` in YAML is not typeset (YAML cannot carry position); write it in the body as: {form}. "
        "Move the content into the body, or drop the key.",
    ),
    "gate.yaml.form.title": ("`%% 文档标题 标题文字`", "`%% Title Your title`"),
    "gate.yaml.form.subtitle": ("`%% 副标题 副标题文字`", "`%% Subtitle Your subtitle`"),
    "gate.yaml.form.author": ("`%% 作者 姓名`（多位作者各写一行）", "`%% Author Name` (one line per author)"),
    "gate.yaml.form.date": ("`%% 日期 2026 年 1 月`", "`%% Date January 2026`"),
    "gate.yaml.form.abstract": (
        "`%% 摘要标题 摘要` + 每段一行 `%% 摘要 正文…`",
        "`%% Abstract Title Abstract` + one line per paragraph `%% Abstract Text...`",
    ),
    "gate.yaml.form.keywords": ("一行 `%% 关键词 词一；词二`", "one line `%% Keywords word one; word two`"),
    "gate.yaml.form.reference_section_title": (
        "一行 `%% 参考文献标题 参考文献`",
        "one line `%% References Title References`",
    ),
    # ── 文献与交叉引用 ──
    "gate.csl.default": (
        "未写 csl:，将按默认样式排版：{name}"
        "（中文稿 GB/T 7714 数字制，英文稿 APA）；如需其他样式请写 csl:。",
        "No csl: given; typesetting with the default style: {name} "
        "(GB/T 7714 numeric for Chinese manuscripts, APA for English). Write csl: to use another style.",
    ),
    "gate.bib.empty": (
        "文献库 {name} 里一条条目都没有，但正文有 {count} 处引用",
        "The bibliography file {name} has no entries, yet the body cites {count} place(s)",
    ),
    "gate.citation.unknown_key": (
        "引用了 {key}，但文献库里没有这个条目",
        "cited {key}, but the bibliography has no such entry",
    ),
    "gate.citation.no_bibliography": (
        "正文有 {count} 处 `[@key]` 引用语法，但稿件未声明 `bibliography:`（{shown}）；"
        "不处理会把这几个字符原样印进 docx。本工具只支持由 .bib 生成文献列表："
        "在 YAML 里加 `bibliography: refs.bib`（配合 `csl:` 选样式），"
        "若只是想展示语法字面量，用反引号包起来",
        "The body has {count} `[@key]` citation(s) but the manuscript declares no `bibliography:` ({shown}); "
        "left as is, those characters are printed into the docx verbatim. This tool builds reference lists "
        "from .bib only: add `bibliography: refs.bib` to the YAML (with `csl:` to pick a style); to show the "
        "syntax literally, wrap it in backticks",
    ),
    "gate.crossref.undefined": (
        "引用了 {key}，但稿子里没有 {{#{key}}} 这个标签定义",
        "referenced {key}, but the manuscript defines no {{#{key}}} label",
    ),
    "gate.bib.title_missing": (
        "有 bibliography 但正文没写文献区标题：在文末补一行 `%% 参考文献标题 参考文献`"
        "（或 `# 参考文献` 标题），否则生成的文献列表没有抬头",
        "bibliography is declared but the body has no reference-section title: add "
        "`%% References Title References` (or a `# References` heading) at the end, "
        "otherwise the generated list has no heading",
    ),
    # ── 公式编号 ──
    "gate.equation.chapters": (
        "要求文件的「公式编号格式」是 {fmt}，里面有 {{c}}（章号），"
        "但稿件 YAML 的 crossref 下没有 chapters: true。二选一："
        "在 `crossref:` 下加 `chapters: true`，或把格式改成不含 {{c}} 的写法（如 （{{n}}））",
        "The 「公式编号格式」/Equation Number Format in the requirements file is {fmt}, which contains "
        "{{c}} (chapter number), but the manuscript YAML has no chapters: true under crossref. Either add "
        "`chapters: true` under `crossref:`, or change the format to one without {{c}} (e.g. ({{n}}))",
    ),
    "gate.latex.tag": (
        "发现 `\\tag{{}}`，这不是本工具的编号写法，整条公式会退化成字面文本（{snippet}）；"
        "删掉 `\\tag{{X}}`，改写成 `$$…$$ {{#eq-标签}}`，编号由 crossref 生成",
        "found `\\tag{{}}`, which is not how this tool numbers equations: the whole equation degrades to "
        "literal text ({snippet}). Delete `\\tag{{X}}` and write `$$...$$ {{#eq-label}}` instead; the number "
        "is generated by crossref",
    ),
    # ── 图片与表格 ──
    "gate.image.path_space": (
        "行 {line}: 图片路径含未转义空格「{path}」",
        "Line {line}: image path contains an unescaped space: {path}",
    ),
    "gate.image.missing": (
        "行 {line}: 图片文件不存在「{path}」",
        "Line {line}: image file not found: {path}",
    ),
    "gate.citation.suppress_author": (
        "行 {line}: `[-@key]`（只出年份）引文引擎不实现，会渲染成完整引用；"
        "改写为 `@key` 叙述式，或把年份直接写进正文",
        "Line {line}: `[-@key]` (year only) is not implemented by the citation engine and would "
        "render as a full citation; write `@key` inline, or type the year into the sentence",
    ),
    "gate.image.unsupported": (
        "行 {line}: 图片是 {ext} 格式，Word 的内联图片只接受 PNG/JPEG/GIF/BMP/TIFF，"
        "导出会在这里中断。另存为 PNG 后再引用；PDF 也可以直接引用，导出时会按 300 dpi 转成位图",
        "Line {line}: the image is {ext}, and Word's inline pictures accept only PNG, JPEG, GIF, BMP "
        "or TIFF, so the export would stop here. Save it as PNG first, or reference a PDF directly "
        "(PDF figures are rasterised at 300 dpi during export)",
    ),
    "gate.table.row_unclosed": (
        "行 {line}: 表格行缺少行尾竖线——这一行会掉出表格变成正文，竖线原样印出来。补上结尾的 `|`",
        "Line {line}: the table row has no closing pipe — it falls out of the table and is printed as "
        "a body paragraph with the pipes showing. Add the trailing `|`",
    ),
    "gate.style_line.no_space": (
        "行 {line}: `%%` 后面少了空格，整行会原样印成正文。写成 `%% 样式名 内容`",
        "Line {line}: the `%%` style line has no space after the marker, so the whole line is printed "
        "as body text. Write `%% Style Name content`",
    ),
    "gate.yaml.unknown": (
        "YAML 里有认不出的键「{keys}」，会被忽略——它们不会让版面发生任何变化。"
        "只认 bibliography、csl、crossref、link-citations",
        "Unrecognised YAML keys ({keys}) are ignored and change nothing in the layout. Only "
        "bibliography, csl, crossref and link-citations are read",
    ),
    "gate.image.inline": (
        "行 {line}: 图片没有独立成行——行内图片不会落成图段，只会印出一个 `!`。"
        "把 `![](…)` 单独放一行，题注用 `%% 图片题注` 另起一段",
        "Line {line}: the image is not on its own line — an inline image does not become a figure "
        "paragraph, only a stray `!` is printed. Put `![](…)` on its own line and give the caption "
        "its own `%% Image Caption` paragraph",
    ),
    "gate.footnote.undefined": (
        "行 {line}: 脚注引用 `[^{label}]` 没有对应定义（`[^{label}]: …`），"
        "导出后是一个空号，整段注释文字会丢",
        "Line {line}: the footnote reference `[^{label}]` has no definition "
        "(`[^{label}]: …`); the export would print an empty mark and drop the note",
    ),
    "gate.equation.duplicate_label": (
        "公式标签 `{{#{label}}}` 重复：第 {first} 行已有同名标签，两条公式会抢同一个编号，"
        "引用只能指到其中一条",
        "Duplicate equation label `{{#{label}}}`: line {first} already defines it; the two equations "
        "compete for one number and a reference can only reach one of them",
    ),
    "gate.image.pdf_unreadable": (
        "行 {line}: 打不开 PDF「{path}」（{err}）——加密、损坏，或者根本不是 PDF",
        "Line {line}: cannot open the PDF at {path} ({err}) — encrypted, damaged, or not a PDF",
    ),
    "gate.image.pdf_multipage": (
        "行 {line}: PDF「{path}」有 {pages} 页，只取第 1 页；一页一图请拆成单页文件再引用",
        "Line {line}: the PDF at {path} has {pages} pages but only page 1 is used — split it into "
        "one figure per file",
    ),
    "gate.image_width.over": (
        "图片声明宽 {width:g}cm，超过版心 {content:.2f}cm——导出时会被**静默钳成版心宽**"
        "（不报错、也没有警告），实际拿到的不是 {width:g}cm。改成 {content:.2f}cm 以内，或调小页边距",
        "The image is declared {width:g}cm wide, beyond the {content:.2f}cm text block — it is **silently "
        "clamped to the text block width** (no error, no warning), so you do not get {width:g}cm. "
        "Use {content:.2f}cm or less, or narrow the page margins",
    ),
    "gate.image_width.no_margins": (
        "要求文件没写页边距，算不出版心，图片宽度未校验",
        "The requirements file declares no page margins, so the text block width is unknown "
        "and image widths were not checked",
    ),
    "gate.table.column_count": (
        "表格第 1 行有 {expect} 列，第 {line} 行是 {actual} 列——"
        "列数对不上时多出来的单元格会被静默丢掉（连字一起丢）",
        "Table row 1 has {expect} column(s) but line {line} has {actual} — when the column counts "
        "disagree, the extra cells are silently dropped (text and all)",
    ),
    # ── 标题层级 ──
    "gate.heading.first_level": (
        "首个章节标题是 {level} 级（`{hashes} {title}`），必须从 1 级（`#`）开始",
        "the first section heading is level {level} (`{hashes} {title}`); it must start at level 1 (`#`)",
    ),
    "gate.heading.level_jump": (
        "标题层级跳级：从 {prev} 级直接跳到 {level} 级（`{hashes} {title}`），应为 `{expected}`",
        "heading level jumps from {prev} straight to {level} (`{hashes} {title}`); it should be `{expected}`",
    ),
    "gate.heading.number_depth": (
        "章节编号深度与 `#` 数量不匹配：`{hashes} {title}` 有 {level} 个 `#`，"
        "但编号 `{number}` 深度为 {depth}（常见原因：把论文主标题写成了 `# 标题`，"
        "主标题应写在 YAML `title:` 中，正文一级章节用 `# 1. ...`）",
        "the section number depth does not match the number of `#`: `{hashes} {title}` has {level} `#`, "
        "but the number `{number}` is {depth} level(s) deep (common cause: the paper title was written as "
        "`# Title`; the title belongs in YAML `title:`, and top-level sections use `# 1. ...`)",
    ),
    # ── 块级标记与空行 ──
    "gate.block.math_close_no_blank": ("公式收尾行后无空行", "no blank line after the closing `$$`"),
    "gate.block.math_inline_with_text": (
        "公式与文字同行（未独立成行）",
        "a display equation shares its line with text (it must stand on its own line)",
    ),
    "gate.block.math_no_blank": ("公式后无空行", "no blank line after the equation"),
    "gate.block.marker_not_alone": (
        "{label}短代码未独占一行",
        "the {label} shortcode must be alone on its line",
    ),
    "gate.block.marker_no_blank": (
        "{label}短代码后无空行",
        "no blank line after the {label} shortcode",
    ),
    "gate.block.div_no_blank": ("围栏块首行前无空行", "no blank line before the first line of the fenced block"),
    "gate.block.image_no_blank_before": ("图片行前无空行", "no blank line before the image line"),
    "gate.block.image_no_blank_after": ("图片行后无空行", "no blank line after the image line"),
    "gate.block.table_no_blank": ("表格首行前无空行", "no blank line before the first table row"),
    "gate.section.extra_page": (
        "分节标记（行 {section}）之后紧跟分页短代码，会多顶出一页",
        "a pagebreak shortcode directly follows the section marker (line {section}); this adds an extra page",
    ),
    # ── 段落样式行 ──
    "gate.style.unknown_name": (
        "不认识样式名「{name}」；请写词表里的名字（如 {examples}）",
        "unknown style name \"{name}\"; use a name from the vocabulary (e.g. {examples})",
    ),
    "gate.style.heading_style": (
        "「{name}」是标题类样式，章节层级请用 Markdown 的 # 写法（## 为二级，依此类推）",
        "\"{name}\" is a heading style; encode section levels with Markdown # instead "
        "(## is level 2, and so on)",
    ),
    "gate.style.manual_bibliography": (
        "手写文献列表已不支持：在 YAML 里写 `bibliography: refs.bib` 与 `csl:`，"
        "文献列表由引擎生成（样式仍由要求文件的「参考文献」行控制）",
        "hand-written reference lists are no longer supported: put `bibliography: refs.bib` and `csl:` "
        "in the YAML and the engine generates the list (styling still comes from the `Bibliography` "
        "row of the requirements file)",
    ),
    "gate.style.empty_content": (
        "「{name}」后面没有正文；这一行要写成「%% {name} 内容」",
        "\"{name}\" has no body text; the line must read \"%% {name} content\"",
    ),
    "gate.style.continuation": (
        "「{name}」的下一行紧接正文，疑似软换行；本工具的段落样式以这一行为界，"
        "续行不会被并进来。请把整段合并到这一行",
        "the line right after \"{name}\" continues the prose, which looks like a soft wrap; a style line "
        "ends the paragraph here, so the next line is not merged in. Put the whole paragraph on this line",
    ),
    "gate.style.triple_colon": (
        "`:::` 不是本工具的写法。需要段落样式就写成一行 `%% 样式名 内容`；"
        "文献列表由引擎放在文末，不需要定位标记。",
        "`:::` is not part of this tool's syntax. For a paragraph style, write a single line "
        "`%% StyleName content`; the reference list is placed at the end by the engine and needs no anchor.",
    ),
    "gate.style.required_missing": (
        "用到了 {feat}，要求文件缺少 {label}，将静默回退默认样式",
        "used {feat} but the requirements file is missing {label}; it will silently fall back to the "
        "default style",
    ),
    "gate.label.row_settings": ("「{name}：…」配置行", "the `{name}: ...` settings row"),
    "gate.label.style_def": ("「{cn}」（{en}）定义", "the `{en}` style definition"),
    "gate.bib.required_missing": (
        "{feat}，要求文件缺少「{cn}」（{en}）定义，将静默回退默认样式",
        "{feat}, but the requirements file is missing the `{en}` style definition; it will silently fall "
        "back to the default style",
    ),
    "gate.template.missing": ("模板不存在: {path}", "Template not found: {path}"),
    "gate.template.unreadable": (
        "模板存在但读不出样式表（{err}）: {path}",
        "The template exists but its styles part cannot be read ({err}): {path}",
    ),
    "gate.template.style_absent": (
        "行 {line} 样式「{name}」在模板中不存在，格式不会生效；"
        "请在格式要求文件里补上这一条，或核对写法",
        "Line {line}: style \"{name}\" does not exist in the template, so the formatting will not take "
        "effect; add that row to the requirements file or check how it is written",
    ),
    # ── 题注 ──
    "gate.caption.table_far": (
        "表格题注未紧邻表格（上下均未检测到表格实体），会被排成孤立题注。",
        "the table caption is not adjacent to a table (none found above or below); it becomes an orphan "
        "caption.",
    ),
    "gate.caption.image_far": (
        "图片题注未紧邻图片（上下均未检测到图片实体），会被排成孤立题注。",
        "the image caption is not adjacent to an image (none found above or below); it becomes an orphan "
        "caption.",
    ),
    "gate.caption.in_alt": (
        "方括号里的文字是无障碍替代文字，不会被排成题注。"
        "题注另起一行：`%% 图片题注 {text}`（写在图片上方或下方都可），"
        "`![](…)` 的方括号留空或写一句替代文字",
        "the text in square brackets is alt text, not a caption. Put the caption on its own line: "
        "`%% Image Caption {text}` (above or below the image, either way), and leave `![](...)` "
        "empty or give it a one-line alt text",
    ),
    # ── 折行与方言 ──
    "gate.soft_wrap": (
        "上一行没有句末标点而本行紧随其后（「{snippet}」）。本引擎按「一行一段」读取，"
        "这两行会拆成两段、各吃一次首行缩进。若本意是同一段落内换行，把上一行行尾加一个 `\\`；"
        "若本意是同一段落的一整句，合并成一行；若本意就是两个短段落，不必处理",
        "the previous line has no sentence-ending punctuation and this line follows it (\"{snippet}\"); "
        "this engine reads one line as one paragraph, so the two become separate paragraphs, each with "
        "its own first-line indent. For a line break inside one paragraph, end the previous line with a "
        "backslash; to make them one running paragraph, join the lines; if they are meant to be two "
        "short paragraphs, no action is needed",
    ),
    "gate.wikilink": (
        "行 {line}: 发现未转换的 Obsidian WikiLink 语法（请改用标准 Markdown 链接）",
        "Line {line}: unconverted Obsidian WikiLink syntax (use a standard Markdown link instead)",
    ),
    "gate.latex.pagebreak": (
        "行 {line}: 发现 LaTeX 分页命令（请改用 `{{{{< pagebreak >}}}}`）",
        "Line {line}: LaTeX page-break command found (use `{{{{< pagebreak >}}}}` instead)",
    ),
    "gate.dialect.html": (
        "不支持 HTML 标签；换行用行尾两空格，换页用 `{{< pagebreak >}}`，"
        "网址直接写或写成 `[文字](网址)`",
        "HTML tags are not supported; for a line break end the line with two spaces, for a page break "
        "use `{{< pagebreak >}}`, and write URLs bare or as `[text](url)`",
    ),
    "gate.dialect.hr": (
        "不支持横向分隔线；需要分页用 `{{< pagebreak >}}`，需要分段用空行",
        "horizontal rules are not supported; use `{{< pagebreak >}}` for a page break and a blank line "
        "to start a new paragraph",
    ),
    "gate.dialect.setext": (
        "不支持 `====` 下划线式标题；标题一律写成 `# 标题`",
        "`====` underline headings are not supported; always write headings as `# Heading`",
    ),
    "gate.dialect.def_list": (
        "不支持定义列表（`术语` + `: 定义`）；两项各写成一段",
        "definition lists (`term` + `: definition`) are not supported; write each item as its own paragraph",
    ),
    "gate.dialect.task_item": (
        "不支持待办勾选框（`- [ ]`）；去掉 `[ ]` 写成普通无序列表",
        "task checkboxes (`- [ ]`) are not supported; drop the `[ ]` and write a plain bulleted list",
    ),
    "gate.dialect.heading_no_space": (
        "标题的 `#` 后面要空一格；不空格的 `#` 会连同井号一起当成正文印出来",
        "a heading's `#` must be followed by a space; without one the `#` is printed as body text",
    ),
    "gate.dialect.image_percent": (
        "图片宽度不支持百分比，请写绝对长度，例如 `{width=14cm}`",
        "percentage image widths are not supported; write an absolute length, e.g. `{width=14cm}`",
    ),
    "gate.dialect.highlight": (
        "不支持 `==高亮==`；去掉等号即可，重点靠正文样式表达",
        "`==highlight==` is not supported; drop the equals signs and let the body style carry emphasis",
    ),
    "gate.dialect.span_attr": (
        "行内属性只支持 `[文字]{.underline}`；`{.{类名}}`、`{{#标识}}` 其余写法会连同花括号印出来，"
        "要改样式请整段写成 `%% 样式名 内容`",
        "the only inline attribute is `[text]{.underline}`; other `{.{class}}` or `{{#id}}` forms are "
        "printed with their braces — for a different style write the paragraph as `%% Style content`",
    ),
    "gate.dialect.inline_math_paren": (
        "行内公式用 `$…$`，不支持 `\\(…\\)`（会连同括号当成正文印出来）",
        "inline math uses `$...$`; `\\(...\\)` is not supported and is printed as body text",
    ),
    "gate.dialect.image_attr": (
        "图片行只认 `{width=…}`；对齐请写要求文件的「图：… 左对齐」",
        "an image line only accepts `{width=...}`; for alignment add `left` to the `Figure:` row "
        "of the requirements file",
    ),
    "gate.dialect.empty_heading": (
        "标题只有 `#` 没有文字；补上标题文字，或删掉这一行",
        "the heading has `#` but no text; add the heading text or delete the line",
    ),
    "gate.dialect.table_no_edge": (
        "表格首尾都要加竖线：把 `名称 | 值` 写成 `| 名称 | 值 |`",
        "tables need pipes at both ends: write `Name | Value` as `| Name | Value |`",
    ),
    "gate.dialect.nested_quote": (
        "不支持引用块再套引用块；把内层内容改成普通段落",
        "nested blockquotes are not supported; turn the inner quote into a normal paragraph",
    ),
    "gate.dialect.wide_style_marker": (
        "样式行的 `%%` 必须是半角；全角 `％％` 会被当成正文印出来",
        "the `%%` of a style line must be half-width; the full-width `％％` is printed as body text",
    ),
    "gate.dialect.indented_code": (
        "不支持四空格缩进的代码块；代码一律用 ``` 围栏包起来",
        "four-space indented code blocks are not supported; always wrap code in ``` fences",
    ),
    "gate.dialect.unclosed_dollar": (
        "`$` 没有在同一行内闭合；行内公式要写成 `$公式$`，与文字在同一行",
        "`$` is not closed on the same line; write inline math as `$math$` on the same line as the text",
    ),
    "gate.dialect.unclosed_display_math": (
        "独占行公式 `$$` 未闭合；必须成对出现，结尾也应单独一行 `$$`",
        "the display-math `$$` is never closed; `$$` must come in pairs, with a lone `$$` on its own line "
        "at the end",
    ),
    "gate.dialect.table_needs_pipes": (
        "表格每一行都要以 `|` 开头、以 `|` 结尾；否则整行会当成正文印出来",
        "every table row must start and end with `|`; otherwise the whole line is printed as body text",
    ),
    "gate.dialect.list_second_paragraph": (
        "列表项里不支持第二段（空行加缩进）；把它写成列表项之外的一段，或用第二个列表项",
        "a second paragraph inside a list item (blank line plus indent) is not supported; write it as a "
        "paragraph after the list, or as another list item",
    ),
    # ── 稿件结构 → 要求文件该声明的样式 ──
    "gate.feat.heading2": ("二级标题 (##)", "level-2 heading (##)"),
    "gate.feat.heading3": ("三级标题 (###)", "level-3 heading (###)"),
    "gate.feat.heading4": ("四级标题 (####)", "level-4 heading (####)"),
    "gate.feat.heading5": ("五级标题 (#####)", "level-5 heading (#####)"),
    "gate.feat.heading6": ("六级标题 (######)", "level-6 heading (######)"),
    "gate.feat.toc": ("目录短代码 ({{< toc >}})", "toc shortcode ({{< toc >}})"),
    "gate.feat.block_text": ("引用块 (>)", "blockquote (>)"),
    "gate.feat.abstract_title": ("摘要标题包裹", "abstract-title span"),
    "gate.feat.abstract": ("摘要正文包裹", "abstract span"),
    "gate.feat.keywords": ("关键词包裹", "keywords span"),
    "gate.feat.references_title": ("参考文献标题包裹", "references-title span"),
    "gate.feat.bibliography": ("参考文献区块", "bibliography block"),
    "gate.feat.bibliography_yaml": ("YAML bibliography 文献库", "`bibliography:` in YAML"),
    "gate.feat.image": ("图片 (![](...))", "image (![](...))"),
    "gate.feat.table_caption": ("表格题注包裹", "table-caption span"),
    "gate.feat.table_note": ("表注包裹", "table-note span"),
    "gate.feat.markdown_table": ("Markdown 表格 (|...|)", "Markdown table (|...|)"),
}


def resolve_lang(manuscript: str | None = None, override: str | None = None) -> str:
    """决定消息语言。`override` 是 `--lang` 的原值；`auto`/None 时按稿件语种。"""
    if override in SUPPORTED:
        return override
    return "zh" if looks_chinese(manuscript or "") else "en"


def t(message_key: str, lang: str, **kwargs) -> str:
    """取一条消息。缺 key 直接抛——静默回退到另一种语言更难查。

    首参叫 `message_key` 而不是 `key`：好几条门禁消息自己要带一个 `{key}` 占位符
    （引文 key、交叉引用标签），重名会让 `t(..., key=...)` 直接炸。
    """
    zh, en = _MESSAGES[message_key]
    text = en if lang == "en" else zh
    return text.format(**kwargs) if kwargs else text


# 报错里举例用的样式（中文名见 `STYLE_CN`，正典名见 `STYLE_EN`，都从 `STYLE_MAP` 反推）
EXAMPLE_STYLES = ("Abstract", "Keywords", "Table Caption", "Table Note", "References Title")


def style_name(style: str, lang: str) -> str:
    """样式名按消息语言回显：英文稿写 `Abstract`，中文稿写「摘要」。

    词表是唯一真相源（`spec/constants.STYLE_MAP`），这里不抄名字；查不到就原样返回
    正典名——报错宁可英文，也不能把 Word 内部名印成中文。
    """
    from md_to_word.spec.constants import STYLE_CN

    return STYLE_CN.get(style, style) if lang != "en" else style


def style_examples(lang: str) -> str:
    """「如 摘要 / 关键词 / …」这一串示例名，跟消息语言一起走。"""
    return " / ".join(style_name(s, lang) for s in EXAMPLE_STYLES)
