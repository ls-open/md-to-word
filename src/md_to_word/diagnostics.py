"""md_to_word.diagnostics — 机器可读的诊断条目。

`errors` / `warnings` 是给人读的句子，`diagnostics` 是给程序读的同一条信息：
稳定的 `code`、严重度、文件与行号。两条出口（CLI `--json`、MCP）都从这里取，
不在各自那里再拼一遍。

`code` 用 i18n 键或类别名，一经发布不再改名——改 `code` 等于改 Agent 的分支条件。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Diagnostic:
    """一条结构化的校验/导出结果。"""

    severity: Severity
    code: str
    message: str
    file: Optional[str] = None
    line: Optional[int] = None

    def as_dict(self) -> dict:
        """固定键集：即使是空值也保留，解析方不必猜字段在不在。"""
        return {
            "severity": self.severity,
            "code": self.code,
            "file": self.file,
            "line": self.line,
            "message": self.message,
        }
