import ast
import math
import operator
from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.tools.errors import ToolArgumentsError, ToolExecutionError

Number = int | float

MAX_EXPRESSION_LENGTH = 200
# Bounds every intermediate value, so no operation can build huge integers or hang the server.
MAX_MAGNITUDE = 10**100
_MAX_DIGITS = 100

_BINARY_OPERATORS: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS: dict[type[ast.unaryop], Callable[[Number], Number]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

_UNSUPPORTED_MESSAGE = (
    "Unsupported expression: only numbers, parentheses and the operators + - * / // % ** are allowed"
)


class CalculatorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_EXPRESSION_LENGTH),
        Field(description="Arithmetic expression to evaluate, e.g. '25 * 800 / 100'"),
    ]


class CalculatorOutput(BaseModel):
    result: Number


class CalculatorTool:
    name = "calculator"
    description = (
        "Evaluate an arithmetic expression and return the exact result. Supports numbers, "
        "parentheses and the operators + - * / // % ** (power). "
        "Use it for any arithmetic instead of calculating yourself."
    )
    input_model = CalculatorInput

    async def run(self, arguments: CalculatorInput) -> CalculatorOutput:
        return CalculatorOutput(result=evaluate(arguments.expression))


def evaluate(expression: str) -> Number:
    """Safely evaluate an arithmetic expression without `eval`, by walking a whitelisted AST."""
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError:
        raise ToolArgumentsError(f"Invalid expression syntax: {expression!r}") from None

    try:
        result = _evaluate_node(tree.body)
    except ZeroDivisionError:
        raise ToolExecutionError("Division by zero") from None
    except OverflowError:
        raise ToolExecutionError("Result is too large") from None

    if isinstance(result, float) and result.is_integer():
        return int(result)
    return result


def _evaluate_node(node: ast.expr) -> Number:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return _checked(node.value)

    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        if isinstance(node.op, ast.Pow):
            _check_power(left, right)
        return _checked(_BINARY_OPERATORS[type(node.op)](left, right))

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _checked(_UNARY_OPERATORS[type(node.op)](_evaluate_node(node.operand)))

    raise ToolArgumentsError(_UNSUPPORTED_MESSAGE)


def _check_power(base: Number, exponent: Number) -> None:
    # Checked before computing, because e.g. 9 ** 999999 is expensive to calculate at all.
    if abs(base) > 1 and exponent > 0 and exponent * math.log10(abs(base)) > _MAX_DIGITS:
        raise ToolExecutionError("Result is too large")


def _checked(value: object) -> Number:
    if not isinstance(value, (int, float)):
        raise ToolExecutionError("Result is not a real number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ToolExecutionError("Result is not a finite number")
    if abs(value) > MAX_MAGNITUDE:
        raise ToolExecutionError("Result is too large")
    return value
