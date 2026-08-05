import pytest

from amath_bot.marking.symbolic import UnsupportedExpression, equivalent


def test_equivalent_factorised_and_expanded_forms() -> None:
    assert equivalent("(x-2)*(x-3)", "x**2-5*x+6") is True


def test_non_equivalent_expressions_return_false() -> None:
    assert equivalent("x**2", "x**3") is False


@pytest.mark.parametrize(
    "unsafe",
    ["__import__('os')", "x.__class__", "open('/tmp/x')", "x**999999"],
)
def test_unsafe_expression_is_rejected(unsafe: str) -> None:
    with pytest.raises(UnsupportedExpression):
        equivalent(unsafe, "0")
