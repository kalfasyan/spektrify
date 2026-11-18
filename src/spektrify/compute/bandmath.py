"""Safe evaluation of band-math expressions (no ``eval``: a whitelisted AST walk)."""

from __future__ import annotations

import ast
import operator
from collections.abc import Callable
from typing import Any

import numpy as np

_BINOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
}
_CMPOPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}
_UNOPS: dict[type, Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Invert: operator.invert,
}


def safe_eval(expr: str, env: dict[str, Any]) -> Any:
    tree = ast.parse(expr.strip(), mode="eval")

    def ev(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise NameError(f"Unknown name {node.id!r}")
            return env[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
            return _BINOPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
            return _UNOPS[type(node.op)](ev(node.operand))
        if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _CMPOPS:
            return _CMPOPS[type(node.ops[0])](ev(node.left), ev(node.comparators[0])).astype(
                np.float32
            )
        if isinstance(node, ast.Subscript):
            return ev(node.value)[ev(node.slice)]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            fn = ev(node.func)
            if not callable(fn):
                raise TypeError(f"{node.func.id} is not a function")
            return fn(*[ev(a) for a in node.args])
        raise ValueError(f"Unsupported expression element: {ast.dump(node)[:60]}")

    return ev(tree)
