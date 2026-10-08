# md-to-word

基于声明式中文格式配置（`requirements.txt`）与 Quarto 渲染引擎的 **Markdown 转规范 Word（`.docx`）工具与 AI Agent Skill**，专为中文/英文学术期刊论文、硕博学位论文、长文报告与规范公文设计。

无需打开 Microsoft Word 手工点选修改样式面板：只需一份纯文本格式要求（或由脚本从现有参考 `.docx` 自动提取），即可动态生成纯净 Word 365 样式模板，并通过三道自动化质量门禁（导前语法预检、导后防丢数检查、OOXML 样式逐项对账）一键导出可直接交付的 `.docx` 文档。

---

## 核心特性

- **纯中文声明式样式编译（零 GUI 手调）**
  用直观的受控词表（如 `正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符`）动态编译 `.docx` 参考模板；也支持用 `scripts/read_reference_docx.py` 从学校/期刊现有的 `.docx` 模板反向提取配置草稿。
- **纯净现代 Word 365 底模**
  底层采用无主题字体锁（`asciiTheme` / `eastAsiaTheme`）的原生 Word 365（`compatMode=15`）底模，中文字体（`w:eastAsia`）与西文字体（`w:ascii` / `w:hAnsi`）独立绑定，彻底解决 Pandoc 默认模板“改了字体不生效、标题带蓝底线、正文首行缩进污染图表与题注”等顽疾。
- **学术排版细节全覆盖**
  - **数学公式**：自动将带编号公式重构为三列固定布局无边框表格，实现**公式整页居中 + 编号严格靠右对齐**（支持 `(1)`、按章 `(5.1)` 及中文习惯 `（5-1）`）；
  - **三线表与网格表**：原生写入 `Table` 样式条件格式与单元格级边框，支持三线表、全网格线、顶底线、表头跨页重复与单元格垂直对齐；
  - **分节、目录与页眉页脚**：支持 `{{< toc >}}` 自动目录、`{{< section >}}` 分节独立页码（前置罗马页码 `I, II` + 正文阿拉伯页码从 `1` 起算）、奇偶页/首页不同页眉页脚，以及 `STYLEREF` 动态章标题域；
  - **内置 20 种规范化 CSL 引用样式**：涵盖 `GB/T 7714-2015`（顺序编码制 / 作者-年份制）、`APA`、`IEEE`、`Nature`、`Science`、`Cell`、`Lancet`、`AMA`、`Vancouver` 等，已预先剥离会破坏 Word 悬挂缩进的 CSL 布局标签。
- **三道确定性质量门禁**
  1. **导前预检（`scripts/check_md.py`）**：拦截标题跳级、围栏缺空行、`\tag{}` 误用、未声明的深层结构样式；
  2. **导后防丢数（`scripts/post_flight_check.py`）**：确定性比对源稿与导出 `.docx`（含 OMML 公式节点）中的所有高精度小数，零容忍后处理丢段；
  3. **OOXML 样式对账（`scripts/audit_export.py`）**：沿 `basedOn` 继承链逐条核对产物 `.docx` 的字体、字号、粗斜体、对齐、行距、缩进、边框、纸张边距与页码设置，不符即阻断。

---

## 环境要求与安装

1. **安装 Python 依赖**（需 Python 3.9+）：
   ```bash
   pip install -r requirements.txt
   ```
2. **安装 Quarto**（需 Quarto $\ge 1.4$，内嵌 Pandoc）：
   ```bash
   # macOS
   brew install quarto
   ```
3. **作为 AI Agent Skill 安装（Claude Code / Cursor / Antigravity 等）**：
   将本仓库克隆至 Agent 的技能目录即可自动识别：
   ```bash
   git clone https://github.com/ls18166407597-design/md-to-word.git ~/.claude/skills/md-to-word
   ```

---

## 快速使用

### 方式一：通过 AI Agent 自动代办（推荐）

安装为 Skill 后，直接在对话中告诉 AI：
> “把 `paper.md` 按附件这份格式要求（或参考模板 `sample.docx`）导出为 Word 文档。”

Agent 会自动参照 [`SKILL.md`](SKILL.md) 完成格式提取、`requirements.txt` 组装、Markdown 契约规范化与全流程导出校验。

### 方式二：命令行直接调用

#### 1. 编写或提取格式要求文件（`requirements.txt`）

如果你手头有现成的参考 `.docx` 样张，可先一键提取草稿：
```bash
python3 scripts/read_reference_docx.py 参考样张.docx -o requirements.txt
```

或者直接编写 `requirements.txt`（完整语法与受控词表见 [`references/reference.md`](references/reference.md)）：
```text
纸张：A4
页边距：上2.54cm 下2.54cm 左2.54cm 右2.54cm
校对语言：zh-CN
页码：阿拉伯 起始1
页脚：宋体/Times New Roman 小五 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符
页脚内容：{页码}

论文标题：黑体/Times New Roman 小二 加粗 不倾斜 居中 行距1.5倍 段前0磅 段后18磅 首行缩进0字符
摘要标题：黑体/Times New Roman 小三 加粗 不倾斜 居中 行距1.5倍 段前0磅 段后12磅 首行缩进0字符
摘要：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符
关键词：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前6磅 段后12磅 首行缩进0字符
一级标题：黑体/Times New Roman 三号 加粗 不倾斜 左对齐 行距1.5倍 段前18磅 段后12磅 首行缩进0字符
二级标题：黑体/Times New Roman 四号 加粗 不倾斜 左对齐 行距1.5倍 段前12磅 段后6磅 首行缩进0字符
正文：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符
首段：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进2字符
普通：宋体/Times New Roman 小四 不加粗 不倾斜 两端对齐 行距1.5倍 段前0磅 段后0磅 首行缩进0字符
图片题注：黑体/Times New Roman 五号 加粗 不倾斜 居中 行距1.0倍 段前6磅 段后12磅 首行缩进0字符
图：居中 行距1.0倍 段前6磅 段后6磅
表格题注：黑体/Times New Roman 五号 加粗 不倾斜 居中 行距1.0倍 段前12磅 段后6磅 首行缩进0字符
表头：宋体/Times New Roman 五号 加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符 跨页重复
紧凑：宋体/Times New Roman 五号 不加粗 不倾斜 居中 行距1.0倍 段前0磅 段后0磅 首行缩进0字符
表注：宋体/Times New Roman 小五 不加粗 不倾斜 左对齐 行距1.0倍 段前3磅 段后6磅 首行缩进0字符
表格：居中 三线表 线宽上1.5磅 线宽底1.5磅 线宽表头下0.75磅 单元格垂直居中
参考文献标题：黑体/Times New Roman 三号 加粗 不倾斜 左对齐 行距1.5倍 段前18磅 段后12磅 首行缩进0字符
参考文献：宋体/Times New Roman 五号 不加粗 不倾斜 两端对齐 行距1.25倍 段前0磅 段后3磅 悬挂缩进0.5英寸
```

#### 2. 一键渲染导出并过检

```bash
# 标准导出（自动生成模板 → 导前预检 → Quarto 渲染 → 公式重构与主题净化 → 导后防丢数 → 样式对账）
bash scripts/export.sh paper.md -r requirements.txt -o paper.docx

# 中文学位论文按章公式编号改写为（1-1）样式
bash scripts/export.sh thesis.md -r requirements.txt -o thesis.docx --eq-number-style cjk
```

---

## 仓库目录结构

```text
md-to-word/
├── SKILL.md                        # AI Agent 技能主入口与分步工作流说明
├── requirements.txt                # Python 依赖声明 (python-docx, lxml)
├── LICENSE                         # MIT 开源协议
├── references/
│   ├── reference.md                # requirements.txt 完整受控词表、默认值推导规则与内置 CSL 清单
│   └── design.md                   # 内部架构原理（Word 365 底模、公式表格重构、OOXML 故障排查）
├── resources/
│   ├── pure_modern_base.docx       # 纯净现代 Word 365 基础母版
│   └── csl/                        # 20 个已去除布局干扰标签的内置学术引用样式 (.csl)
└── scripts/
    ├── export.sh                   # 一键导出与全链路门禁主入口
    ├── generate_template.py        # 声明式 requirements.txt → Word 模板编译器
    ├── read_reference_docx.py      # 现有参考 .docx → requirements.txt 反向提取器
    ├── check_md.py                 # 门禁 1：Markdown 排版契约与结构样式预检
    ├── expand_markers.py           # 目录 {{< toc >}} 与分节 {{< section >}} OpenXML 展开器
    ├── fix_docx_equations.py       # 公式居中+右编号重构与末端主题属性净化
    ├── post_flight_check.py        # 门禁 2：导后高精度数值完整性检查
    ├── audit_export.py             # 门禁 3：产物 .docx 与 requirements.txt 逐项对账
    ├── normalize_csl.py            # CSL 样式布局属性清洗工具
    ├── create_pure_modern_base.py  # 纯净 Word 365 底模从零构建脚本
    ├── render_via_word.sh          # macOS Microsoft Word 域更新与 PDF 渲染辅助脚本
    └── skill_utils.py              # 公共解析与 XML 主题清洗工具库
```

---

## 开源协议

本项目基于 [MIT License](LICENSE) 开源。
