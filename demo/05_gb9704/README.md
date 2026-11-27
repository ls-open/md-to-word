# Demo 05 — 党政机关公文正文版式（GB/T 9704-2012）

用 `--preset zh-gb9704` 导出一份公文正文：A4、版心 156×225mm、三号仿宋、22 行/面、
二号小标宋标题、全网格表、四号宋体页码（`— 1 —`）。

```bash
md-to-word gongwen_sample.md -o gongwen_sample.docx --preset zh-gb9704
# 或从仓库根目录：
bash scripts/export.sh demo/05_gb9704/gongwen_sample.md -o /tmp/gongwen.docx
```

`gongwen_sample.docx` / `.pdf` / `page-*.png` 是这个预设导出的成品与页面图（真 Word 渲染）。

这个预设**只负责从标题开始的正文版式**，不包含红头、发文字号、签发人、红色分隔线、
版记与印章。需要完整红头公文时，用现成的红头模板套入：

```bash
md-to-word gongwen_sample.md -o gongwen_sample.docx \
  --preset zh-gb9704 --base-template 红头模板.docx --keep-until "签发人"
```

切点要停在模板目录之前；上例的「签发人」只是红头里常见的一行，请按自己模板改成
目录前的最后一行。红头模板若已经用分节符分开，也可以直接用 `--cover-sections N`。
`--keep-until "目录"` 会被拒绝——目录不能保留，正文目录由稿件生成。

已知差异：单页页码居右、双页居左的分置做不到（只有一个页脚样式）；署名/日期的
「右空二字 / 右空四字」只能右对齐近似；页码数字随西文字体走 Times New Roman，
版式、字号、位置一致，字形与纯宋体数字略有差别。

字体：方正小标宋简体不是 Windows/macOS 系统自带字体，需另行安装。未安装时 Word
会替换标题字体（本目录的预览 PDF 就是用替换字体渲染的），正文版式不受影响，
但「二号小标宋」的字形只在装好该字体的机器上成立。
