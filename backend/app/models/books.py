"""The books: accounts, journal entries and their lines.

Double entry, kept honestly:

- Every entry's debits equal its credits, checked before it is written.
- A posted entry is never edited. A mistake is reversed by a second entry that
  mirrors the first, and both stay visible.
- Entries the system writes for itself (a sale, a delivery) carry the document
  they came from, so any figure in a statement can be traced back to the
  receipt or the invoice behind it.

Amounts are whole ngwee, as everywhere else.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id

ACCOUNT_TYPES = ("asset", "liability", "equity", "income", "expense")

# Which side increases an account. Assets and expenses grow by debit; the rest
# grow by credit. This one dict decides every sign in every statement.
NORMAL_SIDE = {
    "asset": "debit",
    "expense": "debit",
    "liability": "credit",
    "equity": "credit",
    "income": "credit",
}

ENTRY_SOURCES = ("manual", "sale", "refund", "purchase", "stock", "shift", "payroll", "opening")
ENTRY_STATUSES = ("draft", "posted", "reversed")


class Account(Base, TimestampMixin):
    """One line of the chart of accounts."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    type: Mapped[str] = mapped_column(String(12), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # A system account is one the posting rules need by name, so it cannot be
    # removed or have its type changed underneath them.
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Marks the accounts that are real money, for the cash flow statement.
    is_cash: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    lines: Mapped[list[JournalLine]] = relationship(back_populates="account")


class JournalEntry(Base, TimestampMixin):
    __tablename__ = "journal_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(24), unique=True, nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    memo: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual", nullable=False, index=True)
    # The receipt, invoice or till session this came from.
    reference: Mapped[str] = mapped_column(String(40), default="", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(12), default="posted", nullable=False, index=True)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    posted_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # A reversal points back at what it undoes, and the original is marked too.
    reverses_id: Mapped[str | None] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    reversed_by_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)

    lines: Mapped[list[JournalLine]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", lazy="selectin",
        order_by="JournalLine.position",
    )

    @property
    def total_ngwee(self) -> int:
        return sum(line.debit_ngwee for line in self.lines)


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    entry_id: Mapped[str] = mapped_column(ForeignKey("journal_entries.id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    debit_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    credit_ngwee: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memo: Mapped[str] = mapped_column(String(200), default="", nullable=False)

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship(back_populates="lines", lazy="selectin")
