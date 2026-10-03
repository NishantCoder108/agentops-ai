import uuid
from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.models import (
    AgentRun,
    AgentRunStatus,
    Conversation,
    Customer,
    Message,
    MessageRole,
    Order,
    OrderStatus,
    Organization,
    Refund,
    RefundStatus,
    ToolCall,
    User,
)

pytestmark = pytest.mark.anyio


async def add(session: AsyncSession, *objects: object) -> None:
    session.add_all(objects)
    await session.commit()


async def count(session: AsyncSession, model: type) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.fixture
async def organization(db_session: AsyncSession) -> Organization:
    organization = Organization(name="Acme")
    await add(db_session, organization)
    return organization


@pytest.fixture
async def user(db_session: AsyncSession, organization: Organization) -> User:
    user = User(organization=organization, email="alice@acme.test", name="Alice")
    await add(db_session, user)
    return user


@pytest.fixture
async def customer(db_session: AsyncSession, organization: Organization) -> Customer:
    customer = Customer(organization=organization, email="bob@example.test", name="Bob")
    await add(db_session, customer)
    return customer


@pytest.fixture
async def order(db_session: AsyncSession, customer: Customer) -> Order:
    order = Order(customer=customer, total_amount=Decimal("800.00"), currency="USD")
    await add(db_session, order)
    return order


@pytest.fixture
async def user_message(db_session: AsyncSession, user: User) -> Message:
    conversation = Conversation(user=user)
    message = Message(conversation=conversation, role=MessageRole.USER, content="What is 25% of 800?")
    await add(db_session, conversation, message)
    return message


# --- ids and timestamps ---


async def test_uuid_and_timestamps_are_generated(organization: Organization) -> None:
    assert isinstance(organization.id, uuid.UUID)
    assert organization.created_at.tzinfo is not None
    assert organization.updated_at == organization.created_at


async def test_updated_at_changes_on_update(db_session: AsyncSession, organization: Organization) -> None:
    created_at = organization.created_at

    organization.name = "Acme Corp"
    await db_session.commit()

    assert organization.created_at == created_at
    assert organization.updated_at > created_at


async def test_server_side_defaults_work_for_raw_sql_inserts(db_session: AsyncSession) -> None:
    row = (
        await db_session.execute(
            text("INSERT INTO organizations (name) VALUES ('Raw') RETURNING id, created_at, updated_at")
        )
    ).one()

    assert isinstance(row.id, uuid.UUID)
    assert row.created_at is not None and row.updated_at is not None


# --- organizations, users, customers ---


async def test_user_email_is_globally_unique(db_session: AsyncSession, user: User) -> None:
    other_organization = Organization(name="Globex")

    with pytest.raises(IntegrityError, match="uq_users_email"):
        await add(db_session, User(organization=other_organization, email=user.email, name="Alice 2"))


async def test_customer_email_is_unique_per_organization(
    db_session: AsyncSession, organization: Organization, customer: Customer
) -> None:
    other_organization = Organization(name="Globex")
    await add(db_session, Customer(organization=other_organization, email=customer.email, name="Bob"))

    with pytest.raises(IntegrityError, match="uq_customers_organization_id_email"):
        await add(db_session, Customer(organization=organization, email=customer.email, name="Bob 2"))


async def test_organization_with_members_cannot_be_deleted(
    db_session: AsyncSession, organization: Organization, user: User
) -> None:
    with pytest.raises(IntegrityError, match="fk_users_organization_id_organizations"):
        await db_session.execute(delete(Organization).where(Organization.id == organization.id))


# --- commerce ---


async def test_customer_order_refund_relationships(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    customer: Customer,
    order: Order,
) -> None:
    await add(
        db_session,
        Refund(order=order, amount=Decimal("200.00"), reason="Damaged item"),
        Refund(order=order, amount=Decimal("50.50")),
    )

    async with session_factory() as fresh:
        loaded = (
            await fresh.execute(
                select(Customer)
                .where(Customer.id == customer.id)
                .options(
                    selectinload(Customer.organization),
                    selectinload(Customer.orders).selectinload(Order.refunds),
                )
            )
        ).scalar_one()

    assert loaded.organization.name == "Acme"
    [loaded_order] = loaded.orders
    assert loaded_order.status == OrderStatus.PENDING
    assert loaded_order.total_amount == Decimal("800.00")
    assert sorted(refund.amount for refund in loaded_order.refunds) == [Decimal("50.50"), Decimal("200.00")]
    assert {refund.status for refund in loaded_order.refunds} == {RefundStatus.REQUESTED}


@pytest.mark.parametrize(
    ("total_amount", "currency", "constraint"),
    [
        (Decimal("-1.00"), "USD", "ck_orders_total_amount_non_negative"),
        (Decimal("10.00"), "usd", "ck_orders_currency_iso_4217"),
        (Decimal("10.00"), "US", "ck_orders_currency_iso_4217"),
    ],
)
async def test_order_check_constraints(
    db_session: AsyncSession, customer: Customer, total_amount: Decimal, currency: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await add(db_session, Order(customer=customer, total_amount=total_amount, currency=currency))


@pytest.mark.parametrize("amount", [Decimal("0.00"), Decimal("-5.00")])
async def test_refund_amount_must_be_positive(db_session: AsyncSession, order: Order, amount: Decimal) -> None:
    with pytest.raises(IntegrityError, match="ck_refunds_amount_positive"):
        await add(db_session, Refund(order=order, amount=amount))


async def test_status_is_restricted_at_database_level(db_session: AsyncSession, customer: Customer) -> None:
    with pytest.raises(IntegrityError, match="ck_orders_status"):
        await db_session.execute(
            text(
                "INSERT INTO orders (customer_id, status, total_amount, currency) "
                "VALUES (:customer_id, 'teleported', 1, 'USD')"
            ),
            {"customer_id": customer.id},
        )


async def test_customer_with_orders_cannot_be_deleted(
    db_session: AsyncSession, customer: Customer, order: Order
) -> None:
    with pytest.raises(IntegrityError, match="fk_orders_customer_id_customers"):
        await db_session.execute(delete(Customer).where(Customer.id == customer.id))


async def test_order_with_refunds_cannot_be_deleted(db_session: AsyncSession, order: Order) -> None:
    await add(db_session, Refund(order=order, amount=Decimal("1.00")))

    with pytest.raises(IntegrityError, match="fk_refunds_order_id_orders"):
        await db_session.execute(delete(Order).where(Order.id == order.id))


# --- conversations and agent runs ---


async def test_agent_run_records_tool_calls_in_order(
    db_session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    user_message: Message,
) -> None:
    from datetime import UTC, datetime, timedelta

    started = datetime(2026, 3, 1, tzinfo=UTC)
    run = AgentRun(
        conversation_id=user_message.conversation_id,
        started_at=started,
        status=AgentRunStatus.COMPLETED,
        completed_at=started + timedelta(seconds=3),
        final_answer="200",
    )
    await add(db_session, run)
    await add(
        db_session,
        ToolCall(
            agent_run_id=run.id,
            tool_name="analytics",
            arguments={"operation": "get_refund_summary"},
            result={"refund_count": 3},
            status="completed",
            started_at=started + timedelta(seconds=1),
            completed_at=started + timedelta(seconds=2),
        ),
        ToolCall(
            agent_run_id=run.id,
            tool_name="calculator",
            arguments={"expression": "1 + 1"},
            result={"error": "Invalid arguments for tool 'calculator'"},
            status="failed",
            started_at=started + timedelta(seconds=2),
            completed_at=started + timedelta(seconds=2, milliseconds=10),
        ),
    )

    async with session_factory() as fresh:
        loaded = (
            await fresh.execute(
                select(AgentRun)
                .where(AgentRun.id == run.id)
                .options(selectinload(AgentRun.tool_calls))
            )
        ).scalar_one()

    assert loaded.status == AgentRunStatus.COMPLETED
    assert loaded.final_answer == "200"
    assert loaded.completed_at is not None
    assert [(call.tool_name, call.status, call.result) for call in loaded.tool_calls] == [
        ("analytics", "completed", {"refund_count": 3}),
        ("calculator", "failed", {"error": "Invalid arguments for tool 'calculator'"}),
    ]


@pytest.mark.parametrize(
    ("status", "final_answer", "constraint"),
    [
        ("completed", "done", "ck_agent_runs_completed_at_iff_finished"),
        ("running", "done", "ck_agent_runs_final_answer_iff_completed"),
        ("failed", None, "ck_agent_runs_completed_at_iff_finished"),
    ],
)
async def test_agent_run_status_constraints(
    db_session: AsyncSession,
    user_message: Message,
    status: str,
    final_answer: str | None,
    constraint: str,
) -> None:
    with pytest.raises(IntegrityError, match=constraint):
        await add(
            db_session,
            AgentRun(
                conversation_id=user_message.conversation_id,
                status=status,
                completed_at=None,
                final_answer=final_answer,
            ),
        )


async def test_running_tool_call_has_no_result(db_session: AsyncSession, user_message: Message) -> None:
    run = AgentRun(conversation_id=user_message.conversation_id)
    await add(db_session, run)

    with pytest.raises(IntegrityError, match="ck_tool_calls_result_iff_finished"):
        await add(
            db_session,
            ToolCall(
                agent_run_id=run.id,
                tool_name="calculator",
                arguments={"expression": "1 + 1"},
                result={"result": 2},
                status="running",
            ),
        )


async def test_deleting_conversation_cascades_to_messages_runs_and_tool_calls(
    db_session: AsyncSession, user_message: Message
) -> None:
    run = AgentRun(conversation_id=user_message.conversation_id)
    await add(db_session, run)
    await add(
        db_session,
        ToolCall(
            agent_run_id=run.id,
            tool_name="calculator",
            arguments={},
            result={"result": 2},
            status="completed",
            completed_at=run.started_at,
        ),
    )

    await db_session.execute(delete(Conversation).where(Conversation.id == user_message.conversation_id))
    await db_session.commit()

    for model in (Conversation, Message, AgentRun, ToolCall):
        assert await count(db_session, model) == 0, model.__name__


async def test_deleting_user_cascades_to_conversations(db_session: AsyncSession, user: User, user_message: Message) -> None:
    await db_session.execute(delete(User).where(User.id == user.id))
    await db_session.commit()

    assert await count(db_session, Conversation) == 0
    assert await count(db_session, Message) == 0
