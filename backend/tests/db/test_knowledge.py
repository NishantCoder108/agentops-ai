import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import AgentService
from app.api.dependencies import get_embedding_provider
from app.knowledge.service import KnowledgeService
from app.llm import ToolCall
from app.main import create_app
from app.models import Organization
from app.models.document import DocumentFormat
from app.tools import create_default_tool_registry
from tests.auth_helpers import JWT_SECRET, bearer, register
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response
from tests.test_knowledge import _FakeEmbedder, vector_for

pytestmark = pytest.mark.anyio


async def test_search_returns_the_nearest_chunk_for_this_organization(
    db_session: AsyncSession,
) -> None:
    acme = Organization(name="Acme")
    globex = Organization(name="Globex")
    db_session.add_all([acme, globex])
    await db_session.commit()
    embedder = _FakeEmbedder()
    acme_docs = KnowledgeService(db_session, acme.id, embedder)
    await acme_docs.add_document("refunds.md", DocumentFormat.MARKDOWN, "Refunds are reviewed in five days.")
    await acme_docs.add_document("shipping.txt", DocumentFormat.TXT, "Shipping takes two days.")
    await KnowledgeService(db_session, globex.id, embedder).add_document(
        "refunds.md", DocumentFormat.MARKDOWN, "Globex refunds are instant."
    )

    result = await acme_docs.search_by_vector(vector_for("Refunds are reviewed in five days."), limit=5)

    assert result.results[0].document == "refunds.md"
    assert result.results[0].chunk == "Refunds are reviewed in five days."
    assert result.results[0].similarity == 1.0
    assert "Globex" not in result.model_dump_json()
    assert [hit.document for hit in result.results] == ["refunds.md", "shipping.txt"]


async def test_agent_search_knowledge_tool_returns_chunks(
    db_session: AsyncSession, session_factory
) -> None:
    organization = Organization(name="Acme")
    db_session.add(organization)
    await db_session.commit()
    embedder = _FakeEmbedder()
    document = await KnowledgeService(db_session, organization.id, embedder).add_document(
        "policy.md", DocumentFormat.MARKDOWN, "The refund window is 30 days."
    )
    call = ToolCall(
        id="call_1",
        name="search_knowledge",
        arguments=json.dumps({"query": "The refund window is 30 days."}),
    )
    provider = FakeLLMProvider(
        responses=[
            tool_call_response(call),
            answer_response(
                json.dumps(
                    {
                        "answer": "The refund window is 30 days.",
                        "document_ids": [str(document.id)],
                    }
                )
            ),
        ]
    )
    registry = create_default_tool_registry(
        session_factory=session_factory, organization_id=organization.id, embedder=embedder
    )

    answer = await AgentService(provider, registry).run("What is the refund window?")

    assert answer.answer == "The refund window is 30 days."
    assert answer.tools_used == ["search_knowledge"]
    assert [(source.document_id, source.document_name, source.relevant_excerpt) for source in answer.sources] == [
        (document.id, "policy.md", "The refund window is 30 days.")
    ]
    assert [tool.name for tool in provider.calls[0]["tools"]] == [
        "calculator",
        "analytics",
        "search_knowledge",
    ]
    payload = json.loads(provider.calls[1]["messages"][-1].content)
    assert payload["results"][0] == {
        "document_id": str(document.id),
        "document": "policy.md",
        "chunk": "The refund window is 30 days.",
        "similarity": 1.0,
    }


def test_upload_document_stores_chunks(clean_database: str) -> None:
    embedder = _RecordingEmbedder()
    app = create_app(
        make_settings(
            database_url=clean_database,
            jwt_secret=JWT_SECRET,
            embedding_model="openai/text-embedding-3-small",
            openrouter_api_key="test-key",
        )
    )
    app.dependency_overrides[get_embedding_provider] = lambda: embedder

    with TestClient(app) as client:
        missing_token = client.post(
            "/api/v1/documents",
            files={"file": ("notes.md", b"# Hi", "text/markdown")},
        )
        assert missing_token.status_code == 401
        assert missing_token.json()["error"]["code"] == "unauthorized"

        admin = register(client)
        headers = bearer(admin["access_token"])
        created = client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("../policy.md", b"# Refunds\n\nFive days.", "text/markdown")},
        )
        assert created.status_code == 201
        assert created.json()["filename"] == "policy.md"
        assert created.json()["format"] == "markdown"
        assert created.json()["chunk_count"] == 1

        rejected = client.post(
            "/api/v1/documents",
            headers=headers,
            files={"file": ("notes.pdf", b"%PDF", "application/pdf")},
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "invalid_document"

    assert embedder.texts == [["# Refunds\n\nFive days."]]


class _RecordingEmbedder(_FakeEmbedder):
    def __init__(self) -> None:
        self.texts: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts.append(list(texts))
        return await super().embed(texts)

