# Demo 04 — 繁體中文學術期刊（臺灣 / 香港）

以 `zh-tw-academic` 預設編出的一份兩頁短稿：新細明體正文、微軟正黑體標題、全形標點不壓縮，
公式按章編號，三線表，以及 GB/T 7714 順序編碼制的參考文獻。

```bash
md-to-word paper_zh_tw.md -o paper_zh_tw.docx          # 同目錄的 format.txt 自動生效
md-to-word paper_zh_tw.md -o paper_zh_tw.docx --preset zh-tw-academic   # 不用 format.txt 時
md-to-word paper_zh_tw.md -o paper_zh_tw.docx --pdf    # 順便出一份 PDF 對核
# 或從倉庫根目錄：
bash scripts/export.sh demo/04_zh_tw_paper/paper_zh_tw.md -o /tmp/paper.docx
```

## 這份為什麼單獨列一份

繁中不是簡中換個字型。`zh-tw-academic` 預設與 `zh-academic` 的差別都在「繁體出版習慣」上，
而這些差別沒有一個是靠肉眼一看就記得的：

| 項目 | 這份的設定 | 為什麼 |
|:--|:--|:--|
| 標點壓縮 | `標點壓縮：不壓縮` | 繁中出版習慣把全形標點放在字面中央（置中標點），壓縮會讓它們往左靠 |
| 正文 | 新細明體 | 臺灣學位論文與期刊的通行正文 |
| 標題 | 微軟正黑體 | 與正文區隔，且多數學校指定 |
| 校對語言 | `zh-TW` | 寫成 `zh-CN` 會讓 Word 用簡中詞典檢查，繁中詞被標成錯字 |
| 參考文獻標題 | `參考文獻` | 寫出器認得繁中標題，不必手寫 |

## 這份稿子演示了什麼

- YAML 裡的 `bibliography:` + `csl:`，正文用 `[@key]` 引用，文獻表由引擎生成
- `crossref: chapters: true` 的**縮進兩行**寫法（寫成一行不是合法 YAML），公式編號為 `（1-1）`
- 公式以原生 OMML 寫入，雙擊可編輯；正文用 `@eq-flux` 引用，不加方括號
- 三線表 + 表題 + 表注
- 全篇兩頁；第 2 頁是參考文獻，三條中英混排

## 維護

- 產物（`.docx` / `.pdf` / `page-1.png`）與稿子一起提交。改了稿子就重新導出一次：

  ```bash
  md-to-word paper_zh_tw.md -o paper_zh_tw.docx --pdf
  pdftoppm -png -r 110 -f 1 -l 1 -singlefile paper_zh_tw.pdf page-1
  ```

- `format.txt` 是 `presets/zh-tw-academic.txt` 的副本，改這裡不會影響預設；
  要改預設請改 `presets/zh-tw-academic.txt`（包內那份有一份同樣的副本，測試盯著兩者不許分叉）。
