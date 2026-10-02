from typing import Any


class ToolError(Exception):
    """A tool failure that is reported back to the model rather than to the API client."""

    def __init__(self, message: str, *, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class ToolNotFoundError(ToolError):
    pass


class ToolArgumentsError(ToolError):
    pass


class ToolExecutionError(ToolError):
    pass
