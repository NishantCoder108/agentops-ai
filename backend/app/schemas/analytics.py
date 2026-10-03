import uuid
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.commerce import OrderStatus, RefundStatus

CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$", examples=["USD"])]


class Period(BaseModel):
    """An inclusive range of calendar days in UTC."""

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_order(self) -> "Period":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self

    def bounds(self) -> tuple[datetime, datetime]:
        """Return [start, end) as timezone-aware datetimes, so the whole end day is included."""
        start = datetime.combine(self.start_date, time.min, tzinfo=UTC)
        end = datetime.combine(self.end_date + timedelta(days=1), time.min, tzinfo=UTC)
        return start, end


class CurrencyRevenue(BaseModel):
    currency: str
    order_count: int
    gross_revenue: Decimal
    refunded_amount: Decimal
    net_revenue: Decimal
    average_order_value: Decimal


class RevenueSummary(BaseModel):
    operation: Literal["get_revenue_summary"] = "get_revenue_summary"
    period: Period
    counted_order_statuses: list[OrderStatus]
    currencies: list[CurrencyRevenue]


class OrderBreakdown(BaseModel):
    status: OrderStatus
    currency: str
    order_count: int
    total_amount: Decimal


class OrderSummary(BaseModel):
    operation: Literal["get_order_summary"] = "get_order_summary"
    period: Period
    order_count: int
    breakdown: list[OrderBreakdown]


class RefundBreakdown(BaseModel):
    status: RefundStatus
    currency: str
    refund_count: int
    total_amount: Decimal


class RefundSummary(BaseModel):
    operation: Literal["get_refund_summary"] = "get_refund_summary"
    period: Period
    refund_count: int
    breakdown: list[RefundBreakdown]


class TopCustomer(BaseModel):
    # No email or other contact data: tool results are sent to an external LLM provider.
    customer_id: uuid.UUID
    name: str
    order_count: int
    total_spent: Decimal


class TopCustomers(BaseModel):
    operation: Literal["get_top_customers"] = "get_top_customers"
    period: Period
    currency: str
    customers: list[TopCustomer]
