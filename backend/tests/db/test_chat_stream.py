import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.events import AgentStatus
from app.agent.service import AgentService
from app.models import AgentRun, AgentRunStatus, Conversation, Message, MessageRole
from tests.fakes import FakeLLMProvider

pytestmark = pytest.mark.anyio


async def test_closing_a_stream_fails_the_open_run(
    db_session: AsyncSession, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    conversation = Conversation()
    db_session.add(conversation)
    await db_session.commit()
    agent = AgentService(FakeLLMProvider(reply="Hi"))
    stream = agent.stream("Hello", session=db_session, conversation_id=conversation.id)

    assert await anext(stream) == AgentStatus(status="thinking")
    await stream.aclose()

    async with session_factory() as fresh:
        run = (await fresh.execute(select(AgentRun).where(AgentRun.id == agent.run_id))).scalar_one()
        messages = (await fresh.scalars(select(Message).order_by(Message.created_at))).all()

    assert run.status == AgentRunStatus.FAILED
    assert run.final_answer is None
    assert [(message.role, message.content) for message in messages] == [(MessageRole.USER, "Hello")]
