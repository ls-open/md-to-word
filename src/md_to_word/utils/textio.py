"""md_to_word.utils.textio — 读取用户文本文件。

用户稿件与格式文件不是只有 UTF-8 一种来源：Windows 记事本会写 UTF-8 BOM 或 UTF-16，
中文旧文件常见 GB18030/GBK。这里按 BOM 与内容依次尝试，读取后统一换行——
调用方只需要「拿到文字」，不必在每一处各写一遍编码判断。
"""

from __future__ import annotations

import codecs
from pathlib import Path

# 按优先级排列：有 BOM 时只认 BOM 声明的编码，不拿别的编码去猜。
_BOM_ENCODINGS = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8-sig"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)

# 读取成功但不在这个集合里的编码，会提醒用户另存为 UTF-8（BOM 仍然算 UTF-8）。
UTF8_ENCODINGS = frozenset({"utf-8", "utf-8-sig"})


class TextDecodeError(ValueError):
    """文件既不是 UTF-8，也解不成 UTF-16 / GB18030。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        super().__init__(
            f"{self.path}: not UTF-8, UTF-16 or GB18030"
        )


def _candidate_encodings(data: bytes) -> tuple[str, ...]:
    for bom, encoding in _BOM_ENCODINGS:
        if data.startswith(bom):
            return (encoding,)
    # 无 BOM 的 UTF-16 会在开头出现 NUL；先试 UTF-16，再退到中文最常见的 GB18030。
    if b"\x00" in data[:4096]:
        return ("utf-8", "utf-16", "gb18030")
    return ("utf-8", "gb18030")


def _normalize_newlines(text: str) -> str:
    """与 `Path.read_text` 的 universal-newline 行为对齐：CRLF / CR 都变成 LF。"""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def decode_text(data: bytes, path: Path | str = "<bytes>") -> tuple[str, str]:
    """返回 `(text, encoding)`；全失败时抛 `TextDecodeError`。"""
    for encoding in _candidate_encodings(data):
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        # GB18030 能解出几乎任意字节；解出 NUL 的显然是二进制，不是稿件。
        if "\x00" in text:
            continue
        return _normalize_newlines(text), encoding
    raise TextDecodeError(path)


def read_text_file(path: Path | str) -> tuple[str, str]:
    """读取用户文本文件，返回 `(text, encoding)`。"""
    p = Path(path)
    return decode_text(p.read_bytes(), p)
