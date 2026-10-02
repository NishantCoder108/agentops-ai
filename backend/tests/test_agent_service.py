import json

import pytest

from app.agent import DEFAULT_SYSTEM_PROMPT, AgentMaxStepsExceededError, AgentService
from app.core.exceptions import AppError
from app.llm import ChatMessage, LLMProvider, LLMProviderError, ToolCall
from app.tools import CalculatorTool, ToolRegistry
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response

pytestmark = pytest.mark.anyio


def calculator_call(expression: str, call_id: str = "call_1") -> ToolCall:
    return ToolCall(id=call_id, name="calculator", arguments=json.dumps({"expression": expression}))


def calculator_agent(provider: FakeLLMProvider, **kwargs: int) -> AgentService:
    return AgentService(provider, ToolRegistry([CalculatorTool()]), **kwargs)


@pytest.fixture
def provider() -> FakeLLMProvider:
    return FakeLLMProvider(reply="Hi there!")


@pytest.fixture
def agent(provider: FakeLLMProvider) -> AgentService:
    typed_provider: LLMProvider = provider
    return AgentService(typed_provider)


async def test_run_returns_model_answer(agent: AgentService) -> None:
    assert await agent.run("Hello") == "Hi there!"


async def test_run_sends_system_prompt_and_user_message(
    agent: AgentService, provider: FakeLLMProvider
) -> None:
    await agent.run("Hello")

    assert len(provider.calls) == 1
    assert provider.calls[0]["messages"] == [
        ChatMessage(role="system", content=DEFAULT_SYSTEM_PROMPT),
        ChatMessage(role="user", content="Hello"),
    ]


async def test_run_uses_custom_system_prompt(provider: FakeLLMProvider) -> None:
    agent = AgentService(provider, system_prompt="Reply in French.")

    await agent.run("Hello")

    assert provider.calls[0]["messages"][0] == ChatMessage(role="system", content="Reply in French.")


async def test_run_rejects_empty_message(agent: AgentService, provider: FakeLLMProvider) -> None:
    with pytest.raises(AppError) as exc_info:
        await agent.run("   ")

    assert exc_info.value.code == "invalid_message"
    assert provider.calls == []


async def test_run_propagates_provider_errors() -> None:
    agent = AgentService(FakeLLMProvider(error=LLMProviderError("LLM provider returned an error")))

    with pytest.raises(LLMProviderError):
        await agent.run("Hello")


async def test_run_without_tools_offers_no_tools(agent: AgentService, provider: FakeLLMProvider) -> None:
    await agent.run("Hello")

    assert provider.calls[0]["tools"] is None


# --- tool-calling loop ---


async def test_run_offers_registered_tools_to_the_model() -> None:
    provider = FakeLLMProvider()

    await calculator_agent(provider).run("Hello")

    [definition] = provider.calls[0]["tools"]
    assert definition.name == "calculator"
    assert definition.description == CalculatorTool.description
    assert definition.parameters["properties"]["expression"]["type"] == "string"


async def test_answer_without_tool_call_needs_one_llm_call() -> None:
    provider = FakeLLMProvider(responses=[answer_response("Hi!")])

    assert await calculator_agent(provider).run("Hello") == "Hi!"
    assert len(provider.calls) == 1


async def test_tool_call_flow_executes_tool_and_returns_final_answer() -> None:
    call = calculator_call("25 * 800 / 100")
    provider = FakeLLMProvider(
        responses=[tool_call_response(call), answer_response("25% of 800 is 200.")]
    )

    answer = await calculator_agent(provider).run("What is 25% of 800?")

    assert answer == "25% of 800 is 200."
    assert len(provider.calls) == 2
    assert provider.calls[1]["messages"] == [
        ChatMessage(role="system", content=DEFAULT_SYSTEM_PROMPT),
        ChatMessage(role="user", content="What is 25% of 800?"),
        ChatMessage(role="assistant", content=None, tool_calls=[call]),
        ChatMessage(role="tool", tool_call_id="call_1", content='{"result":200}'),
    ]


async def test_multiple_tool_calls_in_one_turn_are_all_answered_in_order() -> None:
    provider = FakeLLMProvider(
        responses=[
            tool_call_response(calculator_call("2 + 2", "call_a"), calculator_call("3 * 3", "call_b")),
            answer_response("4 and 9"),
        ]
    )

    assert await calculator_agent(provider).run("2+2 and 3*3?") == "4 and 9"

    tool_messages = [m for m in provider.calls[1]["messages"] if m.role == "tool"]
    assert [(m.tool_call_id, m.content) for m in tool_messages] == [
        ("call_a", '{"result":4}'),
        ("call_b", '{"result":9}'),
    ]


async def test_sequential_tool_calls_across_steps() -> None:
    provider = FakeLLMProvider(
        responses=[
            tool_call_response(calculator_call("25 * 800 / 100", "call_1")),
            tool_call_response(calculator_call("200 + 50", "call_2")),
            answer_response("250"),
        ]
    )

    assert await calculator_agent(provider).run("25% of 800, plus 50?") == "250"
    assert len(provider.calls) == 3
    assert provider.calls[2]["messages"][-1] == ChatMessage(
        role="tool", tool_call_id="call_2", content='{"result":250}'
    )


@pytest.mark.parametrize(
    ("call", "expected_error"),
    [
        (
            ToolCall(id="call_1", name="calculator", arguments='{"expr": "1 + 1"}'),
            "Invalid arguments for tool 'calculator'",
        ),
        (ToolCall(id="call_1", name="calculator", arguments="not json"), "Invalid arguments for tool 'calculator'"),
        (calculator_call("__import__('os').system('ls')"), "Unsupported expression"),
        (calculator_call("1 / 0"), "Division by zero"),
        (ToolCall(id="call_1", name="python_exec", arguments="{}"), "Unknown tool: 'python_exec'"),
    ],
)
async def test_tool_errors_are_returned_to_the_model(call: ToolCall, expected_error: str) -> None:
    provider = FakeLLMProvider(
        responses=[tool_call_response(call), answer_response("Sorry, I could not calculate that.")]
    )

    answer = await calculator_agent(provider).run("Calculate something")

    assert answer == "Sorry, I could not calculate that."
    tool_message = provider.calls[1]["messages"][-1]
    assert tool_message.role == "tool"
    assert tool_message.tool_call_id == "call_1"
    assert tool_message.content is not None
    assert expected_error in json.loads(tool_message.content)["error"]


async def test_invalid_arguments_error_includes_validation_details() -> None:
    call = ToolCall(id="call_1", name="calculator", arguments="{}")
    provider = FakeLLMProvider(responses=[tool_call_response(call), answer_response("ok")])

    await calculator_agent(provider).run("Calculate")

    content = provider.calls[1]["messages"][-1].content
    assert json.loads(content)["details"] == [{"loc": ["expression"], "msg": "Field required"}]


async def test_run_stops_after_max_steps() -> None:
    provider = FakeLLMProvider(
        responses=[tool_call_response(calculator_call("1 + 1", f"call_{i}")) for i in range(10)]
    )

    with pytest.raises(AgentMaxStepsExceededError):
        await calculator_agent(provider, max_steps=3).run("Loop forever")

    assert len(provider.calls) == 3
