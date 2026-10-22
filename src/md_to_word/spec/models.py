"""md_to_word.spec.models — 格式规范数据模型。

提供强类型结构的 Spec 对象，作为全流水线共享的数据契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class MinLineSpacing:
    """行距最小值（磅）。与 Pt / float 区分，对应 Word 的 lineRule='atLeast'。"""

    def __init__(self, pt: float):
        self.pt = float(pt)

    def __repr__(self) -> str:
        return f"MinLineSpacing({self.pt}pt)"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, MinLineSpacing) and abs(self.pt - other.pt) < 1e-4


@dataclass
class TemplateSpec:
    """requirements.txt 的完整强类型数据模型。"""

    schema_version: int = 1
    styles: list[dict[str, Any]] = field(default_factory=list)
    default_latin: Optional[str] = None
    margins: Optional[dict[str, float]] = None
    table: dict[str, Any] = field(default_factory=dict)
    table_header: Optional[dict[str, Any]] = None
    decor: dict[tuple[str, str], list[tuple[str, str]]] = field(default_factory=dict)
    page_number: Optional[tuple[str, int]] = None
    page_size: str = "a4"
    gutter_cm: Optional[float] = None
    doc_grid_lines: Optional[int] = None
    proofing_lang: Optional[str] = None
    header_distance: Optional[float] = None
    footer_distance: Optional[float] = None

    def get_style(self, style_name: str) -> Optional[dict[str, Any]]:
        """按 style_name 获取对应的样式配置字典。"""
        for s in self.styles:
            if s.get("style_name") == style_name:
                return s
        return None
