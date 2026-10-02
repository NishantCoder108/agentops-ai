from app.tools.base import Tool
from app.tools.calculator import CalculatorTool
from app.tools.errors import ToolArgumentsError, ToolError, ToolExecutionError, ToolNotFoundError
from app.tools.registry import ToolRegistry


def create_default_tool_registry() -> ToolRegistry:
    return ToolRegistry([CalculatorTool()])


__all__ = [
    "CalculatorTool",
    "Tool",
    "ToolArgumentsError",
    "ToolError",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolRegistry",
    "create_default_tool_registry",
]
