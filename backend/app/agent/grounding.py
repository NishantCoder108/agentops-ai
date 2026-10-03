"""Turn a model reply into an answer whose citations come only from knowledge-tool results."""

import json
import uuid
from dataclasses import dataclass
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from app.agent.errors import AgentInvalidOutputError
from app.schemas.agent import AgentResponse, Source
from app.schemas.knowledge import KnowledgeSearchResult

KNOWLEDGE_TOOL_NAME = "search_knowledge"
INSUFFICIENT_ANSWER = "I do not have enough information to answer that."
KNOWLEDGE_ANSWER_INSTRUCTIONS = (
    "If you did not call search_knowledge, reply in plain text. "
    "After you call search_knowledge, your final reply must be a JSON object with exactly two keys: "
    '"answer" and "document_ids". '
    "document_ids must be a list of document_id values taken from that tool's results. "
    "Do not invent document ids, names, or quotations. "
    "If those results do not contain enough information to answer, return an empty document_ids list."
)


@dataclass(frozen=True)
class RetrievedPassage:
    document_id: uuid.UUID
    document_name: str
    excerpt: str


class _GroundedModelOutput(BaseModel):
    """What the model may return after search. Citations are ids only; excerpts come from the tool."""

    model_config = ConfigDict(extra="forbid")

    answer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    document_ids: list[uuid.UUID] = Field(min_length=0)


def passages_from_tool_result(content: str) -> list[RetrievedPassage]:
    """Read passages from a search_knowledge result. Tool errors contribute no passages."""
    try:
        result = KnowledgeSearchResult.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError):
        return []
    return [
        RetrievedPassage(document_id=hit.document_id, document_name=hit.document, excerpt=hit.chunk)
        for hit in result.results
    ]


def answer_without_search(content: str, tools_used: list[str]) -> AgentResponse:
    """Use a plain-text reply. Unwrap the knowledge JSON envelope only when it cites nothing."""
    stripped = content.strip()
    if not stripped.startswith("{"):
        return AgentResponse(answer=content, tools_used=tools_used)
    try:
        output = _GroundedModelOutput.model_validate_json(stripped)
    except ValidationError:
        return AgentResponse(answer=content, tools_used=tools_used)
    if output.document_ids:
        raise AgentInvalidOutputError(
            "The model cited documents without using the knowledge search",
            details={"document_ids": [str(document_id) for document_id in output.document_ids]},
        )
    return AgentResponse(answer=output.answer, tools_used=tools_used)


def ground_answer(content: str, passages: list[RetrievedPassage], tools_used: list[str]) -> AgentResponse:
    """Accept only document ids the knowledge tool returned. Excerpts are copied from those passages."""
    output = _parse_model_output(content)
    by_document = _passages_by_document(passages)
    unknown = [str(document_id) for document_id in output.document_ids if document_id not in by_document]
    if unknown:
        raise AgentInvalidOutputError(
            "The model cited documents that were not returned by the knowledge search",
            details={"document_ids": unknown},
        )
    if not output.document_ids:
        return AgentResponse(answer=INSUFFICIENT_ANSWER, sources=[], tools_used=tools_used)

    sources: list[Source] = []
    seen: set[uuid.UUID] = set()
    for document_id in output.document_ids:
        if document_id in seen:
            continue
        seen.add(document_id)
        sources.extend(
            Source(document_id=document_id, document_name=passage.document_name, relevant_excerpt=passage.excerpt)
            for passage in by_document[document_id]
        )
    return AgentResponse(answer=output.answer, sources=sources, tools_used=tools_used)


def _parse_model_output(content: str) -> _GroundedModelOutput:
    try:
        return _GroundedModelOutput.model_validate_json(content)
    except ValidationError:
        raise AgentInvalidOutputError(
            "The model did not return a grounded answer citing knowledge-search results",
            details={"reason": "invalid_json"},
        ) from None


def _passages_by_document(passages: list[RetrievedPassage]) -> dict[uuid.UUID, list[RetrievedPassage]]:
    grouped: dict[uuid.UUID, list[RetrievedPassage]] = {}
    for passage in passages:
        documents = grouped.setdefault(passage.document_id, [])
        if all(existing.excerpt != passage.excerpt for existing in documents):
            documents.append(passage)
    return grouped
