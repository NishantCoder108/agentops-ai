import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from enum import StrEnum
from typing import assert_never

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.schemas.analytics import CurrencyCode, Period
from app.services.analytics_service import AnalyticsService
from app.tools.errors import ToolArgumentsError

DEFAULT_TOP_CUSTOMERS_LIMIT = 5
MAX_TOP_CUSTOMERS_LIMIT = 20


class AnalyticsOperation(StrEnum):
    GET_REVENUE_SUMMARY = "get_revenue_summary"
    GET_ORDER_SUMMARY = "get_order_summary"
    GET_REFUND_SUMMARY = "get_refund_summary"
    GET_TOP_CUSTOMERS = "get_top_customers"


class AnalyticsInput(BaseModel):
    """Arguments chosen by the model. A flat object (not a union) because function-calling APIs
    require the top-level parameters schema to be a single JSON object."""

    model_config = ConfigDict(extra="forbid")

    operation: AnalyticsOperation = Field(description="Which predefined analytics query to run.")
    start_date: date = Field(description="First day of the period, inclusive (YYYY-MM-DD, UTC).")
    end_date: date = Field(description="Last day of the period, inclusive (YYYY-MM-DD, UTC).")
    currency: CurrencyCode | None = Field(
        default=None,
        description="ISO 4217 code. Optional filter; required for get_top_customers.",
    )
    limit: int | None = Field(
        default=None,
        ge=1,
        le=MAX_TOP_CUSTOMERS_LIMIT,
        description=f"Only for get_top_customers: number of customers (default {DEFAULT_TOP_CUSTOMERS_LIMIT}).",
    )

    @model_validator(mode="after")
    def check_operation_arguments(self) -> "AnalyticsInput":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if self.operation == AnalyticsOperation.GET_TOP_CUSTOMERS:
            if self.currency is None:
                raise ValueError("currency is required for get_top_customers")
        elif self.limit is not None:
            raise ValueError("limit is only supported by get_top_customers")
        return self

    @property
    def period(self) -> Period:
        return Period(start_date=self.start_date, end_date=self.end_date)


class AnalyticsTool:
    """Answers business analytics questions with predefined queries; the model never supplies SQL.

    Bound to one organization by the server. Each call uses its own short, read-only transaction
    with a statement timeout, so no database connection is held while the model is thinking.
    """

    name = "analytics"
    description = (
        "Run a predefined business analytics query over the organization's orders and refunds. "
        "Operations: "
        "get_revenue_summary (per currency: paid/shipped/delivered orders placed in the period, "
        "refunds processed in the period, net revenue, average order value); "
        "get_order_summary (orders placed in the period, by status and currency); "
        "get_refund_summary (refunds created in the period, by status and currency); "
        "get_top_customers (customers ranked by spend in one currency; needs currency, optional limit). "
        "Dates are inclusive calendar days in UTC. Amounts are decimal strings and are never "
        "combined across currencies."
    )
    input_model = AnalyticsInput

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], organization_id: uuid.UUID
    ) -> None:
        self._session_factory = session_factory
        self._organization_id = organization_id

    async def run(self, arguments: AnalyticsInput) -> BaseModel:
        async with self._read_only_session() as session:
            service = AnalyticsService(session, self._organization_id)
            period = arguments.period
            match arguments.operation:
                case AnalyticsOperation.GET_REVENUE_SUMMARY:
                    return await service.revenue_summary(period, arguments.currency)
                case AnalyticsOperation.GET_ORDER_SUMMARY:
                    return await service.order_summary(period, arguments.currency)
                case AnalyticsOperation.GET_REFUND_SUMMARY:
                    return await service.refund_summary(period, arguments.currency)
                case AnalyticsOperation.GET_TOP_CUSTOMERS:
                    if arguments.currency is None:
                        raise ToolArgumentsError("currency is required for get_top_customers")
                    return await service.top_customers(
                        period, arguments.currency, arguments.limit or DEFAULT_TOP_CUSTOMERS_LIMIT
                    )
                case _:
                    assert_never(arguments.operation)

    @asynccontextmanager
    async def _read_only_session(self) -> AsyncIterator[AsyncSession]:
        async with self._session_factory() as session, session.begin():
            # Defence in depth: even a buggy query cannot write, and none can run for long.
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text("SET LOCAL statement_timeout = '5s'"))
            yield session
