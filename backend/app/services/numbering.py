"""Document numbers that stay unique when two people act at once.

Counting the rows that already exist and adding one looks right and works
perfectly until two tills take an order in the same moment: both count the same
number, both add one, and the second one fails on the unique index. Under a
lunch rush that is most of the orders.

This counter is a single statement. The database decides the next value while
holding the row, so two tills asking together get different numbers.
"""
from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.models.base import Base


class Counter(Base):
    """One row per series: orders for today, journals for this month."""

    __tablename__ = "counters"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


def next_in_series(db: Session, series: str) -> int:
    """The next number in a series, atomically.

    The insert-or-add is one statement, so nothing can slip between reading the
    old value and writing the new one.

    It runs on the caller's own session and does not commit. The row it touches
    stays locked until that request finishes, so a second till asking for a
    number waits a few milliseconds and then gets the next one. An order takes
    far less time than a customer does, so the queue never builds.

    Taking a separate connection would release the lock sooner, but every
    request would then need two connections at once, and a busy lunch would
    empty the pool and wedge the whole system — which is exactly what happened
    when it was tried.
    """
    return int(
        db.execute(
            text(
                "INSERT INTO counters (key, value) VALUES (:key, 1) "
                "ON CONFLICT (key) DO UPDATE SET value = counters.value + 1 "
                "RETURNING value"
            ),
            {"key": series[:40]},
        ).scalar_one()
    )


def numbered(db: Session, prefix: str, width: int = 3) -> str:
    """`GB-20261123-014` — the prefix is the series, so counting restarts
    naturally each day or month without anything having to reset it."""
    return f"{prefix}{next_in_series(db, prefix):0{width}d}"
