import json

import pytest

from app.agent.events import AgentDone, AgentStatus, AgentToken
from app.agent.service import AgentService
from app.llm.streaming import LLMStreamPart
from app.llm.types import ChatMessage, LLMResponse, ToolCall, ToolDefinition
from app.tools import CalculatorTool, ToolRegistry

pytestmark = pytest.mark.anyio


class _StreamingProvider:
    name = "stream"

    def __init__(self, steps: list[list[LLMStreamPart]]) -> None:
        self.steps = [list(step) for step in steps]
        self.calls: list[list[ChatMessage]] = []

    async def stream(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolDefinition] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        del tools, model, temperature, max_tokens
        self.calls.append(list(messages))
        for part in self.steps.pop(0):
            yield part

    async def generate(self, messages: list[ChatMessage], **_: object) -> LLMResponse:
        raise AssertionError(messages)

    async def aclose(self) -> None:
        return None


def _calculator_step() -> list[LLMStreamPart]:
    call = ToolCall(id="call_1", name="calculator", arguments=json.dumps({"expression": "2 + 2"}))
    return [
        LLMStreamPart(tool_name="calculator"),
        LLMStreamPart(
            response=LLMResponse(content="", model="fake", finish_reason="tool_calls", tool_calls=[call])
        ),
    ]


def _answer_step(text: str) -> list[LLMStreamPart]:
    return [
        LLMStreamPart(text=text[:2]),
        LLMStreamPart(text=text[2:]),
        LLMStreamPart(response=LLMResponse(content=text, model="fake", finish_reason="stop")),
    ]


async def test_stream_yields_tool_status_then_answer_tokens() -> None:
    provider = _StreamingProvider([_calculator_step(), _answer_step("Four")])
    agent = AgentService(provider, ToolRegistry([CalculatorTool()]))

    events = [event async for event in agent.stream("What is 2 + 2?")]

    assert [type(event) for event in events] == [
        AgentStatus,
        AgentStatus,
        AgentStatus,
        AgentStatus,
        AgentToken,
        AgentToken,
        AgentDone,
    ]
    assert events[0] == AgentStatus(status="thinking")
    assert events[1] == AgentStatus(status="tool", tool="calculator")
    assert events[2] == AgentStatus(status="thinking")
    assert events[3] == AgentStatus(status="generating")
    assert events[4] == AgentToken(text="Fo")
    assert events[5] == AgentToken(text="ur")
    done = events[6]
    assert isinstance(done, AgentDone)
    assert done.response.answer == "Four"
    assert done.response.tools_used == ["calculator"]
    assert done.response.sources == []


async def test_stream_replaces_a_citation_envelope_with_the_plain_answer() -> None:
    envelope = json.dumps({"answer": "96", "document_ids": []})
    provider = _StreamingProvider(
        [
            [
                LLMStreamPart(text=envelope),
                LLMStreamPart(response=LLMResponse(content=envelope, model="fake", finish_reason="stop")),
            ]
        ]
    )
    agent = AgentService(provider, ToolRegistry([CalculatorTool()]))

    events = [event async for event in agent.stream("What is 12 * 8?")]

    tokens = [event for event in events if isinstance(event, AgentToken)]
    assert tokens == [AgentToken(text="96", replace=True)]
    assert any(isinstance(event, AgentStatus) and event.status == "generating" for event in events)
    done = events[-1]
    assert isinstance(done, AgentDone)
    assert done.response.answer == "96"


async def test_closing_the_stream_before_the_model_responds_stops() -> None:
    provider = _StreamingProvider([[LLMStreamPart(text="Hi"), LLMStreamPart(response=LLMResponse(content="Hi", model="fake"))]])
    agent = AgentService(provider)
    stream = agent.stream("Hello")

    first = await anext(stream)
    assert first == AgentStatus(status="thinking")
    await stream.aclose()

    assert provider.calls == []
