"""md_to_word.spec.models — 格式规范数据模型。

提供强类型结构的 Spec 对象，作为全流水线共享的数据契约。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


class MinLineSpacing:
    """行距「最小值 N 磅」：与 Pt / float 区分，对应 Word 的 `w:lineRule="atLeast"`。

    三种行距不能用同一个类型表达——`Pt` 是固定值、`float` 是倍数、本类是**最小值**。
    固定值会把超高的内容裁掉，与最小值在单行时长得一样，只有折行才分得出，故类型上
    就必须分开。**全流水线共用这一个类**（解析器产出、模板生成写入、导出后对账读取）：
    各层各定义一份时 `isinstance` 认不出自己人，最小值会被当成倍数去乘 240。
    """

    def __init__(self, pt: float):
        self.pt = float(pt)

    def __repr__(self) -> str:
        return f"MinLineSpacing({self.pt}pt)"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, MinLineSpacing) and abs(self.pt - other.pt) < 1e-4


@dataclass
class TemplateSpec:
    """format.txt 的完整强类型数据模型。"""

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
    equation_number: str = "right"  # right=编号靠右（默认）| inline=紧跟公式
    # 编号外观模板：`（{c}-{n}）`。空串=按语种与是否按章编号自动给默认
    equation_number_format: str = ""
    # 附录里的编号外观；空串=沿用 equation_number_format。学校要「（附2-1）」还是
    # 「（B-1）」是两种不同的前缀，一个全局模板表达不了，故单列一行。
    appendix_equation_number_format: str = ""
    proofing_lang: Optional[str] = None
    header_distance: Optional[float] = None
    footer_distance: Optional[float] = None

    def get_style(self, style_name: str) -> Optional[dict[str, Any]]:
        """按 style_name 获取对应的样式配置字典。"""
        for s in self.styles:
            if s.get("style_name") == style_name:
                return s
        return None
