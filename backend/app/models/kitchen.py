"""What the kitchen is making.

One row per item on a paid order. A separate table rather than extra columns
on the order, so an installed copy gains the kitchen screen by creating one
table and nothing already holding money is touched.

Times are kept at each step instead of a single "status changed" field, so
stage 9 can report how long food actually takes rather than guessing.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id

STATUSES = ("waiting", "preparing", "ready", "served")
NEXT_STATUS = {"waiting": "preparing", "preparing": "ready", "ready": "served"}
STATIONS = ("kitchen", "cold", "bar")


class KitchenItem(Base, TimestampMixin):
    """One line of a paid order, as the station that makes it sees it."""

    __tablename__ = "kitchen_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    order_line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id"), nullable=False)
    order_number: Mapped[str] = mapped_column(String(24), nullable=False, index=True)

    # Copied from the order line, so the board reads without joining back.
    product_name: Mapped[str] = mapped_column(String(90), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    choices: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    station: Mapped[str] = mapped_column(String(24), default="kitchen", nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(16), default="takeaway", nullable=False)
    customer_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)

    status: Mapped[str] = mapped_column(String(16), default="waiting", nullable=False, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    served_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    handled_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
