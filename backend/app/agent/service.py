from app.core.exceptions import AppError
from app.llm.base import LLMProvider
from app.llm.types import ChatMessage

DEFAULT_SYSTEM_PROMPT = (
    "You are AgentOps AI, a helpful enterprise knowledge assistant. "
    "Answer clearly and concisely. If you do not know the answer, say so."
)


class AgentService:
    """Agent orchestration. Depends only on the LLMProvider interface, never on HTTP or a concrete provider."""

    def __init__(self, provider: LLMProvider, *, system_prompt: str = DEFAULT_SYSTEM_PROMPT) -> None:
        self._provider = provider
        self._system_prompt = system_prompt

    async def run(self, message: str) -> str:
        if not message.strip():
            raise AppError("Message must not be empty", code="invalid_message", status_code=422)

        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=message),
        ]
        response = await self._provider.generate(messages)
        return response.content
