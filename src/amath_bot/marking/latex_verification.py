from typing import Any

import sympy  # type: ignore[import-untyped]
from sympy.parsing.latex import parse_latex  # type: ignore[import-untyped]


def _residual(expression: Any) -> Any:
    if isinstance(expression, sympy.Equality):
        return expression.lhs - expression.rhs
    return expression


def verify_latex_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Best-effort parse and transition checks; parser failures never reject OCR."""
    results: list[dict[str, Any]] = []
    parsed: list[Any | None] = []
    for line in lines:
        try:
            expression = parse_latex(str(line["latex"]), strict=True)
        except Exception as error:  # noqa: BLE001 - parser limitations are recorded, not fatal
            parsed.append(None)
            results.append(
                {
                    "line_id": line["id"],
                    "parse_status": "unverified",
                    "parse_error": f"{type(error).__name__}: {error}"[:500],
                }
            )
        else:
            parsed.append(expression)
            results.append({"line_id": line["id"], "parse_status": "parsed"})
    for index in range(1, len(parsed)):
        previous, current = parsed[index - 1], parsed[index]
        if previous is None or current is None:
            results[index]["transition_status"] = "unverified"
            continue
        try:
            equivalent = sympy.simplify(_residual(previous) - _residual(current)) == 0
            results[index]["transition_status"] = (
                "equivalent" if bool(equivalent) else "not_equivalent"
            )
        except Exception as error:  # noqa: BLE001 - symbolic limits are diagnostic only
            results[index]["transition_status"] = "unverified"
            results[index]["transition_error"] = f"{type(error).__name__}: {error}"[:500]
    return results
