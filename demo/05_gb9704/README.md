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
  --preset zh-gb9704 --base-template 红头模板.docx --keep-until "目录"
```

已知差异：单页页码居右、双页居左的分置做不到（只有一个页脚样式）；署名/日期的
「右空二字 / 右空四字」只能右对齐近似；页码数字随西文字体走 Times New Roman，
版式、字号、位置一致，字形与纯宋体数字略有差别。
