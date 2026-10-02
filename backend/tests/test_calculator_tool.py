import json

import pytest
from pydantic import ValidationError

from app.tools import CalculatorTool, ToolArgumentsError, ToolExecutionError, ToolRegistry
from app.tools.calculator import MAX_EXPRESSION_LENGTH, CalculatorInput, CalculatorOutput, evaluate


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("25 * 800 / 100", 200),
        ("2 + 3 * 4", 14),
        ("(2 + 3) * 4", 20),
        ("10 / 4", 2.5),
        ("7 // 2", 3),
        ("7 % 3", 1),
        ("2 ** 10", 1024),
        ("-5 + +2", -3),
        ("1.5 * 2", 3),
        ("0.1 + 0.2", 0.1 + 0.2),
        ("  1 + 1  ", 2),
        ("10 ** 100", 10**100),
        ("2 ** -1", 0.5),
    ],
)
def test_evaluate_valid_expressions(expression: str, expected: float) -> None:
    assert evaluate(expression) == expected


def test_whole_number_results_are_returned_as_int() -> None:
    result = evaluate("25 * 800 / 100")

    assert result == 200
    assert isinstance(result, int)


@pytest.mark.anyio
async def test_calculator_tool_returns_result_model() -> None:
    output = await CalculatorTool().run(CalculatorInput(expression="25 * 800 / 100"))

    assert output == CalculatorOutput(result=200)
    assert output.model_dump_json() == '{"result":200}'


@pytest.mark.anyio
async def test_calculator_via_registry_with_json_arguments() -> None:
    registry = ToolRegistry([CalculatorTool()])

    output = await registry.execute("calculator", json.dumps({"expression": "25 * 800 / 100"}))

    assert output.model_dump() == {"result": 200}


@pytest.mark.parametrize(
    "expression",
    [
        "__import__('os').system('echo pwned')",
        "open('/etc/passwd').read()",
        "abs(-1)",
        "x + 1",
        "(1).real",
        "().__class__",
        "True + 1",
        "1j * 2",
        "'a' * 3",
        "[1, 2]",
        "1 if 1 else 0",
        "lambda: 1",
        "1 < 2",
        "2 ^ 3",
        "~1",
        "(x := 1)",
    ],
)
def test_evaluate_rejects_anything_but_arithmetic(expression: str) -> None:
    with pytest.raises(ToolArgumentsError, match="Unsupported expression"):
        evaluate(expression)


@pytest.mark.parametrize("expression", ["1 +", "2 * (3", "import os", "1; 2", "1 = 1"])
def test_evaluate_rejects_invalid_syntax(expression: str) -> None:
    with pytest.raises(ToolArgumentsError, match="Invalid expression syntax"):
        evaluate(expression)


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        ("1 / 0", "Division by zero"),
        ("5 % 0", "Division by zero"),
        ("9 ** 9 ** 9", "Result is too large"),
        ("10 ** 101", "Result is too large"),
        ("10 ** 60 * 10 ** 60", "Result is too large"),
        ("0.1 ** -400", "Result is too large"),
        ("1e999", "Result is not a finite number"),
        ("(-8) ** 0.5", "Result is not a real number"),
    ],
)
def test_evaluate_reports_math_errors(expression: str, message: str) -> None:
    with pytest.raises(ToolExecutionError, match=message):
        evaluate(expression)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"expression": ""},
        {"expression": "   "},
        {"expression": 42},
        {"expression": "1" * (MAX_EXPRESSION_LENGTH + 1)},
        {"expression": "1 + 1", "code": "print(1)"},
    ],
)
def test_calculator_input_rejects_invalid_arguments(arguments: dict) -> None:
    with pytest.raises(ValidationError):
        CalculatorInput.model_validate(arguments)


def test_calculator_input_schema_describes_expression() -> None:
    schema = CalculatorInput.model_json_schema()

    assert schema["required"] == ["expression"]
    assert schema["properties"]["expression"]["type"] == "string"
    assert schema["additionalProperties"] is False
