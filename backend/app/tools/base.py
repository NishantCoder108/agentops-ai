from typing import Any, Protocol

from pydantic import BaseModel


class Tool(Protocol):
    """A capability the agent can offer to the model.

    `input_model` is the single source of truth for the arguments: it produces the JSON Schema
    shown to the model and validates the model's arguments before `run` is called.
    `run` receives an instance of `input_model` and may raise `ToolError` for expected failures.
    """

    name: str
    description: str
    input_model: type[BaseModel]

    async def run(self, arguments: Any) -> BaseModel: ...
