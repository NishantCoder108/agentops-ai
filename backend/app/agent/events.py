"""Events an agent run yields while it is still working."""

class ClientDisconnected(Exception):
    """The caller stopped listening before the run finished."""

from dataclasses import dataclass
from typing import Literal

from app.schemas.agent import AgentResponse


@dataclass(frozen=True)
class AgentStatus:
    status: Literal["thinking", "tool", "generating"]
    tool: str | None = None


@dataclass(frozen=True)
class AgentToken:
    text: str
    replace: bool = False


@dataclass(frozen=True)
class AgentDone:
    response: AgentResponse


AgentEvent = AgentStatus | AgentToken | AgentDone
