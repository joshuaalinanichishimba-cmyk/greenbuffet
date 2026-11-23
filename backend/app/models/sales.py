"""Orders, payments and cash shifts.

Three rules shape these tables:

1. Prices are copied onto the order line when it is sold. A price change
   tomorrow must never alter what a receipt from today says.
2. Money is whole ngwee, as everywhere else, and is worked out on the server.
   What the browser sends is what was ordered, never what it costs.
3. Nothing is edited after payment. A mistake is cancelled or refunded, and
   both leave their own row.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id

ORDER_TYPES = ("takeaway", "eat_in", "delivery")
ORDER_STATUSES = ("open", "paid", "cancelled")
PAYMENT_METHODS = ("cash", "airtel", "mtn", "zamtel", "card", "account")
METHOD_LABELS = {
    "cash": "Cash",
    "airtel": "Airtel Money",
    "mtn": "MTN MoMo",
    "zamtel": "Zamtel Kwacha",
    "card": "Card",
    "account": "On account",
    "simulated": "Simulated",
}


class Shift(Base, TimestampMixin):
    """One cashier's turn at the till, from opening float to counted cash."""

    __tablename__ = "shifts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    opened_by: Mapped[str] = mapped_column(String(80), nullable=False)
    opened_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    float_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # What the drawer should hold, what it actually held, and the gap between.
    expected_ngwee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    counted_ngwee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variance_ngwee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    orders: Mapped[list[Order]] = relationship(back_populates="shift")

    @property
    def is_open(self) -> bool:
        return self.closed_at is None


class Order(Base, TimestampMixin):
    """One sale. Totals are stored, not recalculated, once it is paid."""

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    shift_id: Mapped[str | None] = mapped_column(ForeignKey("shifts.id"), nullable=True, index=True)
    order_type: Mapped[str] = mapped_column(String(16), default="takeaway", nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)

    customer_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    customer_phone: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    subtotal_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # VAT is inside the price, so this is the share of the total that is tax.
    vat_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cancel_reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    shift: Mapped[Shift | None] = relationship(back_populates="orders")
    lines: Mapped[list[OrderLine]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin",
        order_by="OrderLine.position",
    )
    payments: Mapped[list[Payment]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin",
        order_by="Payment.created_at",
    )

    @property
    def paid_ngwee(self) -> int:
        return sum(p.amount_ngwee for p in self.payments if not p.is_refund)

    @property
    def refunded_ngwee(self) -> int:
        return sum(p.amount_ngwee for p in self.payments if p.is_refund)

    @property
    def outstanding_ngwee(self) -> int:
        return self.total_ngwee - self.paid_ngwee + self.refunded_ngwee


class OrderLine(Base):
    """One item on the order, with its price as it was at the time."""

    __tablename__ = "order_lines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"), nullable=False)
    product_name: Mapped[str] = mapped_column(String(90), nullable=False)
    product_code: Mapped[str] = mapped_column(String(24), nullable=False)
    station: Mapped[str] = mapped_column(String(24), default="kitchen", nullable=False)

    unit_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    options_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    line_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    vat_rate: Mapped[int] = mapped_column(Integer, default=16, nullable=False)
    note: Mapped[str] = mapped_column(String(160), default="", nullable=False)

    order: Mapped[Order] = relationship(back_populates="lines")
    options: Mapped[list[OrderLineOption]] = relationship(
        back_populates="line", cascade="all, delete-orphan", lazy="selectin",
    )


class OrderLineOption(Base):
    """A choice made on a line: the base, the protein, each topping."""

    __tablename__ = "order_line_options"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id"), nullable=False, index=True)
    option_item_id: Mapped[str] = mapped_column(ForeignKey("option_items.id"), nullable=False)
    group_name: Mapped[str] = mapped_column(String(60), nullable=False)
    item_name: Mapped[str] = mapped_column(String(60), nullable=False)
    price_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    line: Mapped[OrderLine] = relationship(back_populates="options")


class Payment(Base, TimestampMixin):
    """Money taken, or given back. Never edited once written."""

    __tablename__ = "payments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    shift_id: Mapped[str | None] = mapped_column(ForeignKey("shifts.id"), nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    # Cash only: what the customer handed over and what went back.
    tendered_ngwee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    change_ngwee: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Mobile money or card: the operator's transaction number.
    reference: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    is_refund: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    order: Mapped[Order] = relationship(back_populates="payments")


class IdempotencyKey(Base, TimestampMixin):
    """Stops a retried request from charging twice.

    The browser sends a key with every write. If the same key arrives again,
    the stored answer is returned instead of taking the money a second time.
    """

    __tablename__ = "idempotency_keys"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    result_id: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[str] = mapped_column(Text, default="", nullable=False)

    __table_args__ = (UniqueConstraint("key", "scope", name="uq_idempotency"),)
