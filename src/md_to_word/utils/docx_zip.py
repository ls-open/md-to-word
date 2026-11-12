"""把 .docx 压缩包的元数据钉死，使同一份稿件重复导出得到逐字节一致的文件。

python-docx 存盘时给每个 zip 条目写当前时刻，于是"内容一个字没改"的两次导出在 Git 里
也是两个不同的二进制对象。这里重写一遍压缩包，条目内容原样搬运，只把时间戳、权限与
条目顺序换成固定值。

时间取 1980-01-01：这是 DOS 时间的起点，也是 zip 格式能表示的最早时刻，一眼看得出是
钉死的值，不会和真实时间混淆。
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_PERMS = 0o100644 << 16  # 标准常规文件权限 -rw-r--r--，消除跨平台 umask 差异


def _opc_sort_key(filename: str) -> tuple[int, str]:
    """条目写入顺序：`[Content_Types].xml`、`_rels/.rels`、其余按路径升序。

    OPC 未规定 ZIP 条目顺序，读取器通过中央目录定位，顺序不影响 Word 打开（已实测）。
    固定顺序的作用是让包的布局只取决于内容，与写入环境无关。
    """
    if filename == "[Content_Types].xml":
        return (0, "")
    if filename == "_rels/.rels":
        return (1, "")
    if filename.startswith("_rels/"):
        return (2, filename)
    return (3, filename)


def normalize_zip(path: Path | str) -> None:
    """原地重写压缩包，把时间戳、权限与条目顺序都换成固定值。"""
    path = Path(path)
    tmp = path.with_name(path.name + ".norm")
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        items = sorted(src.infolist(), key=lambda it: _opc_sort_key(it.filename))
        for item in items:
            info = zipfile.ZipInfo(item.filename, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = FIXED_PERMS
            # `create_system` 决定中央目录里那一个字节：Python 在 Windows 上写 0（FAT），
            # 其它平台写 3（Unix）。不钉死的话，同一份稿件在 Windows 与 macOS 上导出的
            # 两个 .docx 内容一字不差、字节却不一致——「逐字节可复现」就只在单机上成立。
            # 3 与 `external_attr` 里那组 Unix 权限是配套的，统一按它写。
            info.create_system = 3
            dst.writestr(info, src.read(item.filename))
    shutil.move(str(tmp), str(path))
