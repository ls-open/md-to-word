# md-to-word

[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9+-brightgreen.svg)](https://www.python.org/)

[English](https://github.com/ls-open/md-to-word/blob/main/README_EN.md) | 简体中文

把 Markdown 编译成符合规范的 Word（`.docx`）：学位论文、期刊论文、技术报告、公文。

三条硬规矩：**排版与内容分离**——格式写成一份可进 Git 的 `requirements.txt`；
**导出确定性**——同一份源任何时候重跑，产物逐字节一致；**门禁不放行静默错误**——
导出前预检、导出后对账，不合规就中止并把行号指出来。

---

## 两种用法

引擎只有一份（`src/md_to_word/`），两种用法都是它的入口。

### 一、当成命令用

适合在终端里导出、接进 CI、或自己写脚本调。

```bash
pip install md-to-word-docx
md-to-word 稿件.md -o 输出.docx
```

```python
from md_to_word import export

result = export("稿件.md", "输出.docx")          # 默认预设按稿件语种选
if not result.ok:
    raise SystemExit("\n".join(result.errors))
```

- 更新：`pip install -U md-to-word-docx`（隔离环境用 `pipx install` / `pipx upgrade`）
- 包名比命令多一个 `-docx` 后缀：PyPI 上 `md-to-word` 与既有项目过于相似，被规则挡住；命令仍是 `md-to-word`
- 没装文档也能上手：`md-to-word --contract` 打印稿件契约、完整手册与内置预设的绝对路径

### 二、当成技能用

适合把活交给 AI：说清格式要求，剩下的由 Agent 做。

1. 克隆本仓库（或把整个目录放进技能目录）
2. 让 Agent 读仓库根目录的 `SKILL.md`
3. Agent 依次完成：整理稿件 → 写 `requirements.txt` → 导出 → 读门禁、按行号改稿

**不需要安装这个包**：`scripts/export.sh` 直接用仓库里的源码，`SKILL.md` 只写流程、
具体写法指向包内手册。只需装依赖：`pip install -r requirements.txt`。
更新方式是 `git pull`。

另有一个**自包含技能版**：`nature-skills` 仓库的
[`nature-paper2word`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2word)
——同一份源码加上它自己的技能文档，连仓库都不必克隆，供"完全不碰 pip"的用户使用。

| | 当成命令 | 当成技能 |
|:--|:--|:--|
| 谁动手 | 你自己敲命令 | Agent 代办 |
| 装什么 | `pip install md-to-word-docx` | 只装依赖，不装包 |
| 更新 | `pip install -U md-to-word-docx` | `git pull` |
| 读什么 | 本文件和 `--contract` | `SKILL.md`，细节查包内手册 |

---

## 30 秒示例

**你写的**（[`demo/00_quickstart/hello.md`](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.md)，节选）：

```markdown
---
crossref:
  tbl-prefix: "表"
---

%% 文档标题 我的第一份规范 Word 文档

# 引言

这是一份最小样例：一页纸、二十二行 Markdown。中文首行缩进两个字符、西文用
Times New Roman、行距 1.5 倍、各级标题黑体——这些都不用你在 Word 里点。

# 一个三线表

%% 表题 **表 1** 三套样例的端到端导出耗时

| 样例 | 篇幅 | 稳定耗时 | 主要演示的排版要素 |
|:------|:--|:---|:--------------|
| 最小样例（本文） | 1 页 | 0.15 s | 中西文字体、首行缩进、多级标题、三线表 |
| 技术白皮书样例 | 5 页 | 0.30 s | 全网格数据表、APA 引用、单线极简页眉 |
| 学位论文样例 | 8 页 | 0.43 s | 目录、分节页码、双线章名页眉、跨页表头 |
```

**你声明的**（[`demo/00_quickstart/requirements.txt`](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/requirements.txt)，节选）：

```text
纸张：A4
页边距：上2.54cm 下2.54cm 左2.54cm 右2.54cm
西文字体：Times New Roman

文档标题：黑体/Times New Roman 二号 加粗 不倾斜 居中 行距1.5倍 段前0磅 段后12磅 首行缩进0字符 无边框
一级标题：黑体/Times New Roman 三号 加粗 不倾斜 左对齐 行距1.5倍 段前12磅 段后6磅 首行缩进0字符 与下段同页
正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符
表格：居中 三线表 线宽上1.5磅 线宽底1.5磅 线宽表头下0.75磅 单元格垂直居中
表头：宋体/Times New Roman 五号 加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 跨页重复
```

**你跑的**：

```bash
md-to-word hello.md -r requirements.txt -o hello.docx
```

**你得到的**（约 0.2 秒，1 页）：

[![最小样例的输出](https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png)](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx)

中文首行缩进两个字符、西文 Times New Roman、三线表带表题表注——没有一步是在 Word 里点的。

---

## 能力与限制

| 支持 | 说明 |
|:--|:--|
| 页面与正文 | 纸张、页边距、装订线、文档网格、中西文字体、字号、行距、缩进、段距、对齐、颜色 |
| 标题与页眉页脚 | 六级标题、奇偶页/首页不同、页码格式与起始、分节、`{页码}` `{总页数}` `{样式标题}` 域 |
| 表格 | 三线表/全网格线/顶底线/无边框、线宽、表头跨页重复、单元格对齐与内边距、列宽比例 |
| 公式 | 原生 OMML、居中、编号靠右、按章编号、编号外观模板、`@eq-` 交叉引用 |
| 图与题注 | 图片宽度按版心钳制、题注与图同页绑定、图题在上一律由作者决定 |
| 文献 | `.bib` + CSL，内置 29 份常用样式（GB/T 7714、APA、Nature、IEEE、Vancouver 等） |
| 行内 | 加粗、斜体、删除线、下划线、上下标、行内代码、行内公式、链接、脚注 |
| 列表 | 有序、无序、嵌套三级、引用块内的列表 |
| 质量门禁 | 导前预检（契约、样式、引文）、导后防丢数、逐条样式对账 |

**不支持**（需在 Word 里补，或换一种写法）：

| 做不到 | 原因与替代 |
|:--|:--|
| 定制封面页（校徽、填空栏、签署页） | `%% 文档标题` 只生成一页标准标题区；封面在 Word 里并到首页，或用表格排一张简版 |
| 合并单元格、斜线表头、单元格底纹 | Markdown 表格只有规则二维网格；按网格导出后在 Word 里合并 |
| 多栏混排、文字环绕的浮动图 | 单栏是唯一版式，图片走独立居中图段；环绕在 Word 里改 |
| 带编号公式里求和/积分的上下限上下排 | Word 只有显示式才把上下限排到符号上下，带编号公式是行内公式；内容与符号正确，排法不同 |
| 行内文字颜色 | 颜色是样式属性，按样式行声明（`颜色#1F4E79`），不支持行内 `{color=…}` |

完整词表与逐条原理见包内 [`manual.md`](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual.md)
（中英各一份，随 wheel 发布）；实现取舍见
[`references/design.md`](https://github.com/ls-open/md-to-word/blob/main/references/design.md)。

---

## 环境

- **依赖**：`python-docx`、`lxml`、`PyYAML`、`latex2mathml`、`citeproc-py`，5 个纯 Python 包
- **导出不需要任何外部二进制**：没有 Pandoc，没有 Quarto，不调用 Word
- **`--pdf` 核对版**才用到本机 Word（仅 macOS；不可用时自动跳过，不影响 `.docx`）
- **中英双语**：运行时消息、门禁报错、使用手册各有两份，语言跟着**稿件语种**走——
  英文稿拿到英文报错与英文样式名举例，中文稿一字不变

---

## 手上有现成的模板？

学校、期刊或单位下发的 `.docx` 不必逐条抄成要求文件。用包内的读取器反推一份草稿：

```bash
md-to-word-template 学校模板.docx -o 论文_requirements.txt
```

读出页面尺寸、页边距、页眉页脚距边界、页码格式与起始、各样式的中西文字体与字号、加粗倾斜、
对齐、行距（区分倍数/固定值/最小值）、段前段后、缩进（含字符单位）、段落下边框、表格边框与
表头行、页眉页脚内容与域。**读不出的项列成待确认清单**，不假装读到了。

---

## 文档与仓库结构

| 路径 | 读它做什么 |
|:--|:--|
| [`SKILL.md`](https://github.com/ls-open/md-to-word/blob/main/SKILL.md) | 技能入口：代办流程、门禁判据、能力边界。事实一律指向手册 |
| [`src/md_to_word/resources/manual.md`](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual.md) | **使用手册**：稿件契约、完整词表、代办流程、门禁、能力边界、CSL 清单（中英各一份） |
| [`references/design.md`](https://github.com/ls-open/md-to-word/blob/main/references/design.md) | 设计原理与故障排查（导出结果不符合预期时先看它 §2） |
| [`demo/`](https://github.com/ls-open/md-to-word/blob/main/demo/) | 四份样例：最小样例、中文学位论文、技术白皮书、英文期刊投稿 |
| `scripts/` | 开发与验收工具（见 [`scripts/README.md`](https://github.com/ls-open/md-to-word/blob/main/scripts/README.md)） |
| `src/md_to_word/` | 实现本体：模型 → OOXML 写出器、样式生成、校验、对账 |
| `resources/` | Word 365 底模与 29 份规范化 CSL 样式 |
| `presets/` | 内置预设：`zh-academic.txt`、`en-nature.txt` |

发到用户机器上的只有 `src/`（含两份手册）、`presets/`、`resources/` 与包元数据（wheel 约 300 KB）；
`tests/`、`demo/`、`scripts/`、`references/`、`SKILL.md` 是仓库的验收面与技能入口，不进包。

**退出码**：`0` 完成；`1` 稿件、门禁或依赖问题；`3` `.docx` 已写出但 `--pdf` 未渲染。
`md-to-word --help` 列出全部选项，帮助语言跟随稿件语种；`--verbose` 打印逐个样式套用的明细。

---

## 相关技能

这一篇负责"编译成 Word"，上下游由同一套学术技能生态里的伙伴负责，按需转交，不必重造：

| 技能 | 负责什么 |
|:--|:--|
| [`nature-writing`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-writing) | 起草论文与章节论证（本技能的输入） |
| [`nature-polishing`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-polishing) | 英文润色与学术表达收束（本技能的输入） |
| [`nature-citation`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-citation) | 检索并导出本技能消费的 `.bib` 条目 |
| [`nature-ref-verifier`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-ref-verifier) | 投稿前交叉核验参考文献元数据 |
| [`nature-paper2ppt`](https://github.com/Yuan1z0825/nature-skills/tree/main/skills/nature-paper2ppt) | 同一篇论文转成组会/答辩用的 PPTX |

整组技能的入口见 [`nature-skills`](https://github.com/Yuan1z0825/nature-skills)（本技能被它列为第三方项目）。

---

## 实现了什么，借了什么

排版、编号、门禁、OOXML 写出都是本项目自己的代码。借用的只有两段有公开标准的部分：
LaTeX 解析（`latex2mathml`）与 CSL 引文渲染（`citeproc-py`）。判据是：**标准化的借，非标准化的自研**。

---

## 许可

代码为 [MIT](https://github.com/ls-open/md-to-word/blob/main/LICENSE)。`resources/csl/` 下的引文样式来自
[citation-style-language/styles](https://github.com/citation-style-language/styles)，按 CC BY-SA 3.0 使用；
`resources/pure_modern_base.docx` 由本项目生成，随 MIT 发布。
