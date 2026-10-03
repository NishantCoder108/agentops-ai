import json
import uuid

import pytest

from app.agent import AgentInvalidOutputError, AgentService
from app.llm import ToolCall
from app.schemas.knowledge import KnowledgeHit, KnowledgeSearchResult
from app.tools import CalculatorTool
from app.tools.knowledge import KnowledgeSearchInput
from app.tools.registry import ToolRegistry
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response

pytestmark = pytest.mark.asyncio

POLICY_ID = uuid.UUID("7f1c7b7e-3c2e-4a59-9d39-2b0f5c3d8a10")
SHIPPING_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")
UNKNOWN_ID = uuid.UUID("22222222-2222-4222-8222-222222222222")
POLICY = "The refund window is 30 days."
SHIPPING = "Shipping takes two days."


class _KnowledgeTool:
    name = "search_knowledge"
    description = "Search uploaded documents."
    input_model = KnowledgeSearchInput

    def __init__(self, result: KnowledgeSearchResult) -> None:
        self._result = result

    async def run(self, arguments: KnowledgeSearchInput) -> KnowledgeSearchResult:
        return self._result


def _hit(document_id: uuid.UUID, name: str, chunk: str) -> KnowledgeHit:
    return KnowledgeHit(document_id=document_id, document=name, chunk=chunk, similarity=1.0)


def _agent(result: KnowledgeSearchResult, final: str) -> tuple[AgentService, FakeLLMProvider]:
    call = ToolCall(id="call_1", name="search_knowledge", arguments=json.dumps({"query": "refunds"}))
    provider = FakeLLMProvider(responses=[tool_call_response(call), answer_response(final)])
    agent = AgentService(provider, ToolRegistry([_KnowledgeTool(result)]))
    return agent, provider


async def test_grounded_answer_cites_only_the_document_the_model_selected() -> None:
    agent, _provider = _agent(
        KnowledgeSearchResult(
            results=[_hit(POLICY_ID, "policy.md", POLICY), _hit(SHIPPING_ID, "shipping.txt", SHIPPING)]
        ),
        json.dumps({"answer": "The refund window is 30 days.", "document_ids": [str(POLICY_ID)]}),
    )

    response = await agent.run("What is the refund window?")

    assert response.answer == "The refund window is 30 days."
    assert response.tools_used == ["search_knowledge"]
    assert [(source.document_id, source.document_name) for source in response.sources] == [
        (POLICY_ID, "policy.md")
    ]
    assert SHIPPING not in response.model_dump_json()


@pytest.mark.parametrize(
    "results",
    [[], [_hit(POLICY_ID, "policy.md", POLICY)]],
)
async def test_missing_knowledge_says_there_is_not_enough_information(
    results: list[KnowledgeHit],
) -> None:
    agent, _provider = _agent(
        KnowledgeSearchResult(results=results),
        json.dumps({"answer": "The refund window is 90 days.", "document_ids": []}),
    )

    response = await agent.run("What is the refund window?")

    assert response.answer == "I do not have enough information to answer that."
    assert response.sources == []
    assert response.tools_used == ["search_knowledge"]
    assert "90 days" not in response.answer


async def test_sources_propagate_from_the_knowledge_tool() -> None:
    agent, _provider = _agent(
        KnowledgeSearchResult(
            results=[
                _hit(POLICY_ID, "policy.md", "Refunds are reviewed in five days."),
                _hit(POLICY_ID, "policy.md", "The refund window is 30 days."),
            ]
        ),
        json.dumps(
            {"answer": "Refunds take 30 days and are reviewed in five.", "document_ids": [str(POLICY_ID)]}
        ),
    )

    response = await agent.run("What is the refund policy?")

    assert [(source.document_id, source.document_name, source.relevant_excerpt) for source in response.sources] == [
        (POLICY_ID, "policy.md", "Refunds are reviewed in five days."),
        (POLICY_ID, "policy.md", "The refund window is 30 days."),
    ]


@pytest.mark.parametrize(
    "final",
    [
        "The refund window is 30 days.",
        json.dumps({"answer": "The refund window is 30 days.", "document_ids": [str(UNKNOWN_ID)]}),
        json.dumps({"answer": "   ", "document_ids": [str(POLICY_ID)]}),
        json.dumps(
            {
                "answer": "The refund window is 30 days.",
                "document_ids": [str(POLICY_ID)],
                "relevant_excerpt": "A quotation the model invented.",
            }
        ),
    ],
)
async def test_invalid_model_output_is_rejected(final: str) -> None:
    agent, _provider = _agent(
        KnowledgeSearchResult(results=[_hit(POLICY_ID, "policy.md", POLICY)]),
        final,
    )

    with pytest.raises(AgentInvalidOutputError) as exc_info:
        await agent.run("What is the refund window?")

    assert exc_info.value.code == "agent_invalid_output"


async def test_calculator_answer_unwraps_an_empty_citation_envelope() -> None:
    call = ToolCall(id="call_1", name="calculator", arguments=json.dumps({"expression": "12 * 8"}))
    provider = FakeLLMProvider(
        responses=[
            tool_call_response(call),
            answer_response(json.dumps({"answer": "96", "document_ids": []})),
        ]
    )
    agent = AgentService(
        provider,
        ToolRegistry([CalculatorTool(), _KnowledgeTool(KnowledgeSearchResult(results=[]))]),
    )

    response = await agent.run("What is 12 * 8?")

    assert response.answer == "96"
    assert response.sources == []
    assert response.tools_used == ["calculator"]


async def test_citations_without_a_knowledge_search_are_rejected() -> None:
    provider = FakeLLMProvider(
        responses=[answer_response(json.dumps({"answer": "Thirty days.", "document_ids": [str(POLICY_ID)]}))]
    )
    agent = AgentService(provider, ToolRegistry([_KnowledgeTool(KnowledgeSearchResult(results=[]))]))

    with pytest.raises(AgentInvalidOutputError) as exc_info:
        await agent.run("What is the refund window?")

    assert exc_info.value.code == "agent_invalid_output"
