import json

import pytest
from pydantic import BaseModel, ConfigDict

from app.tools import (
    CalculatorTool,
    ToolArgumentsError,
    ToolExecutionError,
    ToolNotFoundError,
    ToolRegistry,
    create_default_tool_registry,
)


class EchoInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str


class EchoOutput(BaseModel):
    text: str


class EchoTool:
    name = "echo"
    description = "Echo the input text."
    input_model = EchoInput

    async def run(self, arguments: EchoInput) -> EchoOutput:
        return EchoOutput(text=arguments.text)


class BrokenTool:
    name = "broken"
    description = "Always fails with an unexpected error."
    input_model = EchoInput

    async def run(self, arguments: EchoInput) -> EchoOutput:
        raise RuntimeError("secret internal detail")


class FailingTool:
    name = "failing"
    description = "Fails with an expected tool error."
    input_model = EchoInput

    async def run(self, arguments: EchoInput) -> EchoOutput:
        raise ToolExecutionError("Upstream service unavailable")


# --- registration and lookup ---


def test_register_and_get_tool() -> None:
    registry = ToolRegistry()
    tool = EchoTool()

    registry.register(tool)

    assert registry.get("echo") is tool
    assert "echo" in registry
    assert len(registry) == 1
    assert registry.list_tools() == [tool]


def test_registry_accepts_tools_in_constructor() -> None:
    registry = ToolRegistry([EchoTool(), CalculatorTool()])

    assert [tool.name for tool in registry.list_tools()] == ["echo", "calculator"]


def test_register_rejects_duplicate_name() -> None:
    registry = ToolRegistry([EchoTool()])

    with pytest.raises(ValueError, match="already registered"):
        registry.register(EchoTool())


@pytest.mark.parametrize("name", ["", "has space", "dots.not.allowed", "x" * 65])
def test_register_rejects_invalid_name(name: str) -> None:
    tool = EchoTool()
    tool.name = name

    with pytest.raises(ValueError, match="Invalid tool name"):
        ToolRegistry().register(tool)


def test_get_unknown_tool_raises_not_found() -> None:
    registry = ToolRegistry([EchoTool()])

    with pytest.raises(ToolNotFoundError, match="Unknown tool: 'missing'"):
        registry.get("missing")
    assert "missing" not in registry


def test_default_registry_contains_calculator() -> None:
    registry = create_default_tool_registry()

    assert isinstance(registry.get("calculator"), CalculatorTool)


# --- execution ---


@pytest.mark.asyncio
async def test_execute_validates_arguments_and_runs_tool() -> None:
    registry = ToolRegistry([EchoTool()])

    output = await registry.execute("echo", json.dumps({"text": "hi"}))

    assert output == EchoOutput(text="hi")


@pytest.mark.asyncio
async def test_execute_unknown_tool_raises_not_found() -> None:
    with pytest.raises(ToolNotFoundError):
        await ToolRegistry().execute("missing", "{}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_arguments",
    [
        "not json",
        "",
        "{}",
        json.dumps({"text": 123}),
        json.dumps({"text": "hi", "extra": True}),
        json.dumps(["hi"]),
    ],
)
async def test_execute_rejects_invalid_arguments(raw_arguments: str) -> None:
    registry = ToolRegistry([EchoTool()])

    with pytest.raises(ToolArgumentsError) as exc_info:
        await registry.execute("echo", raw_arguments)

    assert exc_info.value.message == "Invalid arguments for tool 'echo'"
    assert exc_info.value.details


@pytest.mark.asyncio
async def test_execute_passes_through_expected_tool_errors() -> None:
    registry = ToolRegistry([FailingTool()])

    with pytest.raises(ToolExecutionError, match="Upstream service unavailable"):
        await registry.execute("failing", json.dumps({"text": "hi"}))


@pytest.mark.asyncio
async def test_execute_hides_unexpected_tool_errors() -> None:
    registry = ToolRegistry([BrokenTool()])

    with pytest.raises(ToolExecutionError) as exc_info:
        await registry.execute("broken", json.dumps({"text": "hi"}))

    assert exc_info.value.message == "Tool 'broken' failed"
    assert "secret" not in exc_info.value.message
