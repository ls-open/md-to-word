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

### 1.2 主题属性工作原理与三重净化

在 Word 的 OOXML 规范中，**主题属性（Theme Attributes）优先级高于显式字体指定**：

```xml
<!-- 显式指定 → 会被主题覆盖 -->
<w:rFonts w:ascii="Times New Roman"/>

<!-- 主题引用 → 优先级更高，若残留会强制覆盖显式字体 -->
<w:rFonts w:asciiTheme="majorHAnsi"/>
```

为杜绝"设置了样式却不生效"的隐蔽 Bug，框架实行**三重纵深防御机制**：
1. **底模生成阶段（源头零污染）**：`create_pure_modern_base.py` 构建 `styles.xml` 时不写入任何 `asciiTheme`、`eastAsiaTheme`、`themeColor` 属性或非黑颜色；
2. **模板刷样阶段（过程净化）**：`generate_template.py` 保存时刻对 `styles.xml` 再次执行递归清理；
3. **最终导出阶段（末端兜底与防御）**：`fix_docx_equations.py` 在后处理公式的同时对最终 docx 再次执行样式净化。**此步的双重必要性**：
   - **第三方模板兜底**：用户直接使用期刊官方现有 `.docx` 模板（非脚本生成）时，也能自动拔除其中残留的主题属性；
   - **编译器隐式注入拦截**：Quarto 编译过程中若动态补齐某些特定样式节点，可能会自动带上系统默认主题标记，末端扫描可确保交到作者手中的 Word 终稿 100% 纯净。

### 1.3 学术公式居中与编号靠右对齐引擎

**靠右没有任何原生路径**：Pandoc 把编号塞在公式对象内部（`m:oMath` 末尾），OMML 没有
"对齐到右边"这个概念；Quarto 官方给的方案（`quarto-dev#2618`）也是自己写 filter。
本技能走渲染后重构——把带编号公式改成 **1 行 3 列无边框表格**：左右两列等宽（公式因此
能整页居中），右列放编号。

两个改代码前要知道的点：

- **列宽按编号实际宽度算**（`_eq_number_pct`），不能用固定百分比：固定 12% 时
  「（式 5-1）」这类中文编号会折成两行。
- **必须 `tblLayout type="fixed"`**：不写时 Word 走 autofit 重算列宽，把编号列压到约 40pt。

**编号来源与编号外观分属两层**：

| | 谁定 | 在哪 |
|:--|:--|:--|
| 数字本身 | Quarto crossref：`{#eq-x}` → `(1)`；配 `crossref: chapters: true` → 按章 `(5.1)` | 稿件 + YAML |
| 括号与分隔符 | `--eq-number-style`：`asis` 保持原生 / `cjk` 改写成 `（5-1）` | `format_eq_number()` |

### 1.4 工作流程图

```
格式要求.txt → parse_requirements() → 属性字典列表
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

Pandoc 的 docx writer 在确定图片显示宽度时，会从模板的 `sectPr` 中读取 `pgSz`（页面尺寸）和 `pgMar`（页边距），计算内容宽度 `envPrintWidth = pgSz.w - pgMar.left - pgMar.right`。**如果 pgSz 或 pgMar 任一缺失**，Pandoc 回退到默认值 420pt（≈14.817cm = 5,334,000 EMU）。

**`{width=15cm}` 被静默截断为 14.82cm 的根因**——Pandoc 默认 reference.docx 的 sectPr 不含 pgSz/pgMar。

`generate_template.py` 现在在保存模板前自动设置：
- `section.page_width` / `section.page_height`（写入 `<w:pgSz>`）
- `section.left_margin` 等（写入 `<w:pgMar>`，默认 2.54cm）
- 纸张尺寸由 requirements 文件的 `纸张：A4|Letter` 行设定（不写默认 A4，见 reference.md §1.5）

设置后，A4 页面内容宽度 = 21.0 - 2.54 - 2.54 = 15.92cm，`{width=15cm}` 可正确生效。

**装订线不在这条公式里，所以折进左边距写**。`w:gutter` 是"在装订侧再多留一段空白"，
Word 打印时会把它加到左边距之外，但 **pandoc 算 `envPrintWidth` 时不减它**，本技能算正文
宽度的两处（`_content_width_twips`、`_text_width_pt`）同样。后果实测：A4 + 2.54cm 边距 +
`装订线：1cm`，`{width=25cm}` 被钳成 15.90cm（本应 14.92cm），而文字起点已经右移 1cm——
于是在 Word 渲染的 PDF 上量出图片右缘在 **19.44cm**，越过 18.46cm 的右边距 **0.98cm**，
而导前预检、防丢数、导出后对账三道闸门全绿。

改法是把装订线**加进 `pgMar/@w:left`**（2.54 + 1 = 3.54cm），不写 `w:gutter`。单节、不开
镜像页边距时，两者在打印上等效，但折进去之后 pandoc 与本技能算的都是**真实版心**
（14.92cm），图片、公式网格表、点线制表位的落点一起跟着对——是"算得对"，不是"再补一刀"。
对账侧（`audit_export.py`）左边的期望值相应加上装订线。

### 1.6 原生图语法居中

原生图语法 `![caption](path){width=Xcm}`（alt 非空）时，Pandoc 将图片段落映射为 Captioned Figure 样式，模板中已设为居中。

### 1.7 缩进单位换算技术细节

`generate_template.py` 的缩进子句支持两种单位（单写法收敛，厘米单位已移除）：

| 单位 | OOXML 属性 | 换算关系 | 用途 |
|------|-----------|---------|------|
| 字符 | `firstLineChars` / `hangingChars` + `leftChars` | Word **根据段落字号自动计算**实际缩进量 | 中文正文首行缩进（`首行缩进2字符`）|
| 英寸 | `firstLine` / `hanging` | 1 inch = 72 pt | 英文首行缩进（`首行缩进0.5英寸`）与参考文献悬挂缩进（`悬挂缩进0.5英寸`）|

**字符单位的优势**：12pt 字号下 2 字符 = 24pt = 0.85cm；10.5pt 字号下 2 字符 = 21pt = 0.74cm。字号变化时缩进比例自动保持，比固定 pt 值更准确。

**关键数值对照**：
- 中文正文 `首行缩进2字符`（12pt 字号下 = 24pt = 0.85cm）
- 参考文献 `悬挂缩进0.5英寸`（= 36pt = 1.27cm，APA/MLA/Chicago/Vancouver 国际标准）
- **⚠️ 2 字符 ≠ 0.5 inch**：APA 标准的 0.5 inch = 36pt = 1.27cm，中文排版的 2 字符在 12pt 字号下 = 24pt = 0.85cm，两者是不同体系的数值，不能混用。英文论文用 `首行缩进0.5英寸`，中文论文用 `首行缩进2字符`。

### 1.8 参考文档被带走了什么（**改模板前必读**）

pandoc 只从参考文档拿走三类东西，其余一概忽略：

| 会被带走 | 不会被带走 |
|:--|:--|
| `word/styles.xml` 样式表 | 正文内容（`document.xml` 的段落一概忽略） |
| 文档属性：页面尺寸、页边距、**页眉、页脚** | 多节结构（见 §1.8.1） |
| `word/header*.xml`、`word/footer*.xml` 全部部件 | 域的计算结果（域由 Word 更新） |

> 官方手册：*"The contents of the reference docx are ignored, but its stylesheets and
> document properties (including margins, page size, header, and footer) are used."*

所以**页眉 / 页脚 / 页码是模板能力，不是导出后手工补的活**——`reference.md §1.4` 把它列进
「完全支持」的理由就在这里。

#### 1.8.1 参考模板只能单节，多节由标记在渲染层插入

**pandoc 取参考文档的第一个 `sectPr`，只用它的页眉页脚与页面几何。**

实测：两节模板导出后只剩节 0 的那个 `sectPr`。

- 单节内能做的全都能做：奇偶页不同页眉页脚（`evenAndOddHeaders` + `default`/`even`
  两个 `headerReference`）、首页不同、起始页码与页码格式；
- **跨节切换页码格式**（前置罗马 → 正文阿拉伯）不在模板里做，改由正文的 `{{< section >}}`
  标记在渲染前展开成 OOXML 分节符（§1.8.2）：它整段继承参考模板正文节的页面几何与页脚
  引用，只改分节类型与页码格式——所以参考模板仍须是单节。

`generate_template.py` 生成后强制校验单节，多节直接报错——多节模板会让页眉页脚错位且无人察觉。

#### 1.8.2 分节与目录：为什么在 Markdown 里展开，而不是导出后改 docx

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

### 1.9 requirements.txt 是一门**封闭**的小语言

它是本技能唯一的用户界面，只有两级语法，两级各由**一张表**实现（都在 `generate_template.py`）：

| 层级 | 例子 | 表 |
|:--|:--|:--|
| **行级键** | `纸张：A4`、`页边距：上2.4cm …`、`页眉内容：{页码}` | `_LINE_KEYS`：键 → 消费者，值落到 spec 的某个字段 |
| **样式行子句** | `正文：宋体 小四 行距1.5倍 首行缩进2字符` | `_CLAUSE_TABLE`：按空格切词，最长优先整词消费 |

**规矩只有一条：认不出的东西一律报错**（行号 + 原词 + 应写形式）。没有"静默忽略"这第三种
结果——写上去等于没写、导出还全绿，是这类工具最贵的失败模式（§2.10 记的都是实例）。

**认得出来但没前提的，一样报错**。有一类词本身合法，只是离开了搭配就没有落点：`边框粗`
没有下边框时无处可落（实测产物里连 `w:pBdr` 都没有）、`跨页重复` 只对表头行有意义、
`页码：` 不配 `{页码}` 域就只是一行没人读的 `pgNumType`。这些词若只按词表放行，就绕过了
上面那条规矩——**"认得"不等于"生效"**，故另立一道前提校验（`_check_clause_preconditions`）。
判据是**能否在 XML 里指出它落在哪**：落不下的，就得有个前提。

**为什么封闭**：用法是 AI 读要求原文 → 转写成 requirements.txt → 解析器严格校验。"严格校验"
成立的前提就是词表封闭：转写要么整行被接受、要么当场报错。多收一个同义写法看着只是"宽容
一点"，实际是取消了对转写的唯一验证手段。

**增补一个写法 = 两处同步**：① `generate_template.py` 加一行（`_LINE_KEYS` 或 `_CLAUSE_TABLE`）；
② `reference.md §1.5` 加一行（唯一写法 + 示例 + 错误写法），保持代码词表与文档速查表一致。

**什么不该加**：能力边界见 `reference.md §1.4`。判据是——新写法若只是"再多一个段落/字符/
表格属性"就可以加；若要求一套新的 OOXML 部件或后处理阶段，先问"要求方真的明文写了吗"。
**解释要求，不猜测要求。**

---

### 1.10 导出的 docx 为什么字节可复现

**同一份稿件重复导出，产出的 `.docx` 应当字节一致**——否则 Git 里每次提交都拖着一堆
"内容没改却变了"的二进制 diff，与本技能「确定性交付」的调性相冲。实测原先有**两个**
时间戳在动，都要钉死：

| 来源 | 表现 | 处理 |
|:--|:--|:--|
| `docProps/core.xml` 的 `dcterms:created` / `dcterms:modified` | 就是 Word「属性」里显示的创建/修改时间 | 写死为 `1970-01-01T00:00:00Z` |
| zip 每个条目的时间戳 | `ZipFile.writestr(name, data)` 默认取当前时刻，改的是压缩包本身 | 统一写 `1980-01-01 00:00:00`（DOS 时间起点） |

两个值都一眼看得出是钉死的，不会与真实时间混淆。实现在 `fix_docx_equations.py` 的
`process_docx`：用显式的 `ZipInfo` 写入，并在写之前把 core.xml 的时间戳换掉。

> 只改这两处就够——实测两份产物逐部件比对，差异只出在 `docProps/core.xml`。

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

### 1.12 表格列宽为什么要在后处理里做

Markdown 没有表达表格列宽的语法（pandoc 对 pipe 表一律均分，实测连分隔行短横线的
长短都不看）。所以我们借**分隔行本来就有的短横线**当比例，由后处理兑现；作者不写就
完全不碰那张表。

两个必须一起做的动作：

- **写 `gridCol`**：pandoc 给的列宽与内容多少无关，短列空一大片、长列被挤到换行；
- **钉 `tblLayout=fixed`**：不钉的话 Word 存盘时会按自己的算法重算，写进去的列宽等于没设
  （与 §1.3 公式三列网格表同一个坑）。

**按位置配比例，对不上就一张都不调**：稿件里的表格与 docx 里的表格按顺序一一对应，
中间夹着的公式网格表与图片包装表要先排除。曾经边遍历边跳（单列表直接 `continue`），
结果它后面所有表错位一格——单列表也要占一个位置。

配套的导前拦截：表格各行列数对不上时 pandoc **不报错，直接把多出来的单元格连同内容
丢掉**（实测表头 3 列、分隔行 2 格 → 产物只剩两列）。这是丢内容不是排版问题，
`check_md.py` 会拦。

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
原因与解决见 §1.5——模板 sectPr 缺 `pgSz`/`pgMar` 时 Pandoc 回退到 420pt；用
`generate_template.py` 重新生成模板即可（它按 requirements 的 `纸张：` 行写入这两个元素）。

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
解决：`generate_template.py` 按 OOXML schema 顺序插入（`ensure_ordered_child(tbl_pr, 'jc', _TBLPR_ORDER)`，`jc` 排在 `tblBorders` 之前）——不是 append/insert(0)：`w:tblPr` 的顺序错了 Word 会整段忽略。

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

### 2.20 含目录的文档每次打开都弹「是否更新这些域」

**不是故障，是有意保留的行为**。目录域带 `w:dirty="true"`（`expand_markers.py` 写入），
Word 见到脏域就询问一次，点「是」当场把页码算好。

这个提示**不会因为保存过就消失**（域可能引用外部文件，Word 出于安全不记住选择），
所以每次打开都会问。

去掉 `dirty` 就不再弹窗，代价是目录只剩占位文字「（打开文档后目录会自动生成）」，
必须手动 `Ctrl+A` → `F9` 才有内容。两害相权，保留弹窗。

### 2.21 读参考 .docx 为什么不能直接用 python-docx

`read_reference_docx.py` 走纯 XML，是因为这些格式在 python-docx 的 API 层够不着：

| 格式 | 真实位置 | API 读成什么 |
|:--|:--|:--|
| 中文字体 | `w:rFonts/@w:eastAsia` | `font.name` 只有西文槽 |
| 首行缩进 2 字符 | `w:ind/@w:firstLineChars` | `None` |
| 行距固定值 / 最小值 | `w:spacing/@lineRule` | 两者都是 Length，分不开 |
| 段落下边框、页码格式、表格边框、校对语言 | 各自的 XML 节点 | 没有 API |

### 2.22 图片加了 `{#fig-xxx}` 为什么会被套上表格框线

Quarto 交叉引用要求「图 + 题注」保持同页，为此把它们放进一个**单格表格**；该表格走
`表格：` 那行声明的 `Table` 样式（实测 `w:tblStyle w:val="Table"`），于是图片上下被
套上三线表的框线（顶底线 1.5 磅）。图片段落同时失去 `CaptionedFigure`，不再居中。

本技能只支持公式的交叉引用；图号一律手写在题注文字里。
