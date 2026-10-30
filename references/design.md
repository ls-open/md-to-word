# 设计原理

**适用范围**：本技能的**内部机制面**——底模机制、主题净化、公式引擎、缩进单位换算、reference-doc 携带机制、故障排查原理。

> **本文所有「实测」都是 macOS 上测的**：渲染要过本机 Microsoft Word，而 `--pdf` 这条通道
> 本身也只支持 macOS。Windows 版 Word 尚未试过——凡涉及 Word 排版行为的结论，跨平台时
> 请当成「待验证」，不要当成「已确定」。

---

## Contents

- 模板生成原理
- 深层故障排查
- 分发形态：一份实现，两个入口
- 为什么是 AI 原生

## 1. 模板生成原理

> **引擎关系**：导出由本技能自己的写出器完成——读取器把契约 Markdown 变成文档模型，写出器把模型直接写成 OOXML。没有中间引擎，所以"为什么长这样"都能在代码里指到具体一行。

### 1.1 纯净现代 Word 365 底模机制

本框架使用**纯净现代 Word 365 基础母版**（由 `create_pure_modern_base.py` 按 Word 365 规范直接构建 `pure_modern_base.docx`）。
- **原生现代架构**：基于 ISO/IEC 29500 与 Word 365（`AppVersion=16.0000`、`w14–w16du` 命名空间）组装 OPC 包，`compatibilityMode` 写 **15**——这是**真实 Word 365 新建文档**自己写的值（公开文档记载的合法值只有 11/12/14/15），导出文档打开无 `[兼容模式]` 警告；
- **标准槽位注册**：在纯净文档中预先注册 Word 365 核心根样式与全部标准学术样式 ID（如 `Title`, `Abstract`, `Heading 1..9`, `BodyText`, `Compact`, `TableCaption`, `TableNote`, `Bibliography`, `Table` 等），与 Word 内置样式名精确对接；
- **现代数学支持**：原生写入现代 OMML 数学公式配置，支持 Cambria Math 居中渲染。

### 1.2 主题属性工作原理与两道净化

在 Word 的 OOXML 规范中，**主题属性（Theme Attributes）优先级高于显式字体指定**：

```xml
<!-- 显式指定 → 会被主题覆盖 -->
<w:rFonts w:ascii="Times New Roman"/>

<!-- 主题引用 → 优先级更高，若残留会强制覆盖显式字体 -->
<w:rFonts w:asciiTheme="majorHAnsi"/>
```

为杜绝"设置了样式却不生效"的隐蔽 Bug，框架在两处净化：
1. **底模生成阶段（源头零污染）**：`create_pure_modern_base.py` 构建 `styles.xml` 时不写入任何 `asciiTheme`、`eastAsiaTheme`、`themeColor` 属性或非黑颜色；
2. **模板刷样阶段（过程净化）**：`src/md_to_word/template/generator.py` 保存时刻对 `styles.xml` 再次执行递归清理。

写出器本身不再引入主题标记，所以没有第三处。剥除范围是字体（`asciiTheme` 等）、颜色
（`themeColor`/`themeTint`/`themeShade`）与底纹（`themeFill`/`themeFillTint`/`themeFillShade`）
三类：`w:shd` 同时写 `fill` 与 `themeFill` 时以主题色为准，漏掉它同样是"设了不生效"。

### 1.3 学术公式居中与编号靠右对齐

**靠右没有任何原生路径**：OMML 里的公式对象没有"对齐到右边"这个概念，编号如果塞在
公式对象内部，就只能跟着公式走。本技能的写法是**段落级的三段制表位**——左制表位靠版心
左边、中心制表位在版心中线、右制表位在版心右边，公式落在中间那段，编号落在右边那段：

```xml
<w:tabs><w:tab w:val="center" w:pos="4150"/><w:tab w:val="right" w:pos="8300"/></w:tabs>
<w:r><w:tab/></w:r><m:oMath>…</m:oMath><w:r><w:tab/></w:r><w:r>(1)</w:r>
```

比"用无边框表格摆三列"简单得多：没有列宽要算、没有 `tblLayout` 要钉，也不会因为
列宽随编号长度变化而折行。

代价是 Word 按**行内公式**排它：段落里除了公式还有别的东西（制表位、编号都算），Word
就缩小编排——分式变小、求和的上下限挪到右侧。要拿到显示样式，只能让段落里只剩公式，
而那样编号就没法停在同一行。本工具选的是 Word 的常规做法。**没有编号**的独立公式则
段落里只放公式（居中），因此按显示样式排。

**编号来源与编号外观分属两层**：

| | 谁定 | 在哪 |
|:--|:--|:--|
| 哪些公式有编号 | 只有带 `{#eq-标签}` 的公式进编号序列，没标签的不编号也不占号 | `writer/docx_writer.py::_collect_equation_numbers` |
| 章号与序号 | 写出器按出现顺序给序号；YAML 开 `crossref.chapters: true` 时再按一级标题数出章号 | 同上（存成 `(章号, 序号)` 二元组） |
| 括号与分隔符 | 要求文件的 `公式编号格式：`，一个 `{n}`／`{c}` 模板；不写按语种给默认 | `_render_eq_number` |
| 正文交叉引用 | 前缀（YAML `crossref.eq-prefix`）+ 同一份模板渲染，两处永远一致 | `_resolve_crossref` |

**为什么是模板而不是枚举**：「全角括号 / 半角括号 / 短横 / 点号 / 中间加空格」拆成开关就是
组合爆炸，每一种还得各配一条文档与一个测试。模板一行说完，且写错了当场报错（只认 `{n}`
与 `{c}`，缺 `{n}` 也报）。默认值按稿件语种给，所以多数稿件一个字都不用写。

### 1.4 工作流程图

```
格式要求.txt → parse_format() → 属性字典列表
                                               │
纯净 Word 365 底模 pure_modern_base.docx → Document(tmp.docx) │
                          ↓                    ↓
                   modify_style() ←────────────┘
                          │
                    设置字体/字号/行距/缩进
                    清除主题属性（关键！）
                          │
                   Table 三线表边框
                   Hyperlink 黑色
                   清理 Char 样式
                   Caption 基样式斜体清除
                   页面尺寸 pgSz + pgMar（修复图片宽度）
                   Captioned Figure 居中（原生图语法）
                          │
                   保存 → 模板.docx
```

### 1.5 页面尺寸与图片宽度（pgSz + pgMar）

版心宽 = `pgSz.w - pgMar.left - pgMar.right`；模板保存前由
`src/md_to_word/template/generator.py` 按 `纸张：` 行写入这两组元素，缺任一项按 A4 + 2.54cm 兜底。

**装订线折进左边距写**：`w:gutter` 不进上述公式，版心会算大，所以 `pgMar/@w:left` 写
`左边距 + 装订线`。`_content_width_twips` 已含装订线，仍漏加的是目录的 `dot_leader_pos`
（生成时只传了页边距）。对账侧（`audit/inspector.py`）左边的期望值也加上装订线。

### 1.6 原生图语法居中

图片行 `![](path){width=Xcm}` 落成 Captioned Figure 段落，模板中已设为居中。

### 1.6.1 PDF 图为什么在导出时栅格化

Word 的内联图片只有位图这一种形态，PDF 的矢量内容没有直接嵌入方式；学术稿的图大多默认导出
PDF，所以转换放在导出流程里，三个决定都有具体理由：

| 决定 | 为什么 |
|:--|:--|
| 按**声明宽度的 300 dpi** 渲染 | 宽度越大、图上的小字越模糊；按页面尺寸渲染再缩放撑不住印刷 |
| 未声明宽度时按页面物理尺寸，并写 PNG 的 `pHYs` | python-docx 按 PNG 里的 DPI 还原尺寸，缺这个块会按 72 dpi 算，图大出四倍 |
| 自己写 PNG 编码器（`utils/pdf_figure.py`） | 只要 zlib 一行压缩，不值得为它拉 Pillow；顺带保证字节可复现 |

### 1.7 缩进单位换算技术细节

`src/md_to_word/template/generator.py` 的缩进子句支持两种单位（单写法收敛，厘米单位已移除）：

| 单位 | OOXML 属性 | 换算关系 | 用途 |
|------|-----------|---------|------|
| 字符 | `firstLineChars` / `hangingChars` + `leftChars` | Word **根据段落字号自动计算**实际缩进量 | 中文正文首行缩进（`首行缩进2字符`）|
| 英寸 | `firstLine` / `hanging` | 1 inch = 72 pt | 英文首行缩进（`首行缩进0.5英寸`）与参考文献悬挂缩进（`悬挂缩进0.5英寸`）|

**字符单位的优势**：12pt 字号下 2 字符 = 24pt = 0.85cm；10.5pt 字号下 2 字符 = 21pt = 0.74cm。字号变化时缩进比例自动保持，比固定 pt 值更准确。

**关键数值对照**：
- 中文正文 `首行缩进2字符`（12pt 字号下 = 24pt = 0.85cm）
- 参考文献 `悬挂缩进0.5英寸`（= 36pt = 1.27cm，APA/MLA/Chicago/Vancouver 国际标准）
- **⚠️ 2 字符 ≠ 0.5 inch**：APA 标准的 0.5 inch = 36pt = 1.27cm，中文排版的 2 字符在 12pt 字号下 = 24pt = 0.85cm，两者是不同体系的数值，不能混用。英文论文用 `首行缩进0.5英寸`，中文论文用 `首行缩进2字符`。

### 1.8 底模里哪些东西会被带走（**改模板前必读**）

**为什么要自己生成模板**：Word 的样式槽位是封闭的，用的样式不在 `styles.xml` 里就只能退成普通段落。生成器只从底模拿走三类东西，其余一概不用：

| 会被带走 | 不会被带走 |
|:--|:--|
| `word/styles.xml` 样式表 | 正文内容（`document.xml` 的段落一概忽略） |
| 文档属性：页面尺寸、页边距、**页眉、页脚** | 多节结构（见 §1.8.1） |
| `word/header*.xml`、`word/footer*.xml` 全部部件 | 域的计算结果（域由 Word 更新） |

所以**页眉 / 页脚 / 页码是模板能力，不是导出后手工补的活**——`manual.md §6` 把它列进
「完全支持」的理由就在这里。

#### 1.8.1 模板只有一节，多节由标记在渲染层插入

模板由 `template/generator.py` 从要求文件生成，只包含正文那一个 `sectPr`，页眉页脚与页面
几何都写在这一节上；生成后强制校验单节。

- 单节内能做的全都能做：奇偶页不同页眉页脚（`evenAndOddHeaders` + `default`/`even`
  两个 `headerReference`）、首页不同、起始页码与页码格式；
- **跨节切换页码格式**（前置罗马 → 正文阿拉伯）不在模板里做，改由正文的 `{{< section >}}`
  标记在渲染前展开成 OOXML 分节符（§1.8.2）：它整段继承模板正文节的页面几何与页脚引用，
  只改分节类型与页码格式——另外**剥掉 `headerReference` 与 `titlePg`**（前置件不排页眉；
  `titlePg` 是「文档起始页」的概念，中间节带着它只会让本节首页改用 first 页脚）。

#### 1.8.2 分节与目录：模型节点，不是字符串替换

`{{< section >}}` 与 `{{< toc >}}` 在读取阶段变成两个模型节点（`SectionBreak` / `Toc`），
写出器把它们落成原生 OOXML：

- **分节**：`sectPr` 在 OOXML 里描述的是**上面那一节**，所以分节符写成"上一节段落属性里的
  `sectPr`"。新节的页面几何、页脚引用整段抄模板的正文节，只改分节类型与页码格式；同时
  **剥掉 `headerReference` 与 `titlePg`**（前置件不排页眉，`titlePg` 只属于文档起始页）。
- **目录**：写成 `w:sdt` 里的 TOC 域。Word 打开时算页码，所以每次打开都会问一次"是否更新
  这些域"——点"是"即得正确页码，`Ctrl+A` → `F9` 可强制重算。

模板只有一节，多节只能由正文标记产生，页面几何因此不会互相打架。

### 1.9 format.txt 是一门**封闭**的小语言

它是本技能唯一的用户界面，只有两级语法，各由 `src/md_to_word/spec/parser.py` 里的一张表实现：
行级键 `_LINE_KEYS`（`纸张：A4`）与样式行子句 `_CLAUSE_TABLE`（`正文：宋体 小四 …`）。

**规矩只有一条：认不出的东西一律报错**（行号 + 原词 + 应写形式），没有"静默忽略"这第三种结果。
**认得出来但没前提的，一样报错**：`边框粗` 没有下边框、`跨页重复` 不在 `表头：`、`加入目录` 挂在
正文类样式上，都在解析期拦下——判据是**能否在 XML 里指出它落在哪**。

**为什么封闭**：用法是 AI 读要求原文 → 转写成 format.txt → 严格校验；多收一个同义写法就取消了
对转写的唯一验证手段。

**增补一个写法 = 四处同步**：① `_LINE_KEYS` / `_CLAUSE_TABLE`（必须）；② `manual.md §3.1`（必须）；
③ `audit/inspector.py` 能对账；④ `template/extractor.py` 能读进草稿。后两处可以空，但要写明为什么。
判据同上：这条写法落到哪个 XML 节点？指得出来就该能对账。

---

### 1.10 导出的 docx 为什么字节可复现

同一份稿件重跑要逐字节一致，否则 Git 里全是"内容没改却变了"的二进制 diff。底模不写 dcterms
时间戳，剩下的变量只有 zip 条目时间：`utils/docx_zip.py::normalize_zip` 统一钉成 `1980-01-01`
（DOS 起点），`tests/test_docx_writer.py` 用两次导出逐字节比对守着它。

### 1.11 文档网格为什么要按行距倍数补偿

Word 的「文档网格」（`w:docGrid`）只在**单倍行距**下才等于声明的行数：网格间距还会被
段落行距的**倍数**再乘一遍。实测声明 `每页22行`（A4 + 2.54cm 边距，linePitch=634）：

| 正文行距 | 第 1 页实际行数 |
|:--|:--|
| 1.0 倍 | 21 |
| 1.5 倍 | 14 |
| 2.0 倍 | 11 |

即 `实际行数 = N ÷ 行距倍数`。这是 Word 自己的行为（在 Word 里设「每页 22 行」再配 1.5 倍
行距，结果一样）。

与其要求作者把行距改成单倍，不如**按结果补偿**：`linePitch = 版心高 ÷ N ÷ 正文行距倍数`。
按正文（Body Text，退回 Normal）的倍数算，固定值行距不参与相乘（Word 只把行高向上取整到
网格，故不除）。补偿后三种行距实测都落 21 行（第一页另有标题占位），声明的 N 行就是 N 行。

### 1.11.1 为什么不提供「每行 N 字」

Word 的「文档网格」除了每页行数，还能指定每行字数，落点是 `w:docGrid/@charSpace`
（配合 `w:type="linesAndChars"`）。实测下来这条路不宜接：

| charSpace | 渲染出的每行字数（A4、2.54cm 边距、12pt 宋体） |
|:--|:--|
| 0（`type="lines"`） | 37 |
| 34 | 37 |
| 343 | 37 |
| 3000 | 35 |

按「1/100 字符」推算，34 对应的正是 28 字/行，可 Word 无动于衷；退到 3000 才挪了两字。
也就是说，这个属性与字号、对齐方式的交互没有可靠的换算关系，照文档推出来的值会静默落空——
而落空的表现是「版面看着还行、行数不对」，正是本项目最想避免的那类失败。

实际的「每行 28 字」（GB/T 9704 公文）不是设出来的，**是算出来的**：三号字（16pt，约
320 twips）配 15.6cm 版心（约 8845 twips），8845 ÷ 320 ≈ 27.6，自然落 28 字。所以要求
文件里把字号写对就够了，网格只管「每页行数」这种与内容无关的度量。

### 1.12 引文引擎：借版面，自己补处理阶段

`citeproc-py` 只实现 CSL 的**版面与变量格式化**，不实现处理阶段：`disambiguate-add-names`、
`add-givenname`、`add-year-suffix`、`givenname-disambiguation-rule` 在它的源码里只出现在默认值
常量中，全库没有一处读取（`If.render` 还留着 `# TODO self.get('disambiguate')`）。缺的阶段
做不对时产物**看不出来错**，所以由我们补：

| 阶段 | 在哪 |
|:--|:--|
| 文献表排序（`sort_bibliography()` 实测不生效） | `citations.py::_ordered_keys` |
| 数字制合并 `[4,5,6]→[4–6]` | `_collapse_numeric_runs` |
| 终止标点后不补句点（`Automated?.` → `Automated?`，引号包住的同样） | `_merge_duplicate_period` |
| 同年份后缀 `2020a/b`（写进条目数据的 `year-suffix`） | `CitationEngine.reserve` |
| 同姓补首字母（条目副本）、同首作者补名字（样式副本）、分不开再加后缀 | `transform/disambiguation.py` |

`reserve()` 必须在第一次渲染前调用（形态与后缀都进缓存），所以流水线先读模型、交出真正引用到
的 key。首字母走条目副本（CSL 没有「只给第一个名字加首字母」的写法），补名字走样式副本（显示
几个名字是样式属性）；一个括号里混着两种形态时逐条渲染再按样式的分隔符合并。

---

## 2. 深层故障排查

### 2.1 中文字体不对

原因：底模的 Heading 样式 rFonts 带着 `eastAsiaTheme="majorEastAsia"` 这类主题引用，Word 的主题优先级**高于** `eastAsia` 的显式指定，中文字体因此被换掉。
解决：用 `src/md_to_word/template/generator.py` 重新生成模板——它改样式时会清掉 `eastAsiaTheme` 属性。

### 2.2 字体被主题属性覆盖

与 §2.1 同一原因、同一解法：症状表现为「标题设了 Times New Roman 却显示 Calibri Light」。

### 2.3 表格内外字体

写出器把表格单元格里的段落统一套 `Compact` 样式。正文段落落 `Body Text` / `First Paragraph`。

- **表格内外无特殊要求**：将 `Compact` 设为与 `Body Text`、`First Paragraph`、`Normal` 相同的字体、字号、行距，效果统一
- **表格内有特殊要求**（如表格内 10pt、表格外 12pt）：直接在 `format.txt` 中按表格内标准设 `Compact`，表格内文字自动跟着变

### 2.4 GB/T 7714 引用显示中文"等"而非英文"et al."

症状：使用 GB/T 7714 CSL 时，纯英文文献库的条目显示"等"而非"et al."。
原因：citeproc-py **不支持 CSL-M 多语种 layout**。GB/T 7714 CSL 中的多语种 layout 块已被注释掉（取消注释会导致 `CiteprocParseError: Multiple layout elements present in bibliography`）。`.bib` 条目中的 `language={en}` 字段**不会**触发自动切换。
解决：纯英文文献库 → 将 CSL 文件中的 `default-locale="zh-CN"` 改为 `default-locale="en-US"`，所有条目渲染"et al."。纯中文文献库 → 保持 `zh-CN`。中英文混排 → 不支持，需用户根据主体语言选一种 locale，或在 Word 中手动替换。

### 2.5 图片宽度被截断为 14.82cm

症状：MD 中写 `{width=15cm}`，导出后图片实际宽度只有 14.817cm。
原因与解决见 §1.5——模板 sectPr 缺 `pgSz`/`pgMar` 时只能按兜底值算版心；用
`src/md_to_word/template/generator.py` 重新生成模板即可（它按格式文件的 `纸张：` 行写入这两个元素）。

### 2.6 图片因文件名空格无法加载

症状：`![图 1](file name.png)` 导出后图片缺失，或报路径不存在。
原因：图片行的路径不允许空白，引擎按字面取路径；预检会在导出前拦下。
解决：将文件名中的空格替换为**下划线或连字符**（如 `file_name.png`）。

### 2.7 文档/论文主标题误用 `#` 导致标题层级整体错位

症状：文档/论文主标题用 `# 标题`，所有章节标题被挤到 `##`/`###`/`####`，编号与层级全部错位。
原因：`#` 固定映射到 Heading 1（章节标题样式），不是 Title（文档标题样式）。两者样式不同（本项目的表里 Title 通常**二号**（＝22pt）、Heading 1 通常**三号**（＝16pt）；14pt 是四号）。如果主标题用 `#`，会变成 Heading 1 样式，丢失 Title 样式，还会把所有章节标题挤到 `##`/`###`，导致标题层级整体错位。
解决：文档主标题写一行 `%% 文档标题 标题文字`（落 Title 样式），章节标题从 `# 1. 绪论`（1 级）开始。
主标题不放 YAML：YAML 没有位置，而主标题未必在第一页（学位论文常见「封面 → 标题页」两页结构）。

### 2.8 CSL direct formatting 属性覆盖模板样式

症状：同一个 format.txt 在不同 CSL 下，参考文献的悬挂缩进、行距、段间距行为不一致。
原因：CSL 有两种悬挂缩进机制——`hanging-indent="true"` 与 `second-field-align="flush"`，都会写成段落级 direct formatting，绕过模板，覆盖 Bibliography 样式的设置。
解决：内置 CSL 都已用 `scripts/normalize_csl.py` 去掉 `<bibliography>` 上的 `hanging-indent`、`second-field-align`、`line-spacing` 等 direct formatting 属性，悬挂缩进改由 format.txt 的 Bibliography 样式（`悬挂缩进0.5英寸`）统一控制。**新增 CSL 必须跑一次**：`python3 scripts/normalize_csl.py resources/csl/新期刊.csl`。

### 2.9 参考文献 Tab 残留导致悬挂失效

症状：每行内容都停在 `left_indent` 处，看起来像没有悬挂，实际连首行也缩进了。
原因与解决同 §2.8：CSL 里残留 `second-field-align="flush"`，编号后的 Tab 跳到了 `left_indent`。

### 2.10 静默失败防护（字号无单位、行距变体）

症状：format.txt 写 `12`（无单位）、`双倍行距`/`靠左`（非规范写法），或漏写某个必填字段。
原因：每个属性只有一种规范写法，全部列在 `_CLAUSE_TABLE` 子句表（与 manual.md §3.1 同一张表）。**认不出的词在解析期即当场报错**（给行号、原词、应写形式），不会静默丢弃——旧实现逐属性做子串探测，认不出就无声忽略：既漏（写了不生效）又错（`最小行距25磅` 被当成固定值用）。
解决：解析器与必填校验形成双层防线：① 写错的词（如 `12` 无单位、`双倍行距`）在词法消费阶段直接报错并给出应写形式；② 完全没写的属性由 `_check_required_fields` 直接拦截，确保每个声明样式的字体、字号、对齐、行距、段前段后、缩进（及标题类的加粗/倾斜）全部显式填写。

### 2.11 表格对齐 jc 继承机制

症状：format.txt 写了 `表格：居中`，但导出的表格仍左对齐，右边剩大片空白。
原因：写出器**不输出**表格级 `<w:jc>`，表格会**继承** Table 样式的 `tblPr/jc`（OOXML 规范 ECMA-376 §17.7.6 规定 Table 样式属性 "always applied" 除非被表格实例覆盖）。所以只要模板的 Table 样式 `tblPr` 里有 `<w:jc w:val="center"/>`，所有表格自动居中。
解决：在 format.txt 中写 `表格：居中`，`src/md_to_word/template/generator.py` 会在 Table 样式的 tblPr 中插入 jc 元素。

### 2.12 OOXML schema 顺序要求（jc 必须在 tblBorders 之前）

症状：Table 样式 tblPr 中有 jc 元素，但表格仍左对齐，Word 忽略了 jc。
原因：`jc` 元素必须在 `tblBorders` **之前**（OOXML schema 顺序：`tblStyle → tblW → jc → tblInd → tblBorders → tblLayout → tblLook`）。如果 jc 在 tblBorders 之后，Word 会忽略 jc。
解决：`src/md_to_word/template/generator.py` 按 OOXML schema 顺序插入（`ensure_ordered_child(tbl_pr, 'jc', _TBLPR_ORDER)`，`jc` 排在 `tblBorders` 之前）——不是 append/insert(0)：`w:tblPr` 的顺序错了 Word 会整段忽略。

### 2.13 First Paragraph 必填原理

症状：format.txt 只定义了 `正文 Body Text`，未定义 `首段 First Paragraph`，章节首段格式错误（无缩进或缩进错误）。
原因：章节首段落 `First Paragraph` 样式（不是 `Body Text`）。只定义 `Body Text` 而没定义 `First Paragraph` 时，首段会继承底模默认。
解决：format.txt 必须显式定义 `首段` 样式，通常 `首行缩进0字符`（APA 标准章节首段不缩进），与正文（`首行缩进2字符`）区分。src/md_to_word/template/generator.py 将 First Paragraph 列为必填样式之一（必填样式清单见 `REQUIRED_STYLES`，会随需求演进）。

### 2.14 间距清零原理（段前段后显式写 0）

症状：format.txt 写 `行距2倍` 但未写段前段后，导出后正文段落之间仍有额外间距，"双倍行距贯穿全文"未实现。
原因：底模里大多数样式自带段前/段后间距（如 Body Text 默认段前段后各 9pt）。仅设置行距不清零段间距，最终间距 = 双倍行距 + 段前 9pt + 段后 9pt。
解决：在 format.txt 中显式写 `段前0磅 段后0磅`（必须显式写 `0` 才能覆盖默认值）。src/md_to_word/template/generator.py 将段前段后列为必填字段。

### 2.15 LaTeX 分页符对 docx 无效

症状：MD 中用 `\newpage` 分页，导出的 docx 中不生效，段落连在一起。
原因：`\newpage` 是 LaTeX 命令，写出器不认它。
解决：改用 `{{< pagebreak >}}`（`src/md_to_word/validator/check.py` 会拦下 LaTeX 那几个写法
并给出这一句）。它在 docx 下产出 `<w:br w:type="page"/>`，与手写 raw openxml 块等效，
但不必写 XML。不生效时再在导出的 Word 文档中手动插入分页符。

### 2.16 参考文献不生成

症状：导出的 docx 中没有参考文献列表。
原因：YAML 没写 `bibliography:`，或正文引的 key 不在 `.bib` 里。
解决：两种都在导前预检拦下并给出行号；按报错补 `bibliography:`（路径相对稿件目录）或改 key。

### 2.17 样式映射不上

症状：导出的 docx 中某些段落格式不对（如关键词没有 Keywords 样式）。
原因：模板里没有这个样式（常见：要求文件漏写，或样式 ID 写错）。
解决：检查 `pure_modern_base.docx` 或通过 `create_pure_modern_base.py` 核对注册的标准样式名和 styleId，再用 `python-docx` 对比目标模板确认。

### 2.18 图片无法显示

症状：导出的 docx 中图片缺失（空白框或红叉），导出过程不报错。
原因：`![](path)` 中的路径不对，文件找不到。
解决：
1. 路径**相对稿件所在目录**解析（绝对路径也支持）。稿子放在哪里，图片就相对哪里写，与从哪个目录调用命令无关；
2. 图片文件不存在、路径含未转义空格时，预检会在导出前拦下，不会静默丢图。

### 2.19 代码块内 `:::` 包裹误检测

症状：预检把代码块内部的 `%% 样式名` 当成真的样式行来校验。
原因：脚本未跟踪代码块围栏状态，将代码块内的示例包裹误认为正文包裹。
`src/md_to_word/validator/check.py` 已跟踪代码块围栏状态，代码块内部出现的 `%% 样式名` 不会被误检测。

### 2.20 含目录的文档每次打开都弹「是否更新这些域」

**不是故障，是有意保留的行为**。目录域带 `w:dirty="true"`（`src/md_to_word/preprocessor/markers.py` 写入），
Word 见到脏域就询问一次，点「是」当场把页码算好。

这个提示**不会因为保存过就消失**（域可能引用外部文件，Word 出于安全不记住选择），
所以每次打开都会问。

去掉 `dirty` 就不再弹窗，代价是目录只剩占位文字「（打开文档后目录会自动生成）」，
必须手动 `Ctrl+A` → `F9` 才有内容。两害相权，保留弹窗。

### 2.21 读参考 .docx 为什么不能直接用 python-docx

`src/md_to_word/template/extractor.py` 走纯 XML，是因为这些格式在 python-docx 的 API 层够不着：

| 格式 | 真实位置 | API 读成什么 |
|:--|:--|:--|
| 中文字体 | `w:rFonts/@w:eastAsia` | `font.name` 只有西文槽 |
| 首行缩进 2 字符 | `w:ind/@w:firstLineChars` | `None` |
| 行距固定值 / 最小值 | `w:spacing/@lineRule` | 两者都是 Length，分不开 |
| 段落下边框、页码格式、表格边框、校对语言 | 各自的 XML 节点 | 没有 API |

### 2.22 图号为什么不支持 `{#fig-xxx}` 自动编号

本技能的交叉引用只覆盖公式（`{#eq-x}` + `@eq-x`）。图与表没有自动编号：图号手写在
题注里（`%% 图片题注 图 1 …`），表号手写在表题里。这样题注文字与正文里写的「如图 1 所示」
永远是同一个人写的，不会出现编号对不上。

### 2.23 目录条目样式必须声明成 Word 的**内置**样式

Word 更新目录域时按自己的内置定义重建条目样式，自建样式（`customStyle="1"`、大写 `TOC 1`）上写的
字体、字号、加粗、行距全部被覆盖。生成器（`template/generator.py::_ensure_builtin_toc_style`）
因此去掉 `customStyle`，`styleId` 用 `TOC1/2/3`、`w:name` 用小写 `toc 1/2/3`；
`tests/test_template_toc.py` 断言这三条是内置形态。

---

## 3. 分发形态：一份实现，两个入口

| | pip 包 | 本仓库 |
|:--|:--|:--|
| 拿到什么 | `pip install md-to-word-docx` | 整个仓库，`src/` 就在里面 |
| 入口 | `md-to-word` 命令 | `SKILL.md` / `scripts/export.sh` |
| 事实从哪来 | 包内手册（`--contract` 给路径） | 同一份手册 |
| 更新 | `pip install -U md-to-word-docx` | `git pull` |

**代码只有一份，入口可以有几个**：`scripts/export.sh` 优先用自己所在目录的 `src/`，克隆后跑的就是
所见版本；版本号、词表、门禁判据只留在包里（`manual.md` 随 wheel 走），技能文件只写"按什么顺序做"。
冻结面只有命令与开关、退出码 `0/1/2/3`、`--json` 键名、稿件契约与要求文件词法；消息措辞与包内布局
不冻结——这解释了 `--json` 为什么必须存在：Agent 读键，不读会随语种变的中文。新入口都只是同一实现
的薄壳（命令行、`export`、技能目录、将来的 NPM 包）；要求改写实现的能力应该进包，不进壳。

## 4. 为什么是 AI 原生

使用者是 agent，不是人。判据因此不是「人能否操作」，而是「agent 仅凭一份文档能否把事做完」。下面四条
由这个判据推出，它们解释了这个仓库里的多数取舍。

**文档先于参数。** `--help` 只能罗列开关，表达不了「先做什么、读不懂去哪查、报错怎么改」。所以入口是
一份讲顺序的文档（`SKILL.md`），细节留在随包发布的手册里，由 `--contract` 给出路径。两者同版本，
升级引擎不需要同步技能文件。

**确定性优于宽容。** 一种写法只接受一种拼法，写错即报错并给出行号；不做「猜一个最接近的样式名」这类
容错。理由与 agent 是否可靠无关，而在错误形式的差别：人会卡住，agent 会产出**看起来正常**的产物。
容错会把这处错误变成静默结果，而报错能被立即改正——错误信息因此是交互的一部分，不是失败的证据。

**可机读优先。** 退出码固定为 `0/1/2/3`，`--json` 的键名固定，消息措辞随稿件语种变化。程序读键，
不读措辞；技能文件之所以能长期不改，靠的就是这一层。

**不为不存在的人工操作做优化。** 输入是一份格式要求文件，出错要按行号改稿；手工走一遍的成本高于在
Word 里直接调整。因此没有交互式向导与进阶提示，也没有为人工敲命令而设的别名。

结论：这是一个给 agent 使用的工具，与以自动化为主要使用方式的命令行工具同类；区别在于它的用法无法
由参数表表达，只能由文档表达。
