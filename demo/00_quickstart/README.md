# 最小可跑样例：一页纸，30 秒看懂

这是三个样例里最小的一个：**一份 26 行稿件（不含空行）+ 一份 14 行 `requirements.txt`（不含空行），导出 1 页**。
它的用途不是展示功能，而是让你（和你的 Agent）在 30 秒内看清**输入长什么样、输出长什么样**，顺便验证环境装好了没。

---

## 一、 这两个文件是什么关系

| 文件 | 作用 |
| :--- | :--- |
| `hello.md` | **内容**——你写的东西（正文、标题、三线表） |
| `requirements.txt` | **格式**——每行一条排版规则，导出时编译成 Word 样式 |
| `hello.docx` / `hello.pdf` | 产物：`hello.md` 按 `requirements.txt` 排出来的结果 |
| `page-1.png` | 上面那份 PDF 的第一页，方便直接看 |

改动 `hello.md` 的内容不影响排版，改动 `requirements.txt` 的一行就能整篇换格式——这就是「内容与排版解耦」。

## 二、 这一页演示了什么

| 排版要素 | 在哪儿声明 |
| :--- | :--- |
| 中文首行缩进 2 字符、西文 Times New Roman | `正文：… 首行缩进2字符` |
| 三级标题阶梯（黑体，字号递减） | `文档标题 / 一级标题 / 二级标题` |
| 三线表 + 表题 + 表注 | `表格：` `表格题注：` `表注：` |
| 跨页自动重现表头 | `表头：… 跨页重复` |
| 表格列宽比例 | 分隔行写成 `\|:------\|:--\|:---\|:--------------\|`（长短不一即比例） |

## 三、 一键运行复现

在当前目录下执行：

```bash
# 导出规范 Word 文档（.docx）
bash ../../scripts/export.sh hello.md -r requirements.txt -o hello.docx

# （可选，仅限 macOS 且装有 Word）顺带输出排版 PDF 对照样张
bash ../../scripts/export.sh hello.md -r requirements.txt -o hello.docx --pdf
```

预期：几秒内输出 `✅ Word 文档导出成功`，得到一份 1 页的 `.docx`。

## 四、 接着看什么

- 想看更全的写法：`demo/01_chinese_thesis/`（学位论文：目录、分节页码、公式编号、国标文献）
- 想看商业文档：`demo/02_modern_report/`（白皮书：全网格线表、APA 引用、极简页眉）
- 想知道每个词的确切含义：`references/reference.md §1.5` 的完整词表
