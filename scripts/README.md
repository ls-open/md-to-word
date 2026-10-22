# scripts/ —— 开发与验收工具

这些脚本**不进包**：用户拿到的是 `pip install md-to-word-docx` 之后的 `md-to-word` 命令。脚本只是把包内
已有的能力转成命令行，供仓库内调试与验收使用。各自实现都在 `src/md_to_word/`，这里只做参数转发。
详细用法看各脚本的 `--help`。

| 脚本 | 做什么 | 等价的包内命令 |
|:--|:--|:--|
| `export.sh` | 导出。先找已安装的 `md-to-word`，没有就用仓库里的 `src/` 兜底 | `md-to-word` / `python3 -m md_to_word` |
| `read_reference_docx.py` | 从参考 `.docx` 反推 `format.txt` 草稿 | `md-to-word-template` |
| `generate_template.py` | 只按要求文件生成样式模板，用来看产物长什么样 | —（导出时会临时生成） |
| `check_md.py` | 单独跑导前预检 | —（每次导出都会跑） |
| `normalize_csl.py` | 规范化 CSL（剥掉 `<bibliography>` 上的直接格式属性） | —（用户自带 CSL 时自动执行） |
| `render_via_word.sh` | 用本机 Word 把 docx 渲染成 PDF（macOS） | `md-to-word … --pdf` |
| `create_pure_modern_base.py` | 重新生成 `resources/pure_modern_base.docx` | —（底模已随包发布） |

## 视觉核验的轻重

全篇逐页翻看不现实，改一个错字就渲染也浪费。按改动面决定：

| 改了什么 | 怎么做 |
|:--|:--|
| 正文文字、错别字 | 不渲染。导出后的对账已经比过样式与数字 |
| 要求文件、大表格、长公式、CSL | 渲染并只看受影响的那几页 |
| 正式提交前 | 完整渲染一次，按下面四点抽查 |

四点抽查（直击风险截面，不翻全篇）：

1. **首页**：大标题居中、摘要与关键词、首段与次段的缩进对比、"首页不同"是否生效；
2. **最宽的表**：表格两端在版心内、数字列对齐、跨页处表头重复且没有断行错位；
3. **公式与图密集页**：公式居中且编号靠右、图片不变形、图题与图同页；
4. **参考文献起止页**：页眉章名（`STYLEREF`）不出「错误!未找到引用源」、页码连续、悬挂缩进平整。

**为什么必须用 Word**：目录、页眉章名、页码都是域，只有 Word 会把它们真正展开；LibreOffice 能转
PDF 但不展开域，核对这些内容时不能用。Word for Mac 是沙箱应用，脚本先把文件拷进它的容器目录再渲染，
避免逐次弹窗；中转文件带进程号并在退出时清理。抽查页面转图用 `pdftoppm`（poppler），不要用 PyMuPDF
——内嵌字体容易报乱码。
