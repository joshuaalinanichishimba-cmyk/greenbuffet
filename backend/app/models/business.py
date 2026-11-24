"""Promotions and customer feedback, as the demo has them.

Both are small on purpose. A promotion is a code, what it takes off, and the
smallest order it applies to. Feedback is a star rating and a sentence, tied
to the order it is about. Neither needs more to be useful, and each extra
field would be one more thing for a busy manager to fill in.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id

PROMO_KINDS = ("percent", "amount")
FEEDBACK_SOURCES = ("counter", "phone", "whatsapp", "other")


class Promotion(Base, TimestampMixin):
    """A code a cashier types at the till: STUDENT10, LUNCH15."""

    __tablename__ = "promotions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    kind: Mapped[str] = mapped_column(String(10), default="percent", nullable=False)
    # A percentage as a whole number (10 = 10%), or kwacha off as ngwee.
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Counted when the order it was used on is paid for, not when it is typed,
    # so an order that is cancelled does not count as a use.
    uses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discount_given_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Feedback(Base, TimestampMixin):
    """What a customer said about an order, written down by staff."""

    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    order_number: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 5
    comment: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(12), default="counter", nullable=False)
    customer_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
