"""Stock: suppliers, purchases, and every movement of an ingredient.

The movements table is the truth. A level is the sum of the movements, and
`StockLevel` only caches that sum so the screen does not add up thousands of
rows on every load. If the two ever disagree, the movements win and the cache
is rebuilt from them.

Quantities use the same convention as recipes: thousandths of the ingredient's
own unit, so 180 against something bought by the kilogram is 180 g.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id

# Why a quantity moved. Purchases and openings add; sales and waste take away.
MOVE_KINDS = ("opening", "purchase", "sale", "waste", "adjustment", "return")
MOVE_LABELS = {
    "opening": "Opening count",
    "purchase": "Bought in",
    "sale": "Used in an order",
    "waste": "Wasted",
    "adjustment": "Counted and corrected",
    "return": "Returned to supplier",
}
PURCHASE_STATUSES = ("draft", "received", "cancelled")


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    contact: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    phone: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    email: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    purchases: Mapped[list[Purchase]] = relationship(back_populates="supplier")


class StockLevel(Base):
    """What is on hand right now, and when to reorder."""

    __tablename__ = "stock_levels"

    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), primary_key=True)
    quantity_milli: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reorder_milli: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StockMove(Base, TimestampMixin):
    """One movement of one ingredient. Append-only: corrections are new rows."""

    __tablename__ = "stock_moves"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Signed: positive adds to stock, negative takes away.
    quantity_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    # What the moved quantity was worth, for the books at stage 7.
    value_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reference: Mapped[str] = mapped_column(String(40), default="", nullable=False, index=True)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    balance_milli: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Purchase(Base, TimestampMixin):
    """Goods bought from a supplier. Draft until the delivery is checked in."""

    __tablename__ = "purchases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    total_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    supplier: Mapped[Supplier] = relationship(back_populates="purchases", lazy="selectin")
    lines: Mapped[list[PurchaseLine]] = relationship(
        back_populates="purchase", cascade="all, delete-orphan", lazy="selectin",
    )


class PurchaseLine(Base):
    __tablename__ = "purchase_lines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(ForeignKey("purchases.id"), nullable=False, index=True)
    ingredient_id: Mapped[str] = mapped_column(ForeignKey("ingredients.id"), nullable=False)
    ingredient_name: Mapped[str] = mapped_column(String(80), nullable=False)
    unit: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity_milli: Mapped[int] = mapped_column(Integer, nullable=False)
    # What one whole unit cost on this delivery, which may differ from last time.
    unit_cost_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    line_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)

    purchase: Mapped[Purchase] = relationship(back_populates="lines")


class SupplierPayment(Base, TimestampMixin):
    """Money paid to a supplier, against one delivery.

    A delivery creates a debt when it is checked in. This is how the debt is
    settled — in full or in parts, since a supplier may be paid half now and
    half at the end of the month. Never edited: a mistake is a second row.
    """

    __tablename__ = "supplier_payments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    purchase_id: Mapped[str] = mapped_column(ForeignKey("purchases.id"), nullable=False, index=True)
    supplier_id: Mapped[str] = mapped_column(ForeignKey("suppliers.id"), nullable=False, index=True)
    # Which account the money left: cash in the drawer, the bank, mobile money.
    method: Mapped[str] = mapped_column(String(16), default="bank", nullable=False)
    amount_ngwee: Mapped[int] = mapped_column(Integer, nullable=False)
    reference: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    note: Mapped[str] = mapped_column(String(200), default="", nullable=False)
