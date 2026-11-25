"""Running the system: controls, incidents, support tickets, repairs, errors
and security events.

These belong to the technical side, not the business. Nothing here holds
money, pay or prices. Where something touches business records (a repair
that posts a missing journal, say) it goes through the same services the
till uses, and the result is checked afterwards.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id

SEVERITIES = ("info", "low", "medium", "high", "critical")
INCIDENT_STATES = ("open", "investigating", "repairing", "monitoring", "resolved", "closed")
TICKET_STATES = ("new", "investigating", "waiting", "resolved", "closed")
PRIORITIES = ("low", "normal", "high", "urgent")


class FeatureControl(Base):
    """A switch that changes how the whole system behaves, for an emergency.

    electronic_payments  off = the till takes cash only; mobile money and card
                         already taken can still be matched and confirmed
    take_orders          off = no new orders (the kitchen finishes what it has)
    read_only            on  = nothing can be changed except by owners and IT
    """

    __tablename__ = "feature_controls"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    changed_by: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    service: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    status: Mapped[str] = mapped_column(String(14), default="open", nullable=False, index=True)
    impact: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reported_by: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    assigned_to: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    root_cause: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    prevention: Mapped[str] = mapped_column(Text, default="", nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Ticket(Base):
    """A problem reported by anyone at the restaurant."""

    __tablename__ = "support_tickets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    reporter: Mapped[str] = mapped_column(String(80), nullable=False)
    module: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    device: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    app_version: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    error_reference: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(14), default="new", nullable=False, index=True)
    assigned_to: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    resolution: Mapped[str] = mapped_column(Text, default="", nullable=False)
    incident_id: Mapped[str | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CaseNote(Base):
    """A line in the history of an incident or a ticket."""

    __tablename__ = "case_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    case_kind: Mapped[str] = mapped_column(String(10), nullable=False)   # incident, ticket
    case_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    by: Mapped[str] = mapped_column(String(80), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)


class RepairRun(Base):
    """One run of a predefined repair, from request to checked result."""

    __tablename__ = "repair_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    operation: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    risk: Mapped[str] = mapped_column(String(10), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)   # running, succeeded, failed, partial
    affected: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    result: Mapped[str] = mapped_column(Text, default="", nullable=False)
    verification: Mapped[str] = mapped_column(Text, default="", nullable=False)
    started_by: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ErrorRecord(Base):
    """Errors the server could not handle, grouped so a repeat is one row.

    Only what helps find the fault is kept: the kind of error, where it
    happened, a cleaned-up message. Never request bodies, tokens or passwords.
    """

    __tablename__ = "error_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    reference: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    module: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    path: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    method: Mapped[str] = mapped_column(String(8), default="", nullable=False)
    message: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    where: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(10), default="new", nullable=False)   # new, resolved
    version: Mapped[str] = mapped_column(String(40), default="", nullable=False)


class SecurityEvent(Base):
    """Something on the security side worth a look. An event is not an accusation."""

    __tablename__ = "security_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="low", nullable=False)
    detail: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    account: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    ip: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    path: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(10), default="open", nullable=False)   # open, reviewed
    note: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    reviewed_by: Mapped[str] = mapped_column(String(80), default="", nullable=False)
