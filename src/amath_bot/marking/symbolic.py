import ast
from collections.abc import Callable
from typing import Any

import sympy  # type: ignore[import-untyped]


class UnsupportedExpression(ValueError):
    pass


_FUNCTIONS: dict[str, Callable[[Any], Any]] = {
    "sqrt": sympy.sqrt,
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "exp": sympy.exp,
    "log": sympy.log,
}
_CONSTANTS: dict[str, Any] = {"pi": sympy.pi, "e": sympy.E}
_MAX_CHARACTERS = 500
_MAX_NODES = 100
_MAX_POWER = 20


def _parse(expression: str) -> Any:
    if len(expression) > _MAX_CHARACTERS:
        raise UnsupportedExpression("expression is too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as error:
        raise UnsupportedExpression("invalid expression syntax") from error
    if sum(1 for _ in ast.walk(tree)) > _MAX_NODES:
        raise UnsupportedExpression("expression is too complex")
    return _build(tree.body)


def _build(node: ast.AST) -> Any:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        if abs(node.value) > 1_000_000:
            raise UnsupportedExpression("numeric literal is too large")
        return sympy.Integer(node.value) if isinstance(node.value, int) else sympy.Float(node.value)
    if isinstance(node, ast.Name):
        if node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if not node.id.isalpha() or len(node.id) > 3:
            raise UnsupportedExpression(f"unsupported symbol: {node.id}")
        return sympy.Symbol(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _build(node.operand)
        return value if isinstance(node.op, ast.UAdd) else -value
    if isinstance(node, ast.BinOp):
        left = _build(node.left)
        right = _build(node.right)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        if isinstance(node.op, ast.Pow):
            if not isinstance(node.right, ast.Constant) or not isinstance(
                node.right.value, (int, float)
            ):
                raise UnsupportedExpression("power must be a bounded numeric literal")
            if abs(node.right.value) > _MAX_POWER:
                raise UnsupportedExpression("power is too large")
            return left**right
        raise UnsupportedExpression("unsupported binary operator")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        function = _FUNCTIONS.get(node.func.id)
        if function is None or len(node.args) != 1 or node.keywords:
            raise UnsupportedExpression("unsupported function call")
        return function(_build(node.args[0]))
    raise UnsupportedExpression(f"unsupported syntax: {type(node).__name__}")


def equivalent(left: str, right: str) -> bool:
    left_expression = _parse(left)
    right_expression = _parse(right)
    try:
        return bool(sympy.simplify(left_expression - right_expression) == 0)
    except (ArithmeticError, TypeError, ValueError) as error:
        raise UnsupportedExpression("expression could not be safely simplified") from error
