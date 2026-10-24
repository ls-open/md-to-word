"""PDF 图 → Word 能放进内联图片的位图（Word 只认位图，这是格式的硬限制）。

学术稿的图大多出自 matplotlib、MATLAB、Origin、Visio、TikZ，默认导出就是 PDF，
所以转换在导出时做掉：按目标版面的 300 dpi 渲染第 1 页。多页 PDF 由门禁另有提醒。
"""

from __future__ import annotations

import hashlib
import os
import struct
import tempfile
import zlib
from pathlib import Path

# 期刊对位图的要求线。低于这条线，印刷上会看出来；再高只是变大文件。
DEFAULT_DPI = 300

# Word（经 python-docx）认得的内联图片格式。除此之外一律在门禁拦下，
# 否则 python-docx 会抛 UnrecognizedImageError——一屏 traceback、没有行号。
RASTER_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"})
PDF_SUFFIX = ".pdf"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# 缓存是进程级的：一份稿里同一张图常被引用多次，光栅化却只该做一次。两道闸都要有——
# 只限条目数的话，满页 300 dpi 的图一张就好几 MB，128 条能吃到几百 MB。
_CACHE_MAX_ENTRIES = 128
_CACHE_MAX_BYTES = 64 * 1024 * 1024
_png_cache: dict[tuple[str, float | None, int], bytes] = {}
_CACHE_BYTES = 0


def clear_cache() -> None:
    """清空位图渲染内存缓存（供测试或资源回收使用）。"""
    global _CACHE_BYTES
    _png_cache.clear()
    _CACHE_BYTES = 0


class PdfFigureError(Exception):
    """PDF 打不开、没有页面，或者渲染失败。消息是给作者看的原因，不是 traceback。"""


def is_pdf(path: Path | str) -> bool:
    return Path(path).suffix.lower() == PDF_SUFFIX


def page_count(path: Path | str) -> int:
    """PDF 的页数。打不开时抛 `PdfFigureError`。"""
    pdf = _open(path)
    try:
        return len(pdf)
    finally:
        pdf.close()


def rasterize(path: Path | str, width_cm: float | None = None, dpi: int = DEFAULT_DPI) -> Path:
    """渲染第 1 页到临时 PNG，返回路径（调用方负责删除）。

    给了 `width_cm` 就按「成品里这么宽需要多少像素」反算，声明宽度上正好是 `dpi`；
    没给就按页面物理尺寸渲染，并把 `dpi` 写进 PNG，让 python-docx 还原同一尺寸。

    按「文件内容 + 宽度 + dpi」做内存缓存：命中时省掉的是光栅化，读文件与算哈希照付；
    换的是不必猜文件有没有改过。
    """
    path_obj = Path(path)
    try:
        content = path_obj.read_bytes()
    except OSError as exc:
        raise PdfFigureError(str(exc)) from exc
    cache_key = (hashlib.sha256(content).hexdigest(), width_cm, dpi)

    if cache_key in _png_cache:
        png = _png_cache[cache_key]
    else:
        pdf = _open(path_obj)
        try:
            if len(pdf) == 0:
                raise PdfFigureError("the document has no pages")
            page = pdf[0]
            width_pt, _ = page.get_size()
            if width_pt <= 0:
                raise PdfFigureError("page width is zero")
            if width_cm and width_cm > 0:
                target_px = max(1, round(width_cm / 2.54 * dpi))
                scale = target_px / width_pt
            else:
                scale = dpi / 72.0
            try:
                bitmap = page.render(scale=scale, rev_byteorder=True)
            except Exception as exc:  # PDFium 的异常类型随版本变，统一折成一句可读原因
                raise PdfFigureError(str(exc) or type(exc).__name__) from exc
            png = _png_bytes(bitmap.width, bitmap.height, bitmap.buffer, bitmap.stride, dpi)
        finally:
            pdf.close()

        global _CACHE_BYTES
        while _png_cache and (
            len(_png_cache) >= _CACHE_MAX_ENTRIES
            or _CACHE_BYTES + len(png) > _CACHE_MAX_BYTES
        ):
            oldest = next(iter(_png_cache))
            _CACHE_BYTES -= len(_png_cache.pop(oldest))
        _png_cache[cache_key] = png
        _CACHE_BYTES += len(png)

    fd, name = tempfile.mkstemp(prefix="md-to-word-fig-", suffix=".png")
    try:
        os.write(fd, png)
    finally:
        os.close(fd)
    return Path(name)


def _open(path: Path | str):
    try:
        import pypdfium2 as pdfium
    except ModuleNotFoundError as exc:  # 依赖被裁掉的环境：说清楚装什么
        raise PdfFigureError("pypdfium2 is not installed (pip install pypdfium2)") from exc
    try:
        return pdfium.PdfDocument(str(path))
    except Exception as exc:
        raise PdfFigureError(str(exc) or type(exc).__name__) from exc


def _png_bytes(width: int, height: int, rgb, stride: int, dpi: int) -> bytes:
    """RGB 缓冲区 → PNG。借 zlib，不拉 Pillow；不写时间戳，同一份 PDF 每次字节一致。

    `pHYs` 块是给 python-docx 读的：它按 PNG 里的 DPI 还原物理尺寸，缺了会按 72 dpi 算，
    图在版面上大出四倍。
    """
    raw = bytearray()
    data = bytes(rgb)
    for y in range(height):
        raw.append(0)  # 每行的 filter type：None
        raw += data[y * stride : y * stride + width * 3]

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    pixels_per_metre = round(dpi / 0.0254)
    return (
        _PNG_SIGNATURE
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"pHYs", struct.pack(">IIB", pixels_per_metre, pixels_per_metre, 1))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
