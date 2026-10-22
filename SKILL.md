---
name: md-to-word
description: "Compile a Markdown manuscript into journal- or school-compliant Word (.docx): declared typography, native OMML equations, three-line tables, cross-references, page-number sections, CSL bibliographies, and pre/post-export gates — no Pandoc, no Quarto. 把 Markdown 导出为符合规范的 Word：学位论文/期刊论文/公文排版，摘要、公式编号、三线表、题注、交叉引用、目录域、CSL 参考文献。Use when the user wants a .docx — a readable copy or a compliant submission — including 导出Word、文档转Word、论文转Word、期刊排版、公文排版、prepare submission docx. Not for PDF, HTML or LaTeX output."
license: MIT
---

# Markdown → 规范 Word

把稿件编译成 `.docx`：格式全部声明在一份可进 Git 的 `requirements.txt` 里，导出确定性
（同一份源重跑逐字节一致），导前有预检、导后有对账，不合规就中止并指到行号。

**本文件只是入口。** 完整词表、契约细则、门禁判据、能力边界都在包内手册：

```
src/md_to_word/resources/manual.md      ← 唯一真相源，随包发布
```

跑 `md-to-word --contract` 可以直接拿到它的绝对路径（加 `--lang en` 得英文版）。下面只写
"先做什么、按什么顺序做"，写法一律查手册，不在此复述。

## 怎么用这个仓库

| 用法 | 命令 |
|:--|:--|
| 本地导出 | `bash scripts/export.sh 稿件.md -o 输出.docx`（用仓库里的 `src/`，不需要装包） |
| 装成命令 | `pip install md-to-word-docx` → `md-to-word 稿件.md -o 输出.docx` |
| Python | `from md_to_word import export` |

依赖：`pip install -r requirements.txt`（五个纯 Python 包）。不需要 Pandoc、Quarto 或任何外部二进制；
`--pdf` 视觉抽查才用到本机 Word（仅 macOS，其余平台自动跳过）。

## 代办流程

1. **判断场景**：用户给了明确格式 → 走格式提取；只说"转成 Word" → 用内置预设做基线导出
   （预设本身是一套完整合规的格式，不是占位）。
2. **整理稿件**：统一成符合契约的 Markdown。契约三条：标题用 `#`；段落样式写 `%% 样式名 内容`；
   带编号公式写 `$$…$$ {#eq-标签}`。**标题、作者、摘要写正文的样式行，不写 YAML**；
   YAML 只放与位置无关的配置（`bibliography:` / `csl:` / `crossref:`）。
3. **准备格式要求**：内置预设（中文稿 `zh-academic`、其他 `en-nature`，不传 `-r` 时按稿件语种
   自动选）；或从参考 `.docx` 反推草稿（`bash scripts/read_reference_docx.py`）；或复制预设后
   只改用户明确提到的那几行。属性写法只有一种，查手册 §3.1。
4. **导出**：一条命令跑完 预检 → 生成模板 → 写 OOXML → 防丢数 → 与要求文件逐条对账。
5. **交付**：确认退出码 0；把预设/要求文件、引文样式、以及任何提醒如实告诉用户；
   **版面仍需在 Word 里看过**——行高列宽、公式与题注的落版、页眉页脚只有真打开才算核过。

## 门禁怎么读

两级，判据是「错了看不看得见」：

- **阻断**：静默出错，事后看不出来——内容丢字、语法退化成字面文本、格式没映射上、
  YAML 里写了标题、题注塞进图片方括号。按报错的行号改稿，**不要用 `--no-check` 绕过**。
- **提醒**：看得见但不合规——图片超宽被钳、题注离图表远、标题跳级、分节后又写分页。

退出码：`0` 完成；`1` 稿件/门禁/依赖问题；`3` `.docx` 已写出但 `--pdf` 未渲染。

## 说不出来的东西

定制封面页、合并单元格、多栏混排、行内彩色文字、文字环绕的浮动图——**提前讲清楚，不要用
不匹配的 Markdown 勉强表达**，勉强出来的产物是静默错的。带编号公式里求和/积分的上下限排在
符号右侧（Word 只在显示式里上下排），内容与符号不受影响。

完整边界见手册 §6；报错速查见 §8。

## 相关

- 自包含技能版（不依赖 pip、自带整棵源码）：`nature-skills` 仓库的 `skills/nature-paper2word`
- 设计原理与故障排查：`references/design.md`
- 四份样例：`demo/`
