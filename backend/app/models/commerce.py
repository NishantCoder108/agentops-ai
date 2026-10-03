import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column
from app.models.organization import Organization

# Up to 9,999,999,999.99; exact decimal arithmetic, never float.
Money = Numeric(12, 2)


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class RefundStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROCESSED = "processed"


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An end customer of an organization (the business data the agent answers questions about)."""

    __tablename__ = "customers"
    __table_args__ = (UniqueConstraint("organization_id", "email"),)

    # The (organization_id, email) unique index also serves lookups by organization.
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT")
    )
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))

    organization: Mapped[Organization] = relationship(back_populates="customers")
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Order(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="total_amount_non_negative"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="currency_iso_4217"),
    )

    # Financial records are never cascade-deleted: deleting a customer with orders fails.
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[OrderStatus] = mapped_column(
        enum_column(OrderStatus, "status"), default=OrderStatus.PENDING
    )
    total_amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))

    customer: Mapped[Customer] = relationship(back_populates="orders")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="order")


class Refund(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A (partial or full) refund of an order, in the order's currency."""

    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    status: Mapped[RefundStatus] = mapped_column(
        enum_column(RefundStatus, "status"), default=RefundStatus.REQUESTED
    )
    amount: Mapped[Decimal] = mapped_column(Money)
    reason: Mapped[str | None] = mapped_column(Text)

    order: Mapped[Order] = relationship(back_populates="refunds")
