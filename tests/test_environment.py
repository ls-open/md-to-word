"""渲染引擎体检：版本策略与错误分级。

版本不锁死单点：低于最低版本硬失败（用到的 crossref/短代码行为那时还不存在），
高于验证过的版本只警告——对更新版本拒跑，等于把用户挡在门外。
"""

from __future__ import annotations

from unittest.mock import patch

from md_to_word.renderer.quarto import (
    MIN_QUARTO_VERSION,
    TESTED_QUARTO_VERSION,
    _parse_version,
    check_quarto_environment,
)


def test_parse_version_handles_common_output() -> None:
    assert _parse_version("1.10.18") == (1, 10, 18)
    assert _parse_version("1.4") == (1, 4)
    assert _parse_version("quarto 1.6.42\n") == (1, 6, 42)
    assert _parse_version("not a version") is None


def test_version_bounds_are_ordered() -> None:
    assert MIN_QUARTO_VERSION <= TESTED_QUARTO_VERSION


def test_missing_quarto_is_an_error() -> None:
    with patch("md_to_word.renderer.quarto.shutil.which", return_value=None):
        version, errors, warnings = check_quarto_environment()
    assert version is None
    assert errors and "quarto" in errors[0].lower()
    assert not warnings


def test_too_old_is_an_error() -> None:
    with patch("md_to_word.renderer.quarto.shutil.which", return_value="/usr/bin/quarto"), \
         patch("md_to_word.renderer.quarto.read_quarto_version", return_value=(1, 3, 9)):
        _version, errors, _warnings = check_quarto_environment()
    assert errors and "低于最低要求" in errors[0]


def test_newer_than_tested_only_warns() -> None:
    newer = (TESTED_QUARTO_VERSION[0], TESTED_QUARTO_VERSION[1] + 1, 0)
    with patch("md_to_word.renderer.quarto.shutil.which", return_value="/usr/bin/quarto"), \
         patch("md_to_word.renderer.quarto.read_quarto_version", return_value=newer):
        _version, errors, warnings = check_quarto_environment()
    assert not errors, "比验证过的版本新不应阻断导出"
    assert warnings
