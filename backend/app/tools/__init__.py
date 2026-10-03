import uuid

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.knowledge.embeddings import EmbeddingProvider
from app.tools.analytics import AnalyticsInput, AnalyticsOperation, AnalyticsTool
from app.tools.base import Tool
from app.tools.calculator import CalculatorTool
from app.tools.errors import ToolArgumentsError, ToolError, ToolExecutionError, ToolNotFoundError
from app.tools.knowledge import KnowledgeSearchInput, KnowledgeSearchTool
from app.tools.registry import ToolRegistry


def create_default_tool_registry(
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    organization_id: uuid.UUID | None = None,
    embedder: EmbeddingProvider | None = None,
) -> ToolRegistry:
    """The agent's tools. Business and knowledge tools are only offered when the database,
    the caller's organization, and (for search) an embedding provider are known."""
    tools: list[Tool] = [CalculatorTool()]
    if session_factory is not None and organization_id is not None:
        tools.append(AnalyticsTool(session_factory, organization_id))
        if embedder is not None:
            tools.append(KnowledgeSearchTool(session_factory, organization_id, embedder))
    return ToolRegistry(tools)


__all__ = [
    "AnalyticsInput",
    "AnalyticsOperation",
    "AnalyticsTool",
    "CalculatorTool",
    "KnowledgeSearchInput",
    "KnowledgeSearchTool",
    "Tool",
    "ToolArgumentsError",
    "ToolError",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolRegistry",
    "create_default_tool_registry",
]
