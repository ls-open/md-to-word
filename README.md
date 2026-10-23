# md-to-word

[![Featured in Chinese Indie Dev](https://img.shields.io/badge/Featured%20in-Chinese%20Indie%20Dev-238636?logo=github&logoColor=white)](https://github.com/1c7/chinese-independent-developer/blob/master/.github/pages/README-Programmer-Edition.md)
[![Ecosystem: Academic Research Skills](https://img.shields.io/badge/Ecosystem-Academic%20Research%20Skills%20(51k+%E2%98%85)-0969da?logo=github&logoColor=white)](https://github.com/Imbad0202/academic-research-skills/blob/main/THIRD_PARTY.md#listed-projects)
[![Release](https://img.shields.io/github/v/release/ls-open/md-to-word)](https://github.com/ls-open/md-to-word/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/ls-open/md-to-word/blob/main/LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://www.python.org/)

[English](https://github.com/ls-open/md-to-word/blob/main/README_EN.md) | 简体中文

把 Markdown 编译成符合规范的 Word（`.docx`）。学位论文、期刊投稿、技术报告、公文、说明书都用
同一套写法——差别只在那份 `format.txt`：排版规则写在稿件旁边，跟着稿件一起进 Git；同一份源任何
时候重跑，产物逐字节一致；格式没写全、样式名写错、引文缺文献库，导出前就中止并指出第几行。

[![最小样例的产物](https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png)](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx)

*上图由 [`demo/00_quickstart`](https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/) 导出：
中文首行缩进两字符、西文 Times New Roman、三线表带表题表注——没有一步是在 Word 里点的。*

---

## 安装

```bash
pip install md-to-word-docx
```

包名比命令多一个 `-docx` 后缀：PyPI 上 `md-to-word` 与既有项目过于相似，被命名规则挡住；命令仍是
`md-to-word`。隔离环境用 `pipx install md-to-word-docx`，更新用 `pip install -U md-to-word-docx`。

第一次用先过一遍 `md-to-word --guide`：流程、门禁判据、能力边界都在里面。它就是仓库根
`SKILL.md` 的正文——用技能的人读 `SKILL.md`，只装包的人读这份，内容相同，只是入口不同。

## 30 秒

**先运行一条命令**：`md-to-word init` 在当前目录生成 `format.txt` 与 `hello.md`，后者可直接导出——
先看到成品，再改内容与格式。

```bash
md-to-word init
md-to-word hello.md -o hello.docx
```

**写稿件**——正文是普通 Markdown，只有三处约定：以 `%%` 开头的行指定这一段的样式，`$$…$$ {#eq-x}`
是带编号的公式，`{{< toc >}}` 这类标记单独成行。

```markdown
%% 文档标题 我的第一份规范 Word 文档

# 引言

这是一份最小样例：中文首行缩进两个字符、西文用 Times New Roman、行距 1.5 倍，
这些都不用你在 Word 里点。

%% 表题 **表 1** 三套样例的端到端导出耗时

| 样例 | 篇幅 | 稳定耗时 |
|:------|:--|:---|
| 最小样例（本文） | 1 页 | 0.15 s |
| 学位论文样例 | 8 页 | 0.43 s |
```

**声明格式**——一行一种样式，字段写全就生效（节选：完整的一份还会声明各级标题、脚注、参考文献与页码）：

```text
纸张：A4
页边距：上2.54cm 下2.54cm 左2.54cm 右2.54cm
西文字体：Times New Roman

正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符
表格：居中 三线表 线宽上1.5磅 线宽底1.5磅 线宽表头下0.75磅 单元格垂直居中
表头：宋体/Times New Roman 五号 加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 跨页重复
```

**导出**：

```bash
md-to-word 稿件.md -r format.txt -o 稿件.docx
```

约 0.2 秒。不传 `-r` 时用内置预设，按稿件语种选：中文走 `zh-academic`，其他语言走 `en-nature`。

## 样例

四份样例都真导出、真在 Word 里开过；下面的页图直接由导出的 PDF 生成，不是效果图。

| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/00_quickstart/hello.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/00_quickstart/page-1.png" width="250"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/01_chinese_thesis/thesis_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/01_chinese_thesis/page-1.png" width="250"></a> |
|:--:|:--:|
| **最小样例** · 一页纸，从稿件到成品的最短路径 | **中文学位论文** · 目录域、分节页码、按章编号、双线章名页眉 |
| <a href="https://github.com/ls-open/md-to-word/blob/main/demo/02_modern_report/report_sample.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/02_modern_report/page-1.png" width="250"></a> | <a href="https://github.com/ls-open/md-to-word/blob/main/demo/03_english_paper/paper.docx"><img src="https://raw.githubusercontent.com/ls-open/md-to-word/main/demo/03_english_paper/page-1.png" width="250"></a> |
| **技术白皮书** · 全网格表、引用块、彩色一级标题 | **英文期刊投稿** · APA 作者-年份制、`Equation 1` 交叉引用 |

## 能做什么

- **页面与正文**：纸张、页边距、装订线、文档网格、中西文字体、字号、行距、缩进、段距、对齐、颜色
- **标题与页眉页脚**：六级标题、奇偶页与首页不同、分节、页码格式与起始、`{页码}` `{总页数}` `{样式标题}` 域
- **表格**：三线表、全网格线、顶底线、无边框，线宽、跨页重复表头、单元格对齐与内边距、列宽比例
- **公式**：原生 OMML 对象（在 Word 里可继续编辑，不是图片、不是字面文本），居中、编号靠右，按章编号，编号外观可声明，`@eq-` 交叉引用
- **图与题注**：图片宽度按版心钳制，题注与图同页绑定，图题在上一律由作者决定；图可以直接引用 PDF（导出时按 300 dpi 栅格化）
- **文献**：`.bib` + CSL，内置 29 份常用样式（GB/T 7714、APA、Nature、IEEE、Vancouver 等），也可指向自己的 CSL 文件
- **行内**：加粗、斜体、删除线、下划线、上下标、行内代码、行内公式、链接、脚注
- **列表**：有序、无序、三级嵌套、引用块内的列表
- **质量门禁**：导前预检（契约、样式、引文）、导后防丢数、逐条样式对账
- **纯 Python 导出**：整条链路在 Python 进程内完成，不启动任何外部程序

做不到什么、为什么，以及完整词表见[使用手册](https://github.com/ls-open/md-to-word/blob/main/src/md_to_word/resources/manual.md)——
`md-to-word --contract` 会打印它的路径（中英各一份）；实现取舍见
[`design.md`](https://github.com/ls-open/md-to-word/blob/main/references/design.md)。

## 常用写法

| 要写的内容 | 写法 |
|:--|:--|
| 章节标题 | `# 引言`、`## 2.1 方法`；一个 `#` 一级，不跳级 |
| 给某一段指定样式 | 行首写 `%% 摘要 本文提出……`（一行即一段，无闭合符号） |
| 同一段内换行 | 行尾加 `\` 或两个空格（地址、诗句、长标题）；不写标记就各自成段 |
| 带编号的公式 | `$$E=mc^2$$ {#eq-mass}`，正文用 `@eq-mass` 引用 |
| 参考文献 | YAML 里 `bibliography: refs.bib`，正文写 `[@smith2024]` |
| 图 | `![](figures/arch.png){width=13cm}`，下一行 `%% 图片题注 图 1 系统架构` |
| 表 | 表上方 `%% 表题 **表 1** ……`，表下 `%% 表注 注：……` |
| 目录 | 单独一行 `{{< toc >}}` |
| 分节、换页码 | 单独一行 `{{< section page_number=lowerRoman start=1 >}}` |
| 分页 | 单独一行 `{{< pagebreak >}}` |

## 与其他方案的区别

| | Pandoc / Quarto | 常见的 Markdown→Word 库 | 这里 |
|:--|:--|:--|:--|
| 排版规则写在哪 | 命令行参数 + Word 底模，改细节要动 XML | 代码里，或只有几档预设 | 一份 `format.txt`，随稿件进 Git |
| 公式编号靠右 | 需额外后处理 | 一般不做 | 默认；按章编号可声明 |
| 分节页码、章名页眉 | 要手工改底模并插域 | 不支持 | 一行标记 + 一行要求 |
| 出错时 | 多为静默走样 | 抛异常或静默 | 导前预检带行号，导后逐条对账 |

各家默认就能做到的（中西文字体分离、三线表、跨页表头、参考文献排版），这里同样支持；
上表只列拉开差距的项。

## 另外两个入口

**当作 Python 库**——需要接进自己的流程时：

```python
from md_to_word import export

result = export("稿件.md", "稿件.docx")
if not result.ok:
    raise SystemExit("\n".join(result.errors))
```

**当作 Agent 技能**——把活交给 AI 时，克隆本仓库，让 Agent 读根目录的 [`SKILL.md`](https://github.com/ls-open/md-to-word/blob/main/SKILL.md)，
它依次完成：整理稿件 → 写 `format.txt` → 导出 → 读门禁、按行号改稿。

**给脚本与 Agent**——加 `--json`，结果是一行 JSON：用了哪份格式要求、每条提醒、结尾的核对提示都在 `messages` 里，失败原因在 `errors` 里；进度日志与报错文字走 stderr：

```bash
md-to-word 稿件.md -o 稿件.docx --json
```

键名固定（`ok`、`returncode`、`input`、`output`、`pdf`、`lang`、`messages`、`errors`），不随版本变；
里面的句子跟着稿件语种走。读键，不读措辞。

## 环境

- **依赖**：`python-docx`、`lxml`、`PyYAML`、`latex2mathml`、`citeproc-py`、`pypdfium2` 六个包；`lxml` 与 `pypdfium2` 是带各平台二进制轮子的扩展，其余是纯 Python
- **导出不启动外部程序**：整条链路在 Python 进程内完成
- **`--pdf` 核对版**才用到本机 Word（仅 macOS；不可用时自动跳过，不影响 `.docx`）
- **中英双语**：运行时消息、门禁报错、使用手册各有两份，语言跟着**稿件语种**走——
  英文稿拿到英文报错与英文样式名举例，中文稿一字不变

## 手上有现成的模板？

学校、期刊或单位下发的 `.docx` 不必逐条抄成要求文件。用包内的读取器反推一份草稿：

```bash
md-to-word-template 学校模板.docx -o 论文_format.txt
```

读出页面尺寸、页边距、页眉页脚距边界、页码格式与起始、各样式的中西文字体与字号、加粗倾斜、
对齐、行距（区分倍数/固定值/最小值）、段前段后、缩进（含字符单位）、段落下边框、表格边框与
表头行、页眉页脚内容与域。**读不出的项列成待确认清单**，不假装读到了。

## 推荐上游生态

本项目专注下游的确定性排版与格式交付，写稿、找文献的部分推荐配合这两个学术 Agent 框架使用：

- [Academic Research Skills](https://github.com/Imbad0202/academic-research-skills)：五阶段学术研究与写作
  全流程框架。Stage 5（FINALIZE）产出 Markdown 草稿与参考文献后，可直接接到本工具出规范 `.docx`。
- [Nature Skills](https://github.com/Yuan1z0825/nature-skills)：学术论文写作的 Agent 技能集，覆盖文献综述、
  实验论证与草稿生成。

（本项目目前被 Academic Research Skills 列在第三方项目清单中。）

## 许可

代码为 [MIT](https://github.com/ls-open/md-to-word/blob/main/LICENSE)。内置引文样式来自
[citation-style-language/styles](https://github.com/citation-style-language/styles)，按 CC BY-SA 3.0 使用；
内置底模由本项目生成，随 MIT 发布。
