import logging
import re

from pydantic import BaseModel, ValidationError

from app.tools.base import Tool
from app.tools.errors import ToolArgumentsError, ToolError, ToolExecutionError, ToolNotFoundError

logger = logging.getLogger(__name__)

# Function-calling APIs (OpenAI, OpenRouter, Gemini) accept this name format.
_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


class ToolRegistry:
    def __init__(self, tools: list[Tool] | None = None) -> None:
        self._tools: dict[str, Tool] = {}
        for tool in tools or []:
            self.register(tool)

    def register(self, tool: Tool) -> None:
        if not _TOOL_NAME_PATTERN.fullmatch(tool.name):
            raise ValueError(f"Invalid tool name: {tool.name!r}")
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"Unknown tool: {name!r}") from None

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def __contains__(self, name: object) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)

    async def execute(self, name: str, raw_arguments: str) -> BaseModel:
        """Look up a tool, validate its JSON arguments against `input_model`, and run it."""
        tool = self.get(name)

        try:
            arguments = tool.input_model.model_validate_json(raw_arguments or "{}")
        except ValidationError as exc:
            raise ToolArgumentsError(
                f"Invalid arguments for tool {name!r}",
                details=[
                    {"loc": list(error["loc"]), "msg": error["msg"]}
                    for error in exc.errors(include_url=False)
                ],
            ) from exc

        try:
            return await tool.run(arguments)
        except ToolError:
            raise
        except Exception as exc:
            logger.exception("Tool %r failed unexpectedly", name)
            raise ToolExecutionError(f"Tool {name!r} failed") from exc
