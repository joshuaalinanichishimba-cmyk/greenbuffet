"""Shared column conventions for every table."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def new_id() -> str:
    return uuid.uuid4().hex


class TimestampMixin:
    """Every row records when it was made and by whom."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
