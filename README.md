# md-to-word

[![Official Skill: Nature Skills](https://img.shields.io/badge/Official%20Skill-Nature%20Skills%20(51k+%E2%98%85)-d9381e?logo=github&logoColor=white)](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)

[English](https://github.com/ls-open/md-to-word/blob/main/README_EN.md) | **简体中文** | [在线演示站 (Playground)](https://ls-open.github.io/md-to-word/)

把 Markdown 确定性编译为出版级规范 Word（`.docx`）。专为学术期刊、技术报告、学位论文、公文打造，**也是面向 AI Agent 设计的确定性排版与出版交付底座**。

> 🌐 **零门槛免安装试玩**：[点击访问官方在线体验站 (Web Playground)](https://ls-open.github.io/md-to-word/)，实时编辑内容，在线验证公式、三线表、页眉与出版规范，秒级下载成品 `.docx`。

---

### 为什么需要 md-to-word？

大模型直接编写 `python-docx` 脚本极易产生格式漂移、表格断裂或样式幻觉；而通用工具（如 Pandoc）改动细节需深入修改复杂底模与后处理过滤器。

`md-to-word` 采用**声明式排版契约**与**带精确行号的双向质量门禁**：
- **逐字节一致**：同一份源文件在任何操作系统重编译，产物二进制完全一致；
- **自愈门禁**：格式没写全或语法错误，导出前精准指示行号并提供自愈指引，让 AI Agent 具备自主调试闭环能力；
- **出版级排版**：原生 OMML 矢量数学公式（双击可编辑、自动居中、编号靠右）、跨页自动重复表头三线表、双线/单线页眉、中西文字体分离。

---

## 核心使用认知

本项目**本质上有两种使用方法，3 个入口**。无论通过 Skill 还是 pip 安装，**本质上都是让 AI（Agent）先阅读排版规范与契约文档，再执行排版**：
- **通过 Skill 使用**：AI 会在检测到排版意图时，**自动在后台激活并使用**该技能；
- **通过 pip 使用**：由你**在对话中明确提醒 AI 先阅读规范再调用工具**。

---

## 怎么使用：两种方法，3 个入口

### 方法一：通过 Skill 技能使用（推荐 · AI 自主感知与调用）

#### 入口 1：在支持 Skill 规范的 Agent 中引入本仓库技能
适用于 Claude Code、Codex、Cursor、Windsurf、通用智能体等环境。

- **CLI 自动化挂载（推荐）**：
  ```bash
  npx skills add ls-open/md-to-word
  ```
  *(基于通用 Agent Skills 规范，自动识别本仓库根目录的 `SKILL.md` 并完成挂载)*

- **手动导入技能文件**：  
  将仓库根目录的 [`SKILL.md`](https://github.com/ls-open/md-to-word/blob/main/SKILL.md) 复制到你项目的 Agent 规则/技能目录中（如 `.claude/skills/` 或 `.cursor/rules/`）；或者在对话式 Agent 中直接把它的 Raw 链接提供给 AI：  
  `https://raw.githubusercontent.com/ls-open/md-to-word/main/SKILL.md`

- **日常使用（自然语言对齐）**：  
  配置完成后无需记忆任何命令参数，直接向 AI 提出排版需求即可，AI 会自主命中该技能并处理：
  > “*帮我把这篇论文草稿（paper.md）按照 IEEE 期刊格式排版为规范的 Word 文档。*”  
  > “*这是我们学校的学位论文格式要求（或附件中的模板.docx），帮我把稿件排版导出。*”

#### 入口 2：在 Nature Skills 生态中直接使用
本项目已作为官方独立技能 [`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word) 正式合并入 **Nature Skills（51k+ ★）** 官方生态中。

- **使用方式**：  
  在已安装 Nature Skills 的环境中**无需重复安装**，直接输入指令呼叫 `$nature-paper2word`，或在全流程论文写作完成后的最终交付阶段直接让 AI 编译出符合规范的 Word 文件。

---

### 方法二：通过 pip 安装使用（由你主动驱动本地 Agent）

#### 入口 3：本地 pip 安装 + 提示词唤起 Agent
如果你的环境倾向于直接通过 Python 命令行调用，或者是在本地配合 Claude Code / Cursor Agent / 终端 AI 助手执行：

1. **安装底层编译器**：
   ```bash
   pip install md-to-word-docx
   ```
   *（注：因 PyPI 命名规则限制，安装包名为 `md-to-word-docx`，安装后的命令行命令依然为 `md-to-word`。隔离环境可用 `pipx install md-to-word-docx`，更新用 `pip install -U md-to-word-docx`）*

2. **核心原理与怎么让 AI 使用**：  
   安装包内自带了一份与 `SKILL.md` 完全一致的完整规范指南。当你在终端或编辑器中使用 Agent 时，**核心是告诉 AI 先读指南**：

   > 💬 **发给 Agent 的标准提示词（Prompt 模板，复制即可用）：**  
   > “我已经安装了 `md-to-word-docx` 命令行工具。请你先运行 `md-to-word --guide` 阅读其排版规范与契约要求，然后帮我把当前目录下的稿件按规范导出为 Word（如果手头有目标 Word 模板，请先用 `md-to-word-template` 反推格式要求）。”

3. **AI 在后台的自主执行闭环**：
   - **读规范**：运行 `md-to-word --guide`（或 `--contract`），获知样式的封闭词表与 Markdown 书写契约；
   - **定格式**：根据需求生成或调整 `format.txt`，或从已有模板反推；
   - **调编译**：运行 `md-to-word 稿件.md -r format.txt -o 稿件.docx --json`；
   - **读门禁自愈**：如遇导前预检拦截，根据返回的精确行号自动修改稿件并重跑，直至返回码为 `0` 交付最终文档。

---

### 面向开发者与自动化脚本（可选）

如果你需要在 CI/CD 流程或 Python 程序中直接调用：

- **命令行直接运行**：
  ```bash
  # 最小样例初始化
  md-to-word init
  # 指定格式文件导出
  md-to-word 稿件.md -r format.txt -o 稿件.docx
  ```
- **作为 Python 库调用**：
  ```python
  from md_to_word import export

  result = export("稿件.md", "稿件.docx", rules="format.txt")
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

反推器会自动解析页面尺寸、页边距、页眉页脚距边界、页码样式与起始、各级样式的中西文字体、字号、加粗倾斜、行距（倍数/固定值）、段前段后、字符缩进、表格边框及表头行。**未能完全判定的项会自动生成待确认清单**，严谨可靠。

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

本项目专注下游的高质量确定性排版与出版交付，前期的文献调研、开题构思与论文写作推荐配合以下学术 Agent 框架：

- **[Nature Skills](https://github.com/Yuan1z0825/nature-skills)（51k+ ★）**：顶流科研论文全流程写作 Agent 技能集。本项目已作为官方内置独立技能 [`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word) 正式合并入官方仓库，负责该生态终稿阶段的“规范 Word 编译交付”。在 Nature Skills 环境中可直接唤起 `$nature-paper2word`。
- **[Academic Research Skills](https://github.com/Imbad0202/academic-research-skills)（51k+ ★）**：五阶段学术研究全流程框架。本项目被收录在官方第三方项目列表中，在 Stage 5（FINALIZE）产出 Markdown 草稿与参考文献后，直接承接出规范 `.docx`。
- **[中文独立开发者](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)**：收录于程序员专刊精选独立项目。

---

## 许可

代码开源遵循 [MIT License](https://github.com/ls-open/md-to-word/blob/main/LICENSE)。  
内置引文样式来自 [citation-style-language/styles](https://github.com/citation-style-language/styles)（CC BY-SA 3.0）；内置底模由本项目生成，随 MIT 发布。
