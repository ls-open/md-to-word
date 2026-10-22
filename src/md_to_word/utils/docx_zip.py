"""把 .docx 压缩包的元数据钉死，使同一份稿件重复导出得到逐字节一致的文件。

python-docx 存盘时给每个 zip 条目写当前时刻，于是"内容一个字没改"的两次导出在 Git 里
也是两个不同的二进制对象。这里重写一遍压缩包，只改时间戳，条目内容原样搬运。

时间取 1980-01-01：这是 DOS 时间的起点，也是 zip 格式能表示的最早时刻，一眼看得出是
钉死的值，不会和真实时间混淆。
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def normalize_zip(path: Path | str) -> None:
    """原地重写压缩包，把所有条目的时间戳改成固定值。"""
    path = Path(path)
    tmp = path.with_name(path.name + ".norm")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            info = zipfile.ZipInfo(item.filename, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = item.external_attr
            dst.writestr(info, src.read(item.filename))
    shutil.move(str(tmp), str(path))
