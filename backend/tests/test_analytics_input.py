import json
import uuid
from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.tools import (
    AnalyticsInput,
    AnalyticsOperation,
    AnalyticsTool,
    CalculatorTool,
    ToolArgumentsError,
    ToolRegistry,
    create_default_tool_registry,
)


def analytics_args(**overrides: object) -> dict:
    return {
        "operation": "get_revenue_summary",
        "start_date": "2026-01-01",
        "end_date": "2026-01-31",
        **overrides,
    }


@pytest.mark.parametrize("operation", list(AnalyticsOperation))
def test_every_operation_accepts_a_date_range(operation: AnalyticsOperation) -> None:
    extra = {"currency": "USD"} if operation == AnalyticsOperation.GET_TOP_CUSTOMERS else {}

    parsed = AnalyticsInput.model_validate(analytics_args(operation=operation.value, **extra))

    assert parsed.operation == operation
    assert parsed.period.start_date == date(2026, 1, 1)
    assert parsed.period.end_date == date(2026, 1, 31)


def test_single_day_period_is_allowed() -> None:
    parsed = AnalyticsInput.model_validate(analytics_args(start_date="2026-01-05", end_date="2026-01-05"))

    assert parsed.start_date == parsed.end_date


def test_top_customers_accepts_currency_and_limit() -> None:
    parsed = AnalyticsInput.model_validate(
        analytics_args(operation="get_top_customers", currency="EUR", limit=10)
    )

    assert (parsed.currency, parsed.limit) == ("EUR", 10)


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({"operation": "run_sql"}, "operation"),
        ({"operation": "DROP TABLE orders"}, "operation"),
        ({"start_date": "2026-02-01"}, "end_date must not be before start_date"),
        ({"start_date": "2026-01-01; DELETE FROM orders"}, "start_date"),
        ({"end_date": "yesterday"}, "end_date"),
        ({"end_date": None}, "end_date"),
        ({"currency": "usd"}, "currency"),
        ({"currency": "USD' OR 1=1 --"}, "currency"),
        ({"limit": 5}, "limit is only supported by get_top_customers"),
        ({"sql": "SELECT * FROM users"}, "sql"),
        ({"organization_id": str(uuid.uuid4())}, "organization_id"),
    ],
)
def test_invalid_arguments_are_rejected(overrides: dict, expected_error: str) -> None:
    with pytest.raises(ValidationError, match=expected_error):
        AnalyticsInput.model_validate(analytics_args(**overrides))


@pytest.mark.parametrize(
    ("overrides", "expected_error"),
    [
        ({}, "currency is required for get_top_customers"),
        ({"currency": "USD", "limit": 0}, "limit"),
        ({"currency": "USD", "limit": 21}, "limit"),
    ],
)
def test_top_customers_argument_rules(overrides: dict, expected_error: str) -> None:
    with pytest.raises(ValidationError, match=expected_error):
        AnalyticsInput.model_validate(analytics_args(operation="get_top_customers", **overrides))


def test_missing_required_fields_are_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        AnalyticsInput.model_validate({})

    assert {error["loc"][0] for error in exc_info.value.errors()} == {"operation", "start_date", "end_date"}


def test_schema_is_a_flat_object_with_an_operation_enum() -> None:
    schema = AnalyticsInput.model_json_schema()

    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"operation", "start_date", "end_date"}
    assert set(schema["properties"]) == {"operation", "start_date", "end_date", "currency", "limit"}
    operation_enum = schema["$defs"]["AnalyticsOperation"]["enum"]
    assert operation_enum == [
        "get_revenue_summary",
        "get_order_summary",
        "get_refund_summary",
        "get_top_customers",
    ]


@pytest.mark.anyio
async def test_registry_rejects_invalid_analytics_arguments_before_touching_the_database() -> None:
    # The session factory points at a closed port: any database access would fail loudly.
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    registry = ToolRegistry([AnalyticsTool(async_sessionmaker(engine), uuid.uuid4())])

    with pytest.raises(ToolArgumentsError) as exc_info:
        await registry.execute("analytics", json.dumps(analytics_args(operation="get_top_customers")))

    assert exc_info.value.message == "Invalid arguments for tool 'analytics'"
    await engine.dispose()


def test_default_registry_includes_analytics_only_with_database_and_organization() -> None:
    engine = create_async_engine("postgresql+asyncpg://u:p@127.0.0.1:1/none")
    factory = async_sessionmaker(engine)

    calculator_only = [
        create_default_tool_registry(),
        create_default_tool_registry(session_factory=factory),
        create_default_tool_registry(organization_id=uuid.uuid4()),
    ]
    for registry in calculator_only:
        assert [type(tool) for tool in registry.list_tools()] == [CalculatorTool]

    full = create_default_tool_registry(session_factory=factory, organization_id=uuid.uuid4())
    assert [tool.name for tool in full.list_tools()] == ["calculator", "analytics"]
    engine.sync_engine.dispose()
