# md-to-word

[![Skill: Nature Skills](https://img.shields.io/badge/Skill-Nature%20Skills-d9381e?logo=github&logoColor=white)](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word)
[![Listed in Academic Research Skills](https://img.shields.io/badge/Listed-Academic%20Research%20Skills-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)

[English](https://github.com/ls-open/md-to-word/blob/main/README_EN.md) | **简体中文** | [在线演示站 (Playground)](https://ls-open.github.io/md-to-word/)

把 Markdown 确定性编译为规范 Word（`.docx`）。专为学位论文、技术报告、学术论文、公文打造，**也是面向 AI Agent 设计的确定性 Word 格式编译底座**。

> 🌐 **零门槛免安装试玩**：[点击访问官方在线体验站 (Web Playground)](https://ls-open.github.io/md-to-word/)，按表单填入内容，用三套内置模板实时预览公式、三线表与页眉，秒级下载成品 `.docx`。

---

### 为什么需要 md-to-word？

大模型直接编写 `python-docx` 脚本极易产生格式漂移、表格断裂或样式幻觉；而通用工具（如 Pandoc）改动细节需深入修改复杂底模与后处理过滤器。

`md-to-word` 采用**声明式排版契约**与**带精确行号的双向质量门禁**：
- **逐字节一致**：同一份源文件重复编译，产物二进制完全一致——打包时间戳、权限与条目顺序均已固定；
- **自愈门禁**：格式没写全或语法错误，导出前精准指示行号并提供自愈指引，让 AI Agent 具备自主调试闭环能力；
- **规范排版**：原生 OMML 矢量数学公式（双击可编辑、自动居中、编号靠右）、跨页自动重复表头三线表、双线/单线页眉、中西文字体分离。
- **用户格式优先**：有模板或书面要求时，按其 `format.txt` 编译；没有具体要求时可先用内置预设看效果，正式交付仍以模板或规范为准。

---

## 架构认知：自包含核心与多形态接入

> 💡 **核心设计哲学**：
> 本项目的底层是纯净、确定性的 Python 编译引擎（`md-to-word-docx`），内置了完整的排版契约规范与自检逻辑。为了解决“排版契约一旦升级、外部 Prompt/技能文档就失效不同步”的痛点，项目采用**规范内置自包含**设计（运行 `md-to-word --guide` 即可输出与最新代码 100% 同步的完整指南）。
> 无论你是想在网页上免安装试玩、在桌面端挂载为原生 AI 工具（MCP）、在智能体中作为技能（Skill）调用，还是在终端执行 CLI 批处理，底层运行的都是同一套严格对账的编译逻辑。

### 选型对比与使用全景

| 使用形态 | 适用客户端 / 场景 | 本地环境依赖 | 一键接入 / 启动方式 | 核心特点与适用建议 |
| :--- | :--- | :---: | :--- | :--- |
| **🌐 Web 在线体验站** | 浏览器直接试玩、零门槛体验、快速排版预览 | ❌ 无需安装任何环境 | 直接访问 [官方体验站](https://ls-open.github.io/md-to-word/) | **免配置试玩**：按表单填入标题/摘要/正文/公式/表格，用三套内置模板分屏预览 PDF、下载 `.docx`。 |
| **🤖 MCP 原生外设** *(格式确定后最快)* | **Claude Desktop**、**Cursor**、**Windsurf** 等支持 MCP 协议的 AI 桌面端 | ❌ 无需手动配 Python（`uvx` 自动拉取） | 在客户端配置中声明 `uvx` 命令（见下文） | **最原生**：已经拿到 `format.txt` 后，让 AI 直接编译；环境全自动隔离。 |
| **🧠 Agent Skill 技能** *(推荐)* | **Claude Code**、**终端 Agent**、**Nature Skills** | ⚠️ 依赖宿主 Agent 执行环境 | `npx skills add ls-open/md-to-word` 或呼叫 `$nature-paper2word` | **最智能**：AI 先读规范、按用户模板/要求定格式，遇门禁读行号自愈重跑。 |
| **💻 本地 CLI 与 SDK** | 终端命令行批处理、CI/CD 自动化流水线、Python 脚本开发 | 需 Python >= 3.10 | `pip install md-to-word-docx` 然后运行 `md-to-word 稿.md` | **最确定**：纯本地编译，不依赖任何大模型 API，支持模板样式反推与逐字节回归测试。 |

---

### 快速上手指南

#### 1. 🤖 作为 MCP 原生外设使用（Claude Desktop / Cursor）

MCP（Model Context Protocol）是 Anthropic 开源的标准模型上下文协议。AI 客户端不需要运行在命令行中，直接通过标准协议将 `md-to-word` 当作专属排版外设调用。

**为什么无需手动安装？**  
推荐使用现代 Python 工具链 `uvx`，它会在首次调用时**自动从 PyPI 下载依赖并在隔离环境中执行**，无需污染全局系统。

在你的 `claude_desktop_config.json`（或 Cursor MCP 配置）中添加：

```json
{
  "mcpServers": {
    "md-to-word": {
      "command": "uvx",
      "args": ["--from", "md-to-word-docx[mcp]", "md-to-word-mcp"]
    }
  }
}
```

*（注：若习惯本地全局 Python 环境，亦可运行 `pip install "md-to-word-docx[mcp]"`，并将 `command` 设为 `python3`，`args` 设为 `["-m", "md_to_word.mcp"]`）*

**AI 自动获得的原生能力**：
- `compile_markdown`：将输入的 Markdown（文本或文件路径）直接编译为规范 `.docx`（并可按需转为 PDF）；
- `validate_manuscript`：在生成前执行预检，自动检测未闭合的数学公式、缺线的表格或格式错误；
- `get_guide` / `get_manual`：读取包内的工作流指南与完整词表；
- `extract_format_from_docx`：从学校/期刊模板反推 `format.txt` 草稿；
- `list_presets`：按需选择中文核心期刊、白皮书或 Nature 顶级英文规范；
- `inspect_preset`：透明查阅任意预设的完整字体、行距与排版规则（`format.txt`）。

**使用顺序**：先让 Agent 调用 `get_guide`，若有具体模板或格式要求则提取或编写 `format.txt`，无特殊要求则直接选用内置预设。可以直接给 Agent 这条提示：

> 先运行 `md-to-word --guide` 读完整工作流；如果有目标模板或规范要求，先用 `md-to-word-template` 反推出 `format.txt` 再编译；若无特殊要求，直接使用内置预设快速出稿。

#### 2. 🧠 作为 Agent Skill 技能使用（Claude Code / Nature 生态）

如果你在命令行或具备 Shell 权限的 Agent（如 Claude Code、OpenCode）中使用：

- **自动化一键挂载**：
  ```bash
  npx skills add ls-open/md-to-word
  ```
- **Nature Skills 生态内置**：
  本项目的技能版已合并入 [Nature Skills](https://github.com/Yuan1z0825/nature-skills)，已安装环境直接输入 `$nature-paper2word` 即可唤起。
- **手动导入**：
  将仓库中的 [`SKILL.md`](https://github.com/ls-open/md-to-word/blob/main/SKILL.md) 复制到你项目的技能目录（如 `.claude/skills/`）即可。

#### 3. 💻 本地 pip 安装与命令行直接运行

如果你需要脱离大模型直接作为本地生产力工具使用：

```bash
# 安装核心编译器
pip install md-to-word-docx

# 初始化示例项目（写入 format.txt 与一篇可直接导出的样例）
md-to-word init

# 查看完整工作流与格式词表
md-to-word --guide

# 显式指定格式文件导出
md-to-word 论文.md -f format.txt -o 论文.docx

# 没有格式文件时，用内置预设先看效果（仅预览）
md-to-word 论文.md --preset zh-academic -o 预览.docx
```

- **作为 Python 库调用**：
  ```python
  from md_to_word import export

  result = export("稿件.md", "稿件.docx", format="format.txt")
  if not result.ok:
      raise SystemExit("\n".join(result.errors))
  ```

---

## 样例展示

以下样例均由真实编译流程生成，页图由生成的 PDF 真实渲染，非效果图：

| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png" width="240"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/01_chinese_thesis/thesis_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/01_chinese_thesis/page-1.png" width="240"></a> |
|:--:|:--:|
| **最小起步样例** · 一页纸，从稿件到成品的最短路径 | **中文学位论文** · 目录域、分节页码、按章编号、双线章名页眉 |
| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/02_modern_report/report_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/02_modern_report/page-1.png" width="240"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/paper.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/03_english_paper/page-1.png" width="240"></a> |
| **现代技术白皮书** · 全网格表、引用块、彩色一级标题 | **英文期刊投稿** · APA 作者-年份制、`Equation 1` 交叉引用 |

---

## 手上有现成的 Word 模板？

学校、期刊或单位下发的 `.docx` 模板不必逐条手工抄写。使用内置的模板反推器：

```bash
md-to-word-template 学校模板.docx -o format.txt
```

反推器会自动解析页面尺寸、页边距、页眉页脚距边界、页码样式与起始、各级样式的中西文字体、字号、加粗倾斜、行距（倍数/固定值）、段前段后、字符缩进、表格边框及表头行。**未能完全判定的项会自动生成待确认清单**。

---

## 排版能力一览

- **页面与正文**：纸张、页边距、装订线、文档网格、中西文字体、字号、行距、缩进、段距、对齐、颜色
- **标题与页眉页脚**：六级标题、奇偶页与首页不同、分节、页码格式与起始、`{页码}` `{总页数}` `{样式标题}` 域
- **表格**：三线表、全网格线、顶底线、无边框，线宽、跨页重复表头、单元格垂直水平对齐、列宽比例
- **公式**：原生 OMML 公式对象（Word 内可直接双击二次编辑，绝非位图或文本伪造），居中、编号靠右、按章编号、`@eq-` 交叉引用
- **图与题注**：图片宽度按版心智能钳制，题注与图同页绑定防掉页，直接支持矢量 PDF 插图（导出时自动 300 dpi 高清栅格化）
- **文献与引用**：`.bib` + CSL 样式体系，内置 29 份常用期刊与国家标准样式（GB/T 7714、APA、Nature、IEEE 等），支持自定义 CSL
- **行内样式**：加粗、斜体、删除线、下划线、上下标、行内代码、行内公式、超链接、脚注
- **结构标记**：目录域 `{{< toc >}}`、分节换页码 `{{< section >}}`、分页 `{{< pagebreak >}}`
- **质量门禁**：导前预检（契约、样式、引文合法性）、导后防丢数核对、逐条样式对账
- **纯 Python 本地导出**：整条链路在 Python 进程内完成，无需额外安装或启动 Office/WPS/Pandoc

完整功能边界与词表详见[使用手册](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual.md)。

---

## 常用写法契约速查

| 要写的内容 | 契约写法 | 说明 |
|:--|:--|:--|
| **章节标题** | `# 引言`、`## 2.1 方法` | 一个 `#` 代表一级，不跳级 |
| **指定段落样式** | `%% 摘要 本文提出……` | 行首 `%% 样式名`，一行即一段，无闭合符号 |
| **段内软换行** | 行尾加 `\` 或两个空格 | 地址、诗句、长标题；不加标记则各自独立成段 |
| **带编号公式** | `$$E=mc^2$$ {#eq-mass}` | 单独成行，正文用 `@eq-mass` 交叉引用 |
| **参考文献引用** | 正文写 `[@smith2024]` | YAML 中声明 `bibliography: refs.bib` |
| **插图与题注** | `![](figures/arch.png){width=13cm}`<br>`%% 图片题注 图 1 系统架构` | 图片下一行紧跟题注，自动绑定同页不分离 |
| **表格与题注** | 表前：`%% 表题 **表 1** 耗时对比`<br>`\| A \| B \|`<br>表后：`%% 表注 注：……` | 标准 Markdown 表格，表头上顶线、表尾下底线 |
| **自动目录** | 单独一行 `{{< toc >}}` | 导出 Word 内生原生目录域 |
| **分节与换页码** | `{{< section page_number=lowerRoman start=1 >}}` | 结束上一节，开启新分节并重设页码 |
| **强制分页** | 单独一行 `{{< pagebreak >}}` | 插入分页符 |

---

## 与其他方案的区别

| 维度 | Pandoc / Quarto | 传统 Markdown→Word 脚本库 | 本项目 (md-to-word) |
|:--|:--|:--|:--|
| **排版规则维护** | 命令行复杂参数 + Word 底模，改细节需动内部 XML | 硬编码在 Python 代码中，或只有粗粒度预设 | 一份纯文本 `format.txt`，随稿件进 Git，所见即声明 |
| **公式排版** | 需额外后处理脚本实现靠右编号 | 很多转为图片或字面代码 | 原生 OMML 数学公式，自动居中，编号严格靠右 |
| **分节与页眉页脚** | 必须手工预先修改底模并插域 | 普遍不支持复杂分节 | 标记声明（如目录罗马数字、正文阿拉伯数字分节） |
| **错误诊断与自愈** | 静默走样或布局断裂 | 直接抛异常崩溃 | 严格导前预检并精确指示**第几行**，方便 Agent 闭环修复 |
| **大模型协作友好度**| 难以通过 Prompt 控制细节 | 每次生成脚本都不同、充满幻觉 | **为 Agent 量身打造**：读规范 -> 调工具 -> 读报错自愈 |

---

## 协同生态与收录

本项目专注下游的高质量确定性排版与 Word 交付，前期的文献调研、开题构思与论文写作推荐配合以下学术 Agent 框架：

- **[Nature Skills](https://github.com/Yuan1z0825/nature-skills)**：科研论文全流程写作 Agent 技能集。本项目的技能版已合并入该仓库，负责终稿阶段的规范 Word 编译交付，在 Nature Skills 环境中可直接唤起 `$nature-paper2word`。
- **[Academic Research Skills](https://github.com/Imbad0202/academic-research-skills)**：五阶段学术研究全流程框架。本项目被收录在其第三方项目列表中，在 Stage 5（FINALIZE）产出 Markdown 草稿与参考文献后，直接承接出规范 `.docx`。
- **[中文独立开发者](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)**：收录于程序员专刊精选独立项目。

---

## 许可

代码开源遵循 [MIT License](https://github.com/ls-open/md-to-word/blob/main/LICENSE)。  
内置引文样式来自 [citation-style-language/styles](https://github.com/citation-style-language/styles)（CC BY-SA 3.0）；内置底模由本项目生成，随 MIT 发布。
