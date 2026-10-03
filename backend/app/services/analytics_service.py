import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.commerce import Customer, Order, OrderStatus, Refund, RefundStatus
from app.schemas.analytics import (
    CurrencyRevenue,
    OrderBreakdown,
    OrderSummary,
    Period,
    RefundBreakdown,
    RefundSummary,
    RevenueSummary,
    TopCustomer,
    TopCustomers,
)

# Orders that represent money received. Pending and cancelled orders are not revenue.
REVENUE_STATUSES = (OrderStatus.PAID, OrderStatus.SHIPPED, OrderStatus.DELIVERED)
_ZERO = Decimal("0.00")
_CENT = Decimal("0.01")


def _money(value: Decimal | None) -> Decimal:
    return (value or _ZERO).quantize(_CENT, ROUND_HALF_UP)


class AnalyticsService:
    """Predefined, read-only business analytics for one organization.

    Every query is fixed SQLAlchemy code scoped to `organization_id`; callers only choose which
    query to run and supply validated parameters. Amounts are never summed across currencies.
    """

    def __init__(self, session: AsyncSession, organization_id: uuid.UUID) -> None:
        self._session = session
        self._organization_id = organization_id

    async def revenue_summary(self, period: Period, currency: str | None = None) -> RevenueSummary:
        """Gross revenue of orders placed in the period, minus refunds processed in the period."""
        start, end = period.bounds()

        orders = (
            select(Order.currency, func.count(Order.id), func.sum(Order.total_amount))
            .join(Order.customer)
            .where(
                Customer.organization_id == self._organization_id,
                Order.status.in_(REVENUE_STATUSES),
                Order.created_at >= start,
                Order.created_at < end,
            )
            .group_by(Order.currency)
        )
        refunds = (
            select(Order.currency, func.sum(Refund.amount))
            .join(Refund.order)
            .join(Order.customer)
            .where(
                Customer.organization_id == self._organization_id,
                Refund.status == RefundStatus.PROCESSED,
                Refund.created_at >= start,
                Refund.created_at < end,
            )
            .group_by(Order.currency)
        )
        if currency is not None:
            orders = orders.where(Order.currency == currency)
            refunds = refunds.where(Order.currency == currency)

        gross = {row[0]: (row[1], row[2]) for row in await self._session.execute(orders)}
        refunded = {row[0]: row[1] for row in await self._session.execute(refunds)}

        currencies = []
        for code in sorted(gross.keys() | refunded.keys()):
            order_count, raw_gross = gross.get(code, (0, _ZERO))
            gross_revenue = _money(raw_gross)
            refunded_amount = _money(refunded.get(code))
            currencies.append(
                CurrencyRevenue(
                    currency=code,
                    order_count=order_count,
                    gross_revenue=gross_revenue,
                    refunded_amount=refunded_amount,
                    net_revenue=_money(gross_revenue - refunded_amount),
                    average_order_value=(
                        _money(gross_revenue / order_count) if order_count else _ZERO
                    ),
                )
            )

        return RevenueSummary(
            period=period, counted_order_statuses=list(REVENUE_STATUSES), currencies=currencies
        )

    async def order_summary(self, period: Period, currency: str | None = None) -> OrderSummary:
        """Orders placed in the period, by status and currency."""
        start, end = period.bounds()

        query = (
            select(Order.status, Order.currency, func.count(Order.id), func.sum(Order.total_amount))
            .join(Order.customer)
            .where(
                Customer.organization_id == self._organization_id,
                Order.created_at >= start,
                Order.created_at < end,
            )
            .group_by(Order.status, Order.currency)
            .order_by(Order.currency, Order.status)
        )
        if currency is not None:
            query = query.where(Order.currency == currency)

        breakdown = [
            OrderBreakdown(status=status, currency=code, order_count=count, total_amount=_money(total))
            for status, code, count, total in await self._session.execute(query)
        ]
        return OrderSummary(
            period=period,
            order_count=sum(row.order_count for row in breakdown),
            breakdown=breakdown,
        )

    async def refund_summary(self, period: Period, currency: str | None = None) -> RefundSummary:
        """Refunds created in the period, by status and (order) currency."""
        start, end = period.bounds()

        query = (
            select(Refund.status, Order.currency, func.count(Refund.id), func.sum(Refund.amount))
            .join(Refund.order)
            .join(Order.customer)
            .where(
                Customer.organization_id == self._organization_id,
                Refund.created_at >= start,
                Refund.created_at < end,
            )
            .group_by(Refund.status, Order.currency)
            .order_by(Order.currency, Refund.status)
        )
        if currency is not None:
            query = query.where(Order.currency == currency)

        breakdown = [
            RefundBreakdown(status=status, currency=code, refund_count=count, total_amount=_money(total))
            for status, code, count, total in await self._session.execute(query)
        ]
        return RefundSummary(
            period=period,
            refund_count=sum(row.refund_count for row in breakdown),
            breakdown=breakdown,
        )

    async def top_customers(self, period: Period, currency: str, limit: int) -> TopCustomers:
        """Customers ranked by gross spend on revenue orders placed in the period, in one currency."""
        start, end = period.bounds()
        total_spent = func.sum(Order.total_amount)

        query = (
            select(Customer.id, Customer.name, func.count(Order.id), total_spent)
            .join(Order.customer)
            .where(
                Customer.organization_id == self._organization_id,
                Order.status.in_(REVENUE_STATUSES),
                Order.currency == currency,
                Order.created_at >= start,
                Order.created_at < end,
            )
            .group_by(Customer.id, Customer.name)
            .order_by(total_spent.desc(), func.count(Order.id).desc(), Customer.id)
            .limit(limit)
        )

        customers = [
            TopCustomer(customer_id=customer_id, name=name, order_count=count, total_spent=_money(spent))
            for customer_id, name, count, spent in await self._session.execute(query)
        ]
        return TopCustomers(period=period, currency=currency, customers=customers)
