"""Files the business keeps: dish photographs, invoices, staff documents.

The file itself is written to disk under `backend/uploads`, not into the
database. A database holding megabytes of photographs becomes slow to back up
and awkward to restore, and the backup script already copies the folder.

Each row records what the file is attached to — a menu item, a supplier, an
employee — so a photograph can be found from the thing it belongs to.
"""
from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id

# What a file can be attached to.
ATTACH_TO = ("product", "supplier", "employee", "purchase", "business", "other")
KINDS = ("photo", "invoice", "contract", "certificate", "receipt", "other")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), default="other", nullable=False, index=True)
    attached_to: Mapped[str] = mapped_column(String(16), default="other", nullable=False, index=True)
    attached_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    # Where it sits under backend/uploads, kept relative so the folder can move.
    path: Mapped[str] = mapped_column(String(240), nullable=False)
    thumb_path: Mapped[str | None] = mapped_column(String(240), nullable=True)
    media_type: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    # A product shows one photograph on the till; this marks which.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
