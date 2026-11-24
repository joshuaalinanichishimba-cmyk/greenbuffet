"""A manager's approval, given on the spot at the till.

Some things a cashier may start but not finish alone: a discount above their
limit, a refund. The manager steps up to the till and types their own email
and password into the approval box; the server checks that person has the
needed permission and is not the cashier asking, and records them as the
approver. The password is checked like a sign-in (wrong ones count towards
the same 15-minute lock) and is never stored or logged.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import verify_password
from app.models.access import LoginAttempt, Setting, User


class ApprovalIn(BaseModel):
    email: str = Field(max_length=120)
    password: str = Field(min_length=1, max_length=200)


def approve(db: Session, approval: ApprovalIn | None, permission: str, asked_by: User, what: str) -> User:
    """Returns the approving user, or refuses with a message for the till."""
    if approval is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"{what} needs a manager's approval. Ask a manager to approve it on this till.",
        )
    email = approval.email.strip().lower()
    now = datetime.now(timezone.utc)
    failures = db.scalar(select(func.count(LoginAttempt.id)).where(
        LoginAttempt.email == email, LoginAttempt.succeeded.is_(False),
        LoginAttempt.at >= now - timedelta(minutes=15),
    )) or 0
    if failures >= 5:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many wrong passwords for that manager. Try again in 15 minutes.")
    approver = db.scalar(select(User).where(User.email == email))
    ok = bool(approver and approver.is_active and verify_password(approval.password, approver.password_hash))
    db.add(LoginAttempt(email=email, at=now, succeeded=ok, ip="approval at the till"))
    if not ok:
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That manager's email or password is not right.")
    if approver.id == asked_by.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Someone else has to approve this.")
    if permission not in approver.role.permission_codes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{approver.name} is not allowed to approve this.")
    return approver


def setting_int(db: Session, key: str, fallback: int) -> int:
    row = db.get(Setting, key)
    try:
        return int(float(row.value)) if row and row.value.strip() else fallback
    except ValueError:
        return fallback
