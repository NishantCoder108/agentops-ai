"""Analytics against real PostgreSQL.

Seed data (organization "Acme", January 2026 unless noted):

    order  customer  currency  amount   status     placed
    o1     alice     USD       100.00   paid       Jan 05
    o2     alice     USD       200.00   delivered  Jan 10
    o3     bob       USD       250.00   shipped    Jan 31 23:59:59   (last second of the period)
    o4     bob       USD       999.00   pending    Jan 15            (not revenue)
    o5     carol     USD        50.00   cancelled  Jan 20            (not revenue)
    o6     carol     EUR        80.00   paid       Jan 12
    o7     alice     USD       500.00   paid       Feb 01 00:00:00   (outside the period)

    refund  order  amount  status     created
    r1      o2     50.00   processed  Jan 20
    r2      o1     20.00   requested  Jan 21
    r3      o6     10.00   processed  Jan 25
    r4      o2     30.00   rejected   Feb 02  (outside the period)

Organization "Globex" has a large paid order and a processed refund in January that must never
appear in Acme's results.
"""

import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent import AgentService
from app.llm import ToolCall
from app.models import Customer, Order, OrderStatus, Organization, Refund, RefundStatus
from app.schemas.analytics import Period
from app.services.analytics_service import AnalyticsService
from app.tools import AnalyticsInput, AnalyticsTool, create_default_tool_registry
from tests.fakes import FakeLLMProvider, answer_response, tool_call_response

pytestmark = pytest.mark.anyio

JANUARY = Period(start_date=date(2026, 1, 1), end_date=date(2026, 1, 31))


def at(month: int, day: int, *hms: int) -> datetime:
    return datetime(2026, month, day, *hms, tzinfo=UTC)


class Seed:
    acme: Organization
    globex: Organization
    alice: Customer
    bob: Customer
    carol: Customer


@pytest.fixture
async def seed(db_session: AsyncSession) -> Seed:
    s = Seed()
    s.acme = Organization(name="Acme")
    s.globex = Organization(name="Globex")
    s.alice = Customer(organization=s.acme, email="alice@example.test", name="Alice")
    s.bob = Customer(organization=s.acme, email="bob@example.test", name="Bob")
    s.carol = Customer(organization=s.acme, email="carol@example.test", name="Carol")
    zed = Customer(organization=s.globex, email="zed@example.test", name="Zed")

    def order(customer: Customer, amount: str, status: OrderStatus, placed: datetime, currency: str = "USD") -> Order:
        return Order(
            customer=customer,
            total_amount=Decimal(amount),
            currency=currency,
            status=status,
            created_at=placed,
        )

    o1 = order(s.alice, "100.00", OrderStatus.PAID, at(1, 5))
    o2 = order(s.alice, "200.00", OrderStatus.DELIVERED, at(1, 10))
    o3 = order(s.bob, "250.00", OrderStatus.SHIPPED, at(1, 31, 23, 59, 59))
    o4 = order(s.bob, "999.00", OrderStatus.PENDING, at(1, 15))
    o5 = order(s.carol, "50.00", OrderStatus.CANCELLED, at(1, 20))
    o6 = order(s.carol, "80.00", OrderStatus.PAID, at(1, 12), currency="EUR")
    o7 = order(s.alice, "500.00", OrderStatus.PAID, at(2, 1))
    o8 = order(zed, "10000.00", OrderStatus.PAID, at(1, 10))

    def refund(order: Order, amount: str, status: RefundStatus, created: datetime) -> Refund:
        return Refund(order=order, amount=Decimal(amount), status=status, created_at=created)

    db_session.add_all(
        [
            s.acme, s.globex, s.alice, s.bob, s.carol, zed,
            o1, o2, o3, o4, o5, o6, o7, o8,
            refund(o2, "50.00", RefundStatus.PROCESSED, at(1, 20)),
            refund(o1, "20.00", RefundStatus.REQUESTED, at(1, 21)),
            refund(o6, "10.00", RefundStatus.PROCESSED, at(1, 25)),
            refund(o2, "30.00", RefundStatus.REJECTED, at(2, 2)),
            refund(o8, "500.00", RefundStatus.PROCESSED, at(1, 15)),
        ]
    )
    await db_session.commit()
    return s


@pytest.fixture
def analytics(db_session: AsyncSession, seed: Seed) -> AnalyticsService:
    return AnalyticsService(db_session, seed.acme.id)


# --- get_revenue_summary ---


async def test_revenue_summary(analytics: AnalyticsService) -> None:
    summary = await analytics.revenue_summary(JANUARY)

    assert summary.counted_order_statuses == [OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED]
    assert [row.model_dump() for row in summary.currencies] == [
        {
            "currency": "EUR",
            "order_count": 1,
            "gross_revenue": Decimal("80.00"),
            "refunded_amount": Decimal("10.00"),
            "net_revenue": Decimal("70.00"),
            "average_order_value": Decimal("80.00"),
        },
        {
            "currency": "USD",
            "order_count": 3,
            "gross_revenue": Decimal("550.00"),
            "refunded_amount": Decimal("50.00"),
            "net_revenue": Decimal("500.00"),
            "average_order_value": Decimal("183.33"),
        },
    ]


async def test_revenue_summary_currency_filter(analytics: AnalyticsService) -> None:
    summary = await analytics.revenue_summary(JANUARY, currency="EUR")

    assert [row.currency for row in summary.currencies] == ["EUR"]


async def test_revenue_summary_includes_currencies_with_only_refunds(analytics: AnalyticsService) -> None:
    # Jan 20-25: no revenue orders (o5 is cancelled), but r1 and r3 were processed.
    summary = await analytics.revenue_summary(Period(start_date=date(2026, 1, 20), end_date=date(2026, 1, 25)))

    assert [
        (row.currency, row.order_count, row.gross_revenue, row.net_revenue, row.average_order_value)
        for row in summary.currencies
    ] == [
        ("EUR", 0, Decimal("0.00"), Decimal("-10.00"), Decimal("0.00")),
        ("USD", 0, Decimal("0.00"), Decimal("-50.00"), Decimal("0.00")),
    ]


async def test_revenue_summary_period_boundaries(analytics: AnalyticsService) -> None:
    last_day = await analytics.revenue_summary(
        Period(start_date=date(2026, 1, 31), end_date=date(2026, 1, 31)), currency="USD"
    )
    first_of_february = await analytics.revenue_summary(
        Period(start_date=date(2026, 2, 1), end_date=date(2026, 2, 1)), currency="USD"
    )

    assert last_day.currencies[0].gross_revenue == Decimal("250.00")  # o3 at 23:59:59 is included
    assert first_of_february.currencies[0].gross_revenue == Decimal("500.00")  # o7 only


# --- get_order_summary ---


async def test_order_summary(analytics: AnalyticsService) -> None:
    summary = await analytics.order_summary(JANUARY)

    assert summary.order_count == 6
    assert [(row.currency, row.status, row.order_count, row.total_amount) for row in summary.breakdown] == [
        ("EUR", OrderStatus.PAID, 1, Decimal("80.00")),
        ("USD", OrderStatus.CANCELLED, 1, Decimal("50.00")),
        ("USD", OrderStatus.DELIVERED, 1, Decimal("200.00")),
        ("USD", OrderStatus.PAID, 1, Decimal("100.00")),
        ("USD", OrderStatus.PENDING, 1, Decimal("999.00")),
        ("USD", OrderStatus.SHIPPED, 1, Decimal("250.00")),
    ]


async def test_order_summary_currency_filter(analytics: AnalyticsService) -> None:
    summary = await analytics.order_summary(JANUARY, currency="EUR")

    assert summary.order_count == 1


# --- get_refund_summary ---


async def test_refund_summary(analytics: AnalyticsService) -> None:
    summary = await analytics.refund_summary(JANUARY)

    assert summary.refund_count == 3
    assert [(row.currency, row.status, row.refund_count, row.total_amount) for row in summary.breakdown] == [
        ("EUR", RefundStatus.PROCESSED, 1, Decimal("10.00")),
        ("USD", RefundStatus.PROCESSED, 1, Decimal("50.00")),
        ("USD", RefundStatus.REQUESTED, 1, Decimal("20.00")),
    ]


async def test_refund_summary_currency_filter(analytics: AnalyticsService) -> None:
    summary = await analytics.refund_summary(JANUARY, currency="USD")

    assert summary.refund_count == 2
    assert {row.currency for row in summary.breakdown} == {"USD"}


# --- get_top_customers ---


async def test_top_customers(analytics: AnalyticsService, seed: Seed) -> None:
    result = await analytics.top_customers(JANUARY, currency="USD", limit=5)

    # Bob's pending order and Carol's cancelled order do not count; Carol has no USD revenue.
    assert [(c.customer_id, c.name, c.order_count, c.total_spent) for c in result.customers] == [
        (seed.alice.id, "Alice", 2, Decimal("300.00")),
        (seed.bob.id, "Bob", 1, Decimal("250.00")),
    ]


async def test_top_customers_limit_and_currency(analytics: AnalyticsService, seed: Seed) -> None:
    usd_top_one = await analytics.top_customers(JANUARY, currency="USD", limit=1)
    eur = await analytics.top_customers(JANUARY, currency="EUR", limit=5)

    assert [c.name for c in usd_top_one.customers] == ["Alice"]
    assert [(c.name, c.total_spent) for c in eur.customers] == [("Carol", Decimal("80.00"))]


async def test_top_customers_do_not_expose_contact_details(analytics: AnalyticsService) -> None:
    result = await analytics.top_customers(JANUARY, currency="USD", limit=5)

    assert "example.test" not in result.model_dump_json()


# --- tenant isolation and empty periods ---


async def test_results_are_scoped_to_the_organization(db_session: AsyncSession, seed: Seed) -> None:
    globex = AnalyticsService(db_session, seed.globex.id)

    revenue = await globex.revenue_summary(JANUARY)
    orders = await globex.order_summary(JANUARY)
    refunds = await globex.refund_summary(JANUARY)
    top = await globex.top_customers(JANUARY, currency="USD", limit=5)

    assert [(r.gross_revenue, r.refunded_amount) for r in revenue.currencies] == [
        (Decimal("10000.00"), Decimal("500.00"))
    ]
    assert orders.order_count == 1
    assert refunds.refund_count == 1
    assert [c.name for c in top.customers] == ["Zed"]


async def test_unknown_organization_sees_nothing(db_session: AsyncSession, seed: Seed) -> None:
    nobody = AnalyticsService(db_session, uuid.uuid4())

    assert (await nobody.revenue_summary(JANUARY)).currencies == []
    assert (await nobody.order_summary(JANUARY)).order_count == 0
    assert (await nobody.refund_summary(JANUARY)).refund_count == 0
    assert (await nobody.top_customers(JANUARY, currency="USD", limit=5)).customers == []


async def test_empty_period_returns_empty_results(analytics: AnalyticsService) -> None:
    period = Period(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))

    assert (await analytics.revenue_summary(period)).currencies == []
    assert (await analytics.order_summary(period)).order_count == 0
    assert (await analytics.refund_summary(period)).refund_count == 0
    assert (await analytics.top_customers(period, currency="USD", limit=5)).customers == []


# --- the tool ---


@pytest.fixture
def tool(session_factory: async_sessionmaker[AsyncSession], seed: Seed) -> AnalyticsTool:
    return AnalyticsTool(session_factory, seed.acme.id)


@pytest.mark.parametrize(
    ("arguments", "field", "expected"),
    [
        ({"operation": "get_revenue_summary", "currency": "USD"}, ("currencies", 0, "net_revenue"), "500.00"),
        ({"operation": "get_order_summary"}, ("order_count",), 6),
        ({"operation": "get_refund_summary"}, ("refund_count",), 3),
        ({"operation": "get_top_customers", "currency": "USD", "limit": 1}, ("customers", 0, "name"), "Alice"),
    ],
)
async def test_tool_runs_each_operation_and_returns_json(
    session_factory: async_sessionmaker[AsyncSession],
    seed: Seed,
    arguments: dict,
    field: tuple,
    expected: object,
) -> None:
    registry = create_default_tool_registry(session_factory=session_factory, organization_id=seed.acme.id)
    raw = json.dumps({"start_date": "2026-01-01", "end_date": "2026-01-31", **arguments})

    output = json.loads((await registry.execute("analytics", raw)).model_dump_json())

    assert output["operation"] == arguments["operation"]
    value = output
    for key in field:
        value = value[key]
    assert value == expected


async def test_tool_uses_default_limit_for_top_customers(tool: AnalyticsTool) -> None:
    result = await tool.run(
        AnalyticsInput(operation="get_top_customers", start_date="2026-01-01", end_date="2026-01-31", currency="USD")
    )

    assert len(result.customers) == 2  # type: ignore[attr-defined]


async def test_tool_session_is_read_only(tool: AnalyticsTool) -> None:
    async with tool._read_only_session() as session:
        with pytest.raises(DBAPIError, match="read-only transaction"):
            await session.execute(
                Organization.__table__.insert().values(name="Should not be written")
            )


async def test_tool_session_has_statement_timeout(tool: AnalyticsTool) -> None:
    async with tool._read_only_session() as session:
        timeout = (await session.execute(text("SHOW statement_timeout"))).scalar_one()

    assert timeout == "5s"


# --- the agent ---


async def test_agent_answers_with_analytics_tool(
    session_factory: async_sessionmaker[AsyncSession], seed: Seed
) -> None:
    call = ToolCall(
        id="call_1",
        name="analytics",
        arguments=json.dumps(
            {"operation": "get_refund_summary", "start_date": "2026-01-01", "end_date": "2026-01-31"}
        ),
    )
    provider = FakeLLMProvider(
        responses=[tool_call_response(call), answer_response("There were 3 refunds in January.")]
    )
    registry = create_default_tool_registry(session_factory=session_factory, organization_id=seed.acme.id)

    answer = await AgentService(provider, registry).run("How many refunds did we have in January?")

    assert answer.answer == "There were 3 refunds in January."
    assert [tool.name for tool in provider.calls[0]["tools"]] == ["calculator", "analytics"]
    tool_message = provider.calls[1]["messages"][-1]
    assert tool_message.role == "tool"
    result = json.loads(tool_message.content)
    assert result["refund_count"] == 3
    assert result["breakdown"][0] == {
        "status": "processed",
        "currency": "EUR",
        "refund_count": 1,
        "total_amount": "10.00",
    }
