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

这里曾经是一个 FastAPI 服务（表单填内容 → 在线编译 → 浏览器预览 PDF），2026-11 移除。原因有两条：一是它把最有力的那一步藏起来了——真正的说服力是「下载 `.docx`，用 Word 打开，发现是成品」，而表单要求人先填十来个输入框才看得到一张玩具稿；二是成本不成比例，要养一台服务器（systemd、nginx、证书、限流、对公网开放的编译能力），还要维护两份手工同步的前端。

所以现在：**没有任何后端，也没有需要维护的服务器**。静态页不会宕机、零维护，页面上的东西照样是真导出的，可复核。

## 发布

GitHub Pages 的源是 **`main` 分支的 `/docs` 目录**（仓库 Settings → Pages），`docs/.nojekyll` 已放好，`assets/` 不走 Jekyll 处理。产物与页面都提交进仓库，不在 CI 上重建，因此只有一个真相源。

## 依赖

导出本身只要包本体。**PDF 与首页图需要两样额外的东西**：

- **Microsoft Word（macOS）**：`--pdf` 走本机 Word 渲染，目录、`STYLEREF` 页眉章名、页码这些
  域只有 Word 会真正展开。没有 Word 时 docx 照样生成，PDF 与预览图跳过，脚本会在末尾告诉你。
- **`pdftoppm`（poppler）**：PDF 转首页图。`brew install poppler`。

所以 `docs/assets/*.pdf` 与 `*.png` 是**提交进仓库的二进制**，CI 上不重建（Linux 没有 Word）。
改了样张正文就要在 macOS 上重跑一次 `build.py`，把 docx/pdf/png 一起提交。

## 测试

`tests/test_web_templates.py` 锁五件事，其中两条覆盖这一层最容易出错的环节：

- **提交的 `.docx` 与现场以同一条命令重新导出的逐字节一致**——页面上写着「这不是效果图」，
  那就得能复核；改了样张却忘了重建产物，这条测试会失败。只重导出 docx，不渲染 PDF，所以不需要 Word。
- **`docs/index.html` 与重新渲染的结果一致**——页面是生成物：改了 `catalog.py` 或
  `page.html` 却没有重建，用户看到的就是旧页面。

## 已知局限

- 预览图是**第一页**。样张都是单页稿；想看学位论文的九页，去仓库 `demo/01_chinese_thesis/`。
- 页面只做展示，不能改内容。想试自己的稿子：`pip install md-to-word-docx`，或把 Markdown 交给
  装了本技能的 Agent。
- PDF 是 Word 在 macOS 上渲染的，Windows 下的分页没有验证过；`docs/index.html` 的措辞不要写成
  「任何机器上都长这样」。
- **「逐字节一致」只在同一平台上成立。** 时间戳、权限、条目顺序都已经钉死，但 deflate
  压缩流的字节取决于 zlib 的实现与版本——macOS 的系统 zlib 与 Windows 的 CPython 自带
  那份打出来的字节不同，内容一样。所以 `test_committed_docx_matches_a_fresh_export`
  在 Windows 上跳过：它检查的是「源码改了有没有忘记重建产物」，在生成产物的平台上跑就够了。
