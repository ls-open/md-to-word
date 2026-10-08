# 设计原理

**适用范围**：本技能的**内部机制面**——底模机制、三重净化、公式引擎、缩进单位换算、reference-doc 携带机制、故障排查原理。

---

## 1. 模板生成原理

> **引擎关系**：导出由 Quarto 渲染，Quarto 内嵌 Pandoc，docx 的样式映射/段落转换均由 Pandoc 的 docx writer 完成，故本文故障排查沿用 "Pandoc" 指代该底层行为。

### 1.1 纯净现代 Word 365 底模机制

本框架使用**纯净现代 Word 365 基础母版**（由 `create_pure_modern_base.py` 按 Word 365 规范直接构建 `pure_modern_base.docx`）。
- **原生现代架构**：基于 ISO/IEC 29500 与 Word 365（`AppVersion=16.0000`、`w14–w16du` 命名空间）组装 OPC 包，`compatibilityMode` 写 **15**——这是**真实 Word 365 新建文档**自己写的值（公开文档记载的合法值只有 11/12/14/15），导出文档打开无 `[兼容模式]` 警告；
- **标准槽位注册**：在纯净文档中预先注册 Word 365 核心根样式与全部标准学术样式 ID（如 `Title`, `Abstract`, `Heading 1..9`, `BodyText`, `Compact`, `TableCaption`, `TableNote`, `Bibliography`, `Table` 等），与 Quarto / Pandoc 内部解析器 100% 精确对接；
- **现代数学支持**：原生写入现代 OMML 数学公式配置，支持 Cambria Math 居中渲染。

**增补一个写法 = 两处同步**：① `generate_template.py` 加一行（`_LINE_KEYS` 或 `_CLAUSE_TABLE`）；
② `reference.md §1.5` 加一行（唯一写法 + 示例 + 错误写法），保持代码词表与文档速查表一致。

**什么不该加**：能力边界见 `reference.md §1.4`。判据是——新写法若只是"再多一个段落/字符/
表格属性"就可以加；若要求一套新的 OOXML 部件或后处理阶段，先问"要求方真的明文写了吗"。
**解释要求，不猜测要求。**

---

## 2. 深层故障排查

### 2.1 中文字体不对

原因：Pandoc 默认模板中 Heading 1、Heading 2 等样式的 rFonts 带有 `eastAsiaTheme="majorEastAsia"`，Word 的主题优先级高于 `eastAsia` 显式指定，导致中文字体被宋体覆盖。
解决：用 `generate_template.py` 重新生成模板——它改样式时会清掉 `eastAsiaTheme` 属性。

### 2.2 字体被主题属性覆盖

与 §2.1 同一原因、同一解法：症状表现为「标题设了 Times New Roman 却显示 Calibri Light」。

### 2.3 表格内外字体

Pandoc 将表格单元格映射为 `Compact` 样式。正文段落映射为 `Body Text` / `First Paragraph`。

- **表格内外无特殊要求**：将 `Compact` 设为与 `Body Text`、`First Paragraph`、`Normal` 相同的字体、字号、行距，效果统一
- **表格内有特殊要求**（如表格内 10pt、表格外 12pt）：直接在 `requirements.txt` 中按表格内标准设 `Compact`，Pandoc 会自动应用到表格内文字，无需任何 Word 后处理

### 2.4 GB/T 7714 引用显示中文"等"而非英文"et al."

症状：使用 GB/T 7714 CSL 时，纯英文文献库的条目显示"等"而非"et al."。
原因：Pandoc 的 citeproc **不支持 CSL-M 多语种 layout**。GB/T 7714 CSL 中的多语种 layout 块已被注释掉（取消注释会导致 `CiteprocParseError: Multiple layout elements present in bibliography`）。`.bib` 条目中的 `language={en}` 字段**不会**触发自动切换。
解决：纯英文文献库 → 将 CSL 文件中的 `default-locale="zh-CN"` 改为 `default-locale="en-US"`，所有条目渲染"et al."。纯中文文献库 → 保持 `zh-CN`。中英文混排 → 不支持，需用户根据主体语言选一种 locale，或在 Word 中手动替换。

### 2.5 图片宽度被截断为 14.82cm

症状：MD 中写 `{width=15cm}`，导出后图片实际宽度只有 14.817cm。
原因：模板的 sectPr 中缺少 `pgSz` 或 `pgMar`，Pandoc 算不出内容宽度，回退到 420pt（≈14.817cm）。
解决：用最新版 `generate_template.py` 重新生成模板（页面尺寸由 requirements 的 `纸张：A4|Letter` 行设定），脚本会自动写入 pgSz + pgMar（2.54cm 边距）。旧模板也可在 Word 中手动设置页面尺寸和页边距。

### 2.6 图片因文件名空格无法加载

症状：`![图 1](file name.png)` 导出后图片缺失，Pandoc 无报错或报路径不存在。
原因：标准 Markdown 链接语法 `[]()` 和 `![]()` 的路径部分遵循 URL 规范（RFC 3986），空格不是合法字符。Pandoc 无法正确解析含空格的路径，导致图片静默加载失败。
解决：将文件名中的空格替换为**下划线或连字符**（如 `file_name.png`），或使用 `%20` 编码空格（`file%20name.png`）。推荐前者，可读性更好。

### 2.7 文档/论文主标题误用 `#` 导致标题层级整体错位

症状：文档/论文主标题用 `# 标题`，所有章节标题被挤到 `##`/`###`/`####`，编号与层级全部错位。
原因：Pandoc 的 `#` 固定映射到 Heading 1（章节标题样式），不是 Title（文档标题样式）。两者样式不同（Title 通常二号/16pt 居中，Heading 1 通常三号/14pt）。如果主标题用 `#`，会变成 Heading 1 样式，丢失 Title 样式，还会把所有章节标题挤到 `##`/`###`，导致标题层级整体错位。
解决：文档主标题用 YAML `title:` 字段（Pandoc 自动渲染为 Title 样式），章节标题从 `# 1. 绪论`（1 级）开始。

### 2.8 CSL direct formatting 属性覆盖模板样式

症状：同一个 requirements.txt 在不同 CSL 下，参考文献的悬挂缩进、行距、段间距行为不一致。
原因：CSL 规范定义了两种悬挂缩进机制——`hanging-indent="true"`（Pandoc 直接设置段落 direct formatting）和 `second-field-align="flush"`（Pandoc 应输出 Tab 但实际输出空格，是已知实现缺陷）。两种机制行为不一致，且都会绕过模板控制，覆盖 requirements.txt 中 Bibliography 样式的设置。
解决：所有 CSL 的 `<bibliography>` 标签均已去掉 `hanging-indent`、`second-field-align`、`line-spacing` 等 direct formatting 属性（运行 `scripts/normalize_csl.py` 自动处理）。悬挂缩进由 requirements.txt 中 Bibliography 样式的"悬挂缩进0.5英寸"控制，所有 CSL 行为一致，AI 可预测。新增 CSL 必须运行 `python3 scripts/normalize_csl.py resources/csl/新期刊.csl` 规范化。

### 2.9 参考文献 Tab 残留导致悬挂失效

症状：参考文献列表中每一行内容都跑到 left_indent 处，看起来像没有悬挂，实际上连首行都缩进了。
原因：CSL 含 `second-field-align="flush"`（未规范化），Pandoc 在编号 "1." 后插入 Tab，Tab 跳到 `left_indent` 位置，导致每一行内容都跑到 left_indent 处。
解决：运行 `scripts/normalize_csl.py` 规范化技能文件夹的 CSL（去掉 `second-field-align="flush"`）。

### 2.10 静默失败防护（字号无单位、行距变体）

症状：requirements.txt 写 `12`（无单位）、`双倍行距`/`靠左`（非规范写法），或漏写某个必填字段。
原因：每个属性只有一种规范写法，全部列在 `_CLAUSE_TABLE` 子句表（与 reference.md §1.5 同一张表）。**认不出的词在解析期即当场报错**（给行号、原词、应写形式），不会静默丢弃——旧实现逐属性做子串探测，认不出就无声忽略：既漏（写了不生效）又错（`最小行距25磅` 被当成固定值用）。
解决：解析器与必填校验形成双层防线：① 写错的词（如 `12` 无单位、`双倍行距`）在词法消费阶段直接报错并给出应写形式；② 干脆没写的属性由 `_check_required_fields` 直接拦截，确保每个声明样式的字体、字号、对齐、行距、段前段后、缩进（及标题类的加粗/倾斜）全部显式填写。

### 2.11 表格对齐 jc 继承机制

症状：requirements.txt 写了 `表格：居中`，但导出的表格仍左对齐，右边剩大片空白。
原因：Pandoc 生成的表格**不输出**表格级 `<w:jc>` 元素，但会**继承** Table 样式的 `tblPr/jc`（OOXML 规范 ECMA-376 §17.7.6 规定 Table 样式属性 "always applied" 除非被表格实例覆盖）。所以只要模板的 Table 样式 `tblPr` 里有 `<w:jc w:val="center"/>`，所有表格自动居中。
解决：在 requirements.txt 中写 `表格：居中`，`generate_template.py` 会在 Table 样式的 tblPr 中插入 jc 元素。

### 2.12 OOXML schema 顺序要求（jc 必须在 tblBorders 之前）

症状：Table 样式 tblPr 中有 jc 元素，但表格仍左对齐，Word 忽略了 jc。
原因：`jc` 元素必须在 `tblBorders` **之前**（OOXML schema 顺序：`tblStyle → tblW → jc → tblInd → tblBorders → tblLayout → tblLook`）。如果 jc 在 tblBorders 之后，Word 会忽略 jc。
解决：`generate_template.py` 已按正确顺序插入（用 `tbl_pr.insert(0, jc_el)` 插入到最前面）。

### 2.13 First Paragraph 必填原理

症状：requirements.txt 只定义了 `正文 Body Text`，未定义 `首段 First Paragraph`，章节首段格式错误（无缩进或缩进错误）。
原因：Pandoc 把章节首段映射为 `First Paragraph` 样式（不是 `Body Text`）。如果只定义了 `Body Text` 而没定义 `First Paragraph`，章节首段会用 Pandoc 默认样式。
解决：requirements.txt 必须显式定义 `首段` 样式，通常 `首行缩进0字符`（APA 标准章节首段不缩进），与正文（`首行缩进2字符`）区分。generate_template.py 将 First Paragraph 列为必填样式之一（必填样式清单见 `REQUIRED_STYLES`，会随需求演进）。

### 2.14 间距清零原理（段前段后显式写 0）

症状：requirements.txt 写 `行距2倍` 但未写段前段后，导出后正文段落之间仍有额外间距，"双倍行距贯穿全文"未实现。
原因：Pandoc 默认模板中大多数样式自带段前/段后间距（如 Body Text 默认段前段后各 9pt）。仅设置行距不清零段间距，最终间距 = 双倍行距 + 段前 9pt + 段后 9pt。
解决：在 requirements.txt 中显式写 `段前0磅 段后0磅`（必须显式写 `0` 才能覆盖默认值）。generate_template.py 将段前段后列为必填字段。

### 2.15 LaTeX 分页符对 docx 无效

症状：MD 中用 `\newpage` 分页，导出的 docx 中不生效，段落连在一起。
原因：`\newpage` 是 LaTeX 命令，Pandoc 的 docx writer 不支持（已知限制，GitHub #6358/#1934）。
解决：改用 Quarto 标准短代码 `{{< pagebreak >}}`（`check_md.py` 会拦下 LaTeX 那几个写法
并给出这一句）。它在 docx 下产出 `<w:br w:type="page"/>`，与手写 raw openxml 块等效，
但不必写 XML。不生效时再在导出的 Word 文档中手动插入分页符。

### 2.15.1 分节与目录：为什么在 Markdown 里展开，而不是导出后改 docx

**`{=openxml}` 围栏块会被 Quarto 原样写进 `word/document.xml`**（实测：写一段含 `sectPr`
的围栏块，产物里就真多一个 `sectPr`）。于是分节符、目录域这类 Pandoc 语法里没有的东西都能
停在标记层表达，不必再写"改产物 XML"的后处理。

`expand_markers.py` 在**预检之后、渲染之前**把标记换成 OOXML 块：

- 放在预检之后，是为了让 `check_md.py` 校验的仍是作者写的标记本身（未独占一行、拼错的
  短代码都该在那一层报错），而 Quarto 只看到展开后的结果。
- 展开要读参考模板的 `word/document.xml`：新节的页面几何与页脚引用整段抄正文节。
  rId 是模板自己的编号，**pandoc 会照搬**（实测两次渲染一致），故抄过来在产物里同样有效。

展开用的是渲染前的临时副本，**必须与原稿同目录**（YAML 的 bibliography/csl 与图片路径都是
相对稿件目录写的），并由 `CLEANUP_FILES` + trap 清理。

### 2.16 参考文献不生成

症状：导出的 docx 中没有参考文献列表。
原因：缺 `--citeproc` 或 frontmatter 中 bibliography 路径不对。
解决：确认 Pandoc 命令包含 `--citeproc`，确认 .bib 文件路径正确。如果路径是相对路径，导出时先 `cd` 到 MD 文件所在目录。

### 2.17 样式映射不上

症状：导出的 docx 中某些段落格式不对（如关键词没有 Keywords 样式）。
原因：模板中样式名不符合 Pandoc 默认要求（常见：自定义了新样式而非修改已有的，或用错了样式 ID）。
解决：检查 `pure_modern_base.docx` 或通过 `create_pure_modern_base.py` 核对注册的标准样式名和 styleId，再用 `python-docx` 对比目标模板确认。

### 2.18 图片无法显示

症状：导出的 docx 中图片缺失（空白框或红叉），Pandoc 无报错。
原因：`![](path)` 中的路径不对，Pandoc/Quarto 找不到文件。
解决：
1. 绝对路径（`/Users/...`）与相对路径均可；`export.sh` 已自动追加 `--resource-path "$RESOURCE_PATH:/"`（含输入目录、git 仓库根目录与根 `/`）。根 `/` 使绝对路径不被 Quarto 误解析为 `./Users/...`（否则图片静默丢弃、仅有 warning）；
2. 图片放在稿件同目录、子目录或同一 Git 仓库下均可，写相对路径或绝对路径即可，无需在 YAML 配置 `resource-path`；
3. 图片文件不存在时 `check_md.py` 会在导出前拦截（预检报图片缺失），不静默失败。

### 2.19 代码块内 `:::` 包裹误检测

症状：check_md.py 报代码块内部的 `::: {custom-style="X"}` 为"未在模板中定义"。
原因：脚本未跟踪代码块围栏状态，将代码块内的示例包裹误认为正文包裹。
`check_md.py` 已跟踪代码块围栏状态，代码块内部出现的 `::: {custom-style="X"}` 不会被误检测。
