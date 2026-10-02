import json
import logging

from app.agent.errors import AgentMaxStepsExceededError
from app.core.exceptions import AppError
from app.llm.base import LLMProvider
from app.llm.types import ChatMessage, ToolCall, ToolDefinition
from app.tools.errors import ToolError
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = (
    "You are AgentOps AI, a helpful enterprise knowledge assistant. "
    "Answer clearly and concisely. If you do not know the answer, say so. "
    "When one of your tools can answer part of a question exactly, call it instead of guessing."
)
DEFAULT_MAX_STEPS = 5


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
    ) -> None:
        self._provider = provider
        self._tools = tools if tools is not None else ToolRegistry()
        self._system_prompt = system_prompt
        self._max_steps = max_steps

    async def run(self, message: str) -> str:
        if not message.strip():
            raise AppError("Message must not be empty", code="invalid_message", status_code=422)

        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=message),
        ]
        tool_definitions = self._tool_definitions() or None

        for _ in range(self._max_steps):
            response = await self._provider.generate(messages, tools=tool_definitions)
            if not response.tool_calls:
                return response.content

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content or None,
                    tool_calls=response.tool_calls,
                )
            )
            for call in response.tool_calls:
                messages.append(
                    ChatMessage(role="tool", tool_call_id=call.id, content=await self._run_tool(call))
                )

        raise AgentMaxStepsExceededError(
            f"Agent did not produce a final answer within {self._max_steps} steps"
        )

    async def _run_tool(self, call: ToolCall) -> str:
        """Execute one tool call and return its JSON result, or a JSON error the model can react to."""
        logger.info("Agent calling tool %r", call.name)
        try:
            output = await self._tools.execute(call.name, call.arguments)
        except ToolError as exc:
            logger.info("Tool %r returned an error: %s", call.name, exc.message)
            error: dict[str, object] = {"error": exc.message}
            if exc.details is not None:
                error["details"] = exc.details
            return json.dumps(error)
        return output.model_dump_json()

    def _tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description,
                parameters=tool.input_model.model_json_schema(),
            )
            for tool in self._tools.list_tools()
        ]
