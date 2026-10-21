"""md_to_word.renderer.base — 渲染引擎抽象基类（3.0 可拔插插槽）。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BaseRenderer(ABC):
    """渲染器抽象基类。将预处理后的 Markdown 编译为原始 DOCX。"""

    @abstractmethod
    def is_available(self) -> bool:
        """检查当前环境该渲染器是否就绪可用。"""
        pass

    @abstractmethod
    def render(
        self,
        input_md: Path | str,
        template_docx: Path | str,
        output_docx: Path | str,
    ) -> Path:
        """执行编译渲染。

        参数:
            input_md: 展开标记后的 Markdown 稿件文件
            template_docx: 包含样式定义的参考文档模板
            output_docx: 最终产出的原始 DOCX 路径
        返回:
            生成的 output_docx Path
        """
        pass
