"""md_to_word.status — 退出码。

技能与脚本靠这几个数字判断结果（`SKILL.md` §8 把它们列在冻结面里），
所以在代码里只写一次：改数字等于改契约。
"""

from __future__ import annotations

EXIT_OK = 0
EXIT_ERROR = 1          # 稿件、门禁或依赖问题
EXIT_USAGE = 2          # 参数写法不对（解析阶段就返回，不产出 JSON）
EXIT_PDF_SKIPPED = 3    # docx 已写出，--pdf 未渲染
