import json
import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.errors import AgentMaxStepsExceededError
from app.agent.grounding import (
    KNOWLEDGE_ANSWER_INSTRUCTIONS,
    KNOWLEDGE_TOOL_NAME,
    RetrievedPassage,
    answer_without_search,
    ground_answer,
    passages_from_tool_result,
)
from app.agent.tracking import RunTracker
from app.core.exceptions import AppError
from app.llm.base import LLMProvider
from app.llm.types import ChatMessage, ToolCall, ToolDefinition
from app.schemas.agent import AgentResponse
from app.tools.errors import ToolError
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are AgentOps AI, a helpful enterprise knowledge assistant. "
    "Answer clearly and concisely. If you do not know the answer, say so. "
    "When one of your tools can answer part of a question exactly, call it instead of guessing."
)
DEFAULT_MAX_STEPS = 5


def _utc_today() -> date:
    return datetime.now(UTC).date()


class AgentService:
    """Agent orchestration: runs the LLM / tool-call loop.

    Depends only on the LLMProvider interface and the ToolRegistry, never on HTTP or a concrete provider.
    """

    def __init__(
        self,
        provider: LLMProvider,
        tools: ToolRegistry | None = None,
        *,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_steps: int = DEFAULT_MAX_STEPS,
        today: Callable[[], date] = _utc_today,
    ) -> None:
        self._provider = provider
        self._tools = tools if tools is not None else ToolRegistry()
        self._system_prompt = system_prompt
        self._max_steps = max_steps
        self._today = today
        self.run_id: uuid.UUID | None = None

    async def run(
        self,
        message: str,
        *,
        session: AsyncSession | None = None,
        conversation_id: uuid.UUID | None = None,
    ) -> AgentResponse:
        if not message.strip():
            raise AppError("Message must not be empty", code="invalid_message", status_code=422)
        if (session is None) != (conversation_id is None):
            raise ValueError("session and conversation_id must be provided together")

        tracker = RunTracker(session, conversation_id) if session is not None and conversation_id is not None else None
        if tracker is not None:
            await tracker.start(message)
            self.run_id = tracker.run_id

        messages = [
            ChatMessage(role="system", content=self.system_message()),
            ChatMessage(role="user", content=message),
        ]
        tool_definitions = self._tool_definitions() or None
        tools_used: list[str] = []
        passages: list[RetrievedPassage] = []

        try:
            for _ in range(self._max_steps):
                response = await self._provider.generate(messages, tools=tool_definitions)
                if not response.tool_calls:
                    result = self._final_response(response.content, tools_used, passages)
                    if tracker is not None:
                        await tracker.complete(result.answer)
                    return result

                messages.append(
                    ChatMessage(
                        role="assistant",
                        content=response.content or None,
                        tool_calls=response.tool_calls,
                    )
                )
                for call in response.tool_calls:
                    content = await self._run_tool(call, tracker)
                    if call.name not in tools_used:
                        tools_used.append(call.name)
                    if call.name == KNOWLEDGE_TOOL_NAME:
                        passages.extend(passages_from_tool_result(content))
                    messages.append(ChatMessage(role="tool", tool_call_id=call.id, content=content))
        except Exception:
            if tracker is not None:
                await self._record_failure(tracker)
            raise

        if tracker is not None:
            await self._record_failure(tracker)
        raise AgentMaxStepsExceededError(
            f"Agent did not produce a final answer within {self._max_steps} steps"
        )

    async def _record_failure(self, tracker: RunTracker) -> None:
        try:
            await tracker.fail()
        except Exception:
            logger.exception("Could not record agent run failure")

    def system_message(self) -> str:
        # The model has no clock; without the date it cannot resolve "last month" for analytics.
        prompt = self._system_prompt
        if any(tool.name == KNOWLEDGE_TOOL_NAME for tool in self._tools.list_tools()):
            prompt = f"{prompt}\n{KNOWLEDGE_ANSWER_INSTRUCTIONS}"
        return f"{prompt}\nToday's date is {self._today().isoformat()} (UTC)."

    def _final_response(
        self, content: str, tools_used: list[str], passages: list[RetrievedPassage]
    ) -> AgentResponse:
        if KNOWLEDGE_TOOL_NAME in tools_used:
            return ground_answer(content, passages, tools_used)
        return answer_without_search(content, tools_used)

    async def _run_tool(self, call: ToolCall, tracker: RunTracker | None) -> str:
        """Execute one tool call and return its JSON result, or a JSON error the model can react to."""
        logger.info("Agent calling tool %r", call.name)
        record = await tracker.start_tool(call.name, call.arguments) if tracker is not None else None
        try:
            output = await self._tools.execute(call.name, call.arguments)
        except ToolError as exc:
            logger.info("Tool %r returned an error: %s", call.name, exc.message)
            error: dict[str, object] = {"error": exc.message}
            if exc.details is not None:
                error["details"] = exc.details
            content = json.dumps(error)
        else:
            content = output.model_dump_json()
        if record is not None and tracker is not None:
            await tracker.finish_tool(record, content)
        return content

    def _tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_model.model_json_schema(),
            )
            for tool in self._tools.list_tools()
        ]
