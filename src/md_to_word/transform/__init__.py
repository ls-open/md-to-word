"""md_to_word.transform — 与格式转换有关、但不属于模型也不属于写出的中间步骤。"""

from md_to_word.transform.mathml2omml import latex_to_omml, mathml_to_omml

__all__ = ["latex_to_omml", "mathml_to_omml"]
