"""Persist an agent run and its tool calls. No secrets are written."""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, AgentRunStatus, ToolCall, ToolCallStatus

_SECRET_KEY_PARTS = ("api_key", "apikey", "password", "secret", "token", "authorization", "credential")
_REDACTED = "[redacted]"


def utcnow() -> datetime:
    return datetime.now(UTC)


def structured_json(raw: str) -> Any:
    """Parse model output into JSON. Invalid JSON is kept as {"raw": ...}, never executed."""
    try:
        value = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {"raw": raw}
    return redact(value)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _REDACTED if _is_secret_key(key) else redact(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def _is_secret_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SECRET_KEY_PARTS)


class RunTracker:
    """Writes one AgentRun. Each step is committed so a crash does not lose earlier steps."""

    def __init__(self, session: AsyncSession, conversation_id: uuid.UUID) -> None:
        self._session = session
        self._conversation_id = conversation_id
        self.run: AgentRun | None = None
        self.run_id: uuid.UUID | None = None

    async def start(self) -> AgentRun:
        self.run = AgentRun(
            conversation_id=self._conversation_id,
            status=AgentRunStatus.RUNNING,
            started_at=utcnow(),
        )
        self._session.add(self.run)
        await self._session.commit()
        self.run_id = self.run.id
        return self.run

    async def start_tool(self, tool_name: str, raw_arguments: str) -> ToolCall:
        call = ToolCall(
            agent_run_id=self._run().id,
            tool_name=tool_name[:64],
            arguments=structured_json(raw_arguments),
            status=ToolCallStatus.RUNNING,
            started_at=utcnow(),
        )
        self._session.add(call)
        await self._session.commit()
        return call

    async def finish_tool(self, call: ToolCall, raw_result: str) -> None:
        result = structured_json(raw_result)
        failed = isinstance(result, dict) and "error" in result
        call.result = result
        call.status = ToolCallStatus.FAILED if failed else ToolCallStatus.COMPLETED
        call.completed_at = utcnow()
        await self._session.commit()

    async def complete(self, answer: str) -> None:
        run = self._run()
        run.status = AgentRunStatus.COMPLETED
        run.final_answer = answer
        run.completed_at = utcnow()
        await self._session.commit()

    async def fail(self) -> None:
        """Mark the run failed. The exception text is not stored; it can contain credentials."""
        if self.run_id is None:
            return
        await self._session.rollback()
        run = await self._session.get(AgentRun, self.run_id)
        if run is None or run.status != AgentRunStatus.RUNNING:
            return
        run.status = AgentRunStatus.FAILED
        run.final_answer = None
        run.completed_at = utcnow()
        await self._session.commit()
        self.run = run

    def _run(self) -> AgentRun:
        if self.run is None:
            raise RuntimeError("Run tracking has not been started")
        return self.run
