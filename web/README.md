# web/ —— 官网样张页的生成器

一条命令，把四套内置格式的样张编译成成品，再渲染出静态展示页：

```bash
python3 web/build.py            # 四套全建
python3 web/build.py zh-report  # 只重建一套
```

产物在 `docs/`，发布出去的也是 `docs/`：

```
docs/index.html          展示页（由 web/page.html 填内容生成，别手改）
docs/assets/<id>.docx    可直接下载，用 Word 打开就是成品
docs/assets/<id>.pdf     Word 渲染出来的分页（域已展开）
docs/assets/<id>.png     首页图，页面里当预览
```

| 文件 | 职责 |
|:--|:--|
| `catalog.py` | 四套模板的正文、规格清单与 `format.txt`。**内容唯一真相源**，只放纯函数 |
| `page.html` | 页面模板，含 `{{INPUTS}}` / `{{LABELS}}` / `{{PANELS}}` / `{{TAB_CSS}}` 占位 |
| `build.py` | 导出样张 → 渲染首页图 → 填模板生成页面 |

## 为什么是静态的

这里曾经是一个 FastAPI 服务（表单填内容 → 在线编译 → 浏览器预览 PDF）。2026-11 拆掉了，理由：

- 它演示的是**最弱的那一面**：让人先填十来个输入框，才看得到一张玩具稿。真正的说服力是「下载那份 `.docx`，用 Word 打开，发现真的是成品」，这一步被藏在表单后面了。
- 成本不成比例：一台要养的服务器（systemd + nginx + 证书 + 限流 + 对公网开放的编译能力）、两份要手工同步的前端页面、以及一套只能写进公开仓库的服务器信息。
- 静态页永不宕机、零维护，`docs/` 交给 GitHub Pages 就够；页面上的东西照样是真导出的，可复核。

所以现在：**没有任何后端，也没有需要维护的服务器**。

## 发布

GitHub Pages 的源设成 **`main` 分支的 `/docs` 目录**（仓库 Settings → Pages）。
`docs/.nojekyll` 已经放好，`assets/` 不走 Jekyll 处理。

以前是从 `gh-pages` 分支发布的，那份 `index.html` 是手工拷过去的副本，落后过一整轮——
繁中模板、错误提示、页脚措辞都缺，而 README 的第一个按钮就指向它。切到 `main /docs` 之后
只有一个真相源。切换完成后本地那两个分支（`gh-pages`、`pages-sync`）就可以删了。

## 依赖

导出本身只要包本体。**PDF 与首页图需要两样额外的东西**：

- **Microsoft Word（macOS）**：`--pdf` 走本机 Word 渲染，目录、`STYLEREF` 页眉章名、页码这些
  域只有 Word 会真正展开。没有 Word 时 docx 照样生成，PDF 与预览图跳过，脚本会在末尾告诉你。
- **`pdftoppm`（poppler）**：PDF 转首页图。`brew install poppler`。

所以 `docs/assets/*.pdf` 与 `*.png` 是**提交进仓库的二进制**，CI 上不重建（Linux 没有 Word）。
改了样张正文就要在 macOS 上重跑一次 `build.py`，把 docx/pdf/png 一起提交。

## 测试

`tests/test_web_templates.py` 锁五件事，其中两条是这一层最容易烂的地方：

- **提交的 `.docx` 与现场以同一条命令重新导出的逐字节一致**——页面上写着「这不是效果图」，
  那就得能复核；改了样张忘了重建产物会直接红。只重导出 docx，不渲染 PDF，所以不需要 Word。
- **`docs/index.html` 与重新渲染的结果一致**——页面是生成物，改了 `catalog.py` 或 `page.html`
  忘了重建，用户看到的就是旧页面。

## 已知局限

- 预览图是**第一页**。样张都是单页稿；想看学位论文的九页，去仓库 `demo/01_chinese_thesis/`。
- 页面只做展示，不能改内容。想试自己的稿子：`pip install md-to-word-docx`，或把 Markdown 交给
  装了本技能的 Agent。
- PDF 是 Word 在 macOS 上渲染的，Windows 下的分页没有验证过；`docs/index.html` 的措辞不要写成
  「任何机器上都长这样」。
