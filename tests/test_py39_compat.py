"""Python 3.9 兼容性守卫。

`requires-python = ">=3.9"`，但 `Path | str` 这种写法（PEP 604）要到 3.10 才在运行时成立：
3.9 里函数注解是**定义时求值**的，一 import 就 `TypeError: unsupported operand type(s)`。
本机是 3.11，跑不出来；CI 的 3.9 任务会整片红。

规则很简单：用了 `X | Y` 注解的模块，必须 `from __future__ import annotations`。
这条测试把规则变成断言，免得再靠 CI 撞一次。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"


def _annotation_nodes(tree: ast.AST) -> list[ast.AST]:
    """所有出现在注解位置上的表达式节点。"""
    found: list[ast.AST] = []

    def take(node: ast.AST | None) -> None:
        if node is not None:
            found.append(node)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = node.args
            for arg in [*args.posonlyargs, *args.args, *args.kwonlyargs]:
                take(arg.annotation)
            for arg in (args.vararg, args.kwarg):
                if arg is not None:
                    take(arg.annotation)
            take(node.returns)
        elif isinstance(node, ast.AnnAssign):
            take(node.annotation)
    return found


def _modules() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_pep604_unions_need_future_annotations(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    if "from __future__ import annotations" in source:
        return
    tree = ast.parse(source)
    offenders = [
        node
        for annotation in _annotation_nodes(tree)
        for node in ast.walk(annotation)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
    ]
    assert not offenders, (
        f"{path.relative_to(SRC.parent.parent)} 在注解里用了 `X | Y`（PEP 604），"
        f"Python 3.9 会 ImportError。加一行 `from __future__ import annotations`。"
    )


@pytest.mark.parametrize("path", _modules(), ids=lambda p: str(p.relative_to(SRC)))
def test_no_python310_syntax(path: Path) -> None:
    """`match` 是 3.10 语法；3.9 上直接 SyntaxError。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not any(isinstance(n, ast.Match) for n in ast.walk(tree)), (
        f"{path.relative_to(SRC.parent.parent)} 用了 3.10 才有的 match 语句"
    )
