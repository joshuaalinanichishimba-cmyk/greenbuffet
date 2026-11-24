"""Customers: the regulars found by phone number at the till.

The phone number is the customer's identity. In Zambia almost nobody gives an
email and everybody has a phone, so it is how a stamp card is found at the
counter. Deliveries, functions and the message outbox that once lived here
were removed in stage 20; their tables were dropped after a backup.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id




def normalise_phone(raw: str) -> str:
    """One shape for a Zambian number, so the same person is found every time.

    Zambian mobile numbers are nine digits after the country code: 0960554543
    locally, +260960554543 internationally. Both are stored as 0960554543, and
    anything that is not a digit is dropped first, so spaces, brackets and
    dashes that people type do not create a second customer.
    """
    digits = "".join(c for c in (raw or "") if c.isdigit())
    if digits.startswith("260") and len(digits) == 12:
        digits = "0" + digits[3:]
    elif len(digits) == 9 and digits[0] == "9":
        digits = "0" + digits
    return digits[:24]


class Customer(Base, TimestampMixin):
    """Someone who has ordered at least once, found by phone number."""

    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    phone: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    area: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)

    # Loyalty, as the demo proposes it: every paid bowl or burrito earns a
    # stamp, and a full card makes the next one free. The balance is kept here
    # so the till need not add up a ledger at the counter; the entries below
    # are the proof of it.
    stamps: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    orders_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    spent_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_order_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entries: Mapped[list[PointsEntry]] = relationship(
        back_populates="customer", cascade="all, delete-orphan", lazy="selectin",
    )


class PointsEntry(Base, TimestampMixin):
    """Every stamp earned or spent, so a card can always be explained.

    The table kept its first name from when the scheme was points. `points`
    holds the change in stamps.
    """

    __tablename__ = "points_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    order_id: Mapped[str | None] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False)  # negative when spent
    balance_after: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reason: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="entries")
