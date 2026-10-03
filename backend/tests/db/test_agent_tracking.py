import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.agent import AgentService
from app.api.dependencies import get_llm_provider
from app.llm import LLMProviderError, ToolCall
from app.main import create_app
from app.models import AgentRun, AgentRunStatus, Conversation, ToolCallStatus
from app.models import ToolCall as ToolCallRecord
from app.tools import CalculatorTool, ToolRegistry
from tests.auth_helpers import JWT_SECRET, PASSWORD, bearer, login, register
from tests.conftest import make_settings
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response


@pytest.mark.anyio
async def test_agent_records_run_and_tool_calls_in_order(
    db_session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    conversation = Conversation()
    db_session.add(conversation)
    await db_session.commit()

    analytics = ToolCall(
        id="call_1",
        name="analytics",
        arguments=json.dumps(
            {
                "operation": "get_refund_summary",
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "api_key": "sk-should-not-be-stored",
            }
        ),
    )
    calculator = ToolCall(
        id="call_2",
        name="calculator",
        arguments=json.dumps({"expression": "25 * 800 / 100"}),
    )
    provider = FakeLLMProvider(
        responses=[
            tool_call_response(analytics),
            tool_call_response(calculator),
            answer_response("Net of the refunds, 25% of 800 is 200."),
        ]
    )
    agent = AgentService(provider, ToolRegistry([CalculatorTool()]))

    answer = await agent.run("Summarize January", session=db_session, conversation_id=conversation.id)

    assert answer.answer == "Net of the refunds, 25% of 800 is 200."
    async with session_factory() as fresh:
        run = (
            await fresh.execute(
                select(AgentRun)
                .where(AgentRun.id == agent.run_id)
                .options(selectinload(AgentRun.tool_calls))
            )
        ).scalar_one()

    assert run.conversation_id == conversation.id
    assert run.status == AgentRunStatus.COMPLETED
    assert run.final_answer == answer.answer
    assert run.started_at < run.tool_calls[0].started_at
    assert run.completed_at is not None and run.completed_at >= run.tool_calls[-1].completed_at
    assert [call.tool_name for call in run.tool_calls] == ["analytics", "calculator"]
    assert run.tool_calls[0].status == ToolCallStatus.FAILED
    assert run.tool_calls[0].arguments["operation"] == "get_refund_summary"
    assert "error" in run.tool_calls[0].result
    assert run.tool_calls[0].arguments["api_key"] == "[redacted]"
    calculator_call = run.tool_calls[1]
    assert calculator_call.status == ToolCallStatus.COMPLETED
    assert calculator_call.arguments == {"expression": "25 * 800 / 100"}
    assert calculator_call.result == {"result": 200}
    assert "sk-should-not-be-stored" not in json.dumps(
        {
            "arguments": [call.arguments for call in run.tool_calls],
            "results": [call.result for call in run.tool_calls],
            "answer": run.final_answer,
        }
    )
    assert calculator_call.started_at >= run.tool_calls[0].completed_at
    assert calculator_call.completed_at - calculator_call.started_at < timedelta(seconds=5)


@pytest.mark.anyio
async def test_failed_run_stores_no_exception_text(
    db_session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    conversation = Conversation()
    db_session.add(conversation)
    await db_session.commit()
    secret = "sk-live-do-not-store"
    agent = AgentService(FakeLLMProvider(error=LLMProviderError(f"provider failed: {secret}")))

    with pytest.raises(LLMProviderError):
        await agent.run("Hello", session=db_session, conversation_id=conversation.id)

    async with session_factory() as fresh:
        run = (await fresh.execute(select(AgentRun).where(AgentRun.id == agent.run_id))).scalar_one()
        calls = (await fresh.execute(select(ToolCallRecord))).scalars().all()

    assert run.status == AgentRunStatus.FAILED
    assert run.final_answer is None
    assert run.completed_at is not None
    assert secret not in json.dumps({"answer": run.final_answer, "status": run.status})
    assert calls == []


@pytest.mark.anyio
async def test_invalid_tool_arguments_are_stored_without_being_executed_as_code(
    db_session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    conversation = Conversation()
    db_session.add(conversation)
    await db_session.commit()
    call = ToolCall(id="call_1", name="calculator", arguments="not json")
    provider = FakeLLMProvider(responses=[tool_call_response(call), answer_response("I could not calculate that.")])
    agent = AgentService(provider, ToolRegistry([CalculatorTool()]))

    await agent.run("Calculate", session=db_session, conversation_id=conversation.id)

    async with session_factory() as fresh:
        [stored] = (await fresh.execute(select(ToolCallRecord))).scalars().all()

    assert stored.arguments == {"raw": "not json"}
    assert stored.status == ToolCallStatus.FAILED


def test_chat_persists_a_run_and_reuses_the_conversation(clean_database: str) -> None:
    app = create_app(make_settings(database_url=clean_database, jwt_secret=JWT_SECRET))
    fake = FakeLLMProvider(
        responses=[
            tool_call_response(
                ToolCall(id="call_1", name="calculator", arguments='{"expression": "2 + 2"}')
            ),
            answer_response("4"),
            answer_response("Still 4"),
        ]
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake

    with TestClient(app) as client:
        admin = register(client, email="admin@example.com")
        created = client.post(
            "/api/v1/users",
            headers=bearer(admin["access_token"]),
            json={
                "email": "member@example.com",
                "name": "Member",
                "password": PASSWORD,
                "role": "user",
            },
        )
        assert created.status_code == 201
        headers = bearer(login(client, "member@example.com"))
        first = client.post("/api/v1/chat", headers=headers, json={"message": "What is 2 + 2?"})
        assert first.status_code == 200
        body = first.json()
        assert body["answer"] == "4"
        assert body["conversation_id"]
        assert body["run_id"]

        second = client.post(
            "/api/v1/chat",
            headers=headers,
            json={"message": "And again?", "conversation_id": body["conversation_id"]},
        )
        assert second.status_code == 200
        assert second.json()["conversation_id"] == body["conversation_id"]
        assert second.json()["run_id"] != body["run_id"]

        missing = client.post(
            "/api/v1/chat",
            headers=headers,
            json={
                "message": "Hello",
                "conversation_id": "00000000-0000-0000-0000-000000000000",
            },
        )
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
