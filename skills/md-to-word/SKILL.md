---
name: md-to-word
description: "Markdown 转 Word 文档排版工具。将 Markdown 稿件编译为符合学术期刊或高校学位论文规范的 Word (.docx) 文档，支持 Word 原生 OMML 矢量数学公式、学术三线表、CSL 引用、双册手册指引及学位论文底模灌入（实验性场景）。"
allowed-tools: Read,Write,Bash
---

# md-to-word：Markdown 转规范 Word 排版技能

本技能负责将 Markdown 稿件排版为符合学术期刊或高校学位论文规范的 Word（`.docx`）文档。底层排版由 `md-to-word-docx` 包执行。

## 1. 运行环境检查

排版前检查环境中是否已安装底层引擎：

```bash
md-to-word --version
```

- 若未安装，提示用户安装：`uv tool install md-to-word-docx` 或 `pip install md-to-word-docx`。
- 若版本低于 `3.3.0`，提示升级以支持双册手册特性。

## 2. 查阅契约与场景分流

运行以下命令获取规范契约、模板库地址及本地两册手册路径：

```bash
md-to-word --contract
```

根据场景决定排版路径：

| 场景 | 用户表达举例 | 对应路径 |
| :--- | :--- | :--- |
| **常规学术论文** | “投期刊”、“投稿排版”、“格式按 Nature / 规范来” | 查阅**第 1 册手册**；使用内置预设 `--preset zh-academic` / `--preset en-nature` 或使用现有格式文件 `-f format.txt`。 |
| **高校硕博学位论文** | “毕业论文”、“大论文”、“学位论文” | 查阅**第 2 册手册**；按高校格式要求使用 `-f format.txt`，配合分节及附录规则排版。 |
| **保留学校底模封面（实验性场景）** | “需要保留学校模板的封面/声明页”、“不要自己做封面” | 查阅**第 2 册手册 §2**；此为**实验性场景**（非通用保证），针对需原样继承学校前置件的特定需求：`--base-template 学校模板.docx --keep-until "版权使用授权书"`。底模结构各校差异大，引擎采取「验不过就不产出文件」的安全拦截策略。 |
| **已有参考文档** | “参考这份已有格式” | 先查阅模板库是否有现成格式；若无，通过 `md-to-word-template 参考.docx -o format.txt` 反推初稿并逐条人工核对。 |

## 3. 标准排版步骤

1. **确定格式文件**：
   - 先通过 `md-to-word --contract` 提供的模板库地址查阅是否有现成要求文件；
   - 确定使用预设（`--preset`）还是具体的格式文件（`-f format.txt`）。

2. **稿件语法约束**：
   - 数学公式：行内 `$..$`，行间 `$$..$$`，交叉引用标签放末尾 `{#eq-id}`；
   - 表格：标准 Markdown 管道表格（导出自动渲染为规范三线表）；
   - 引文：使用 `[@citekey]`，文末放 `%% 参考文献`。

3. **执行导出**：

常规排版导出（主流通用方式）：
```bash
md-to-word manuscript.md -f format.txt -o output.docx
```

特定场景：学位论文保留学校原版封面（实验性功能）：
```bash
md-to-word manuscript.md -f format.txt --base-template school.docx --keep-until "版权使用授权书" -o output.docx
```

4. **导出后验证**：
   - 检查终端返回的退出码是否为 0；
   - 查看是否有预检警告或对账提示；
   - 确认生成的 `.docx` 结构完整。
