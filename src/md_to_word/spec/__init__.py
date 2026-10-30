"""md_to_word.spec — 规范解析与数据模型子包。"""

from md_to_word.spec.constants import (
    ALIGN_MAP,
    ALIGN_VAL,
    PAGE_SIZES_CM,
    PAGE_SIZE_MAP,
    SIZE_MAP,
    STYLE_CN,
    STYLE_MAP,
    TWIPS_PER_CM,
)
from md_to_word.spec.models import MinLineSpacing, TemplateSpec
from md_to_word.spec.parser import parse_format, parse_requirements
from md_to_word.spec.presets import list_available_presets, read_preset_content
from md_to_word.spec.serializer import serialize_format, serialize_requirements

__all__ = [
    "TemplateSpec",
    "MinLineSpacing",
    "parse_format",
    "parse_requirements",
    "serialize_format",
    "serialize_requirements",
    "list_available_presets",
    "read_preset_content",
    "SIZE_MAP",
    "STYLE_MAP",
    "STYLE_CN",
    "PAGE_SIZE_MAP",
    "PAGE_SIZES_CM",
    "TWIPS_PER_CM",
    "ALIGN_MAP",
    "ALIGN_VAL",
]
