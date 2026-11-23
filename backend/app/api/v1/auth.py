"""Sign in, sign out, who am I, and changing your own password."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.access import LoginAttempt, User
from app.schemas.access import LoginIn, LoginOut, PasswordChangeIn, UserOut
from app.services.audit import record

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_FAILURES = 5
LOCKOUT_MINUTES = 15


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role_id=user.role_id,
        role_label=user.role.label,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
    )


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    email = body.email.strip().lower()
    now = datetime.now(timezone.utc)
    ip = request.client.host if request.client else ""

    since = now - timedelta(minutes=LOCKOUT_MINUTES)
    recent_failures = db.scalars(
        select(LoginAttempt).where(
            LoginAttempt.email == email,
            LoginAttempt.succeeded.is_(False),
            LoginAttempt.at >= since,
        )
    ).all()
    if len(recent_failures) >= MAX_FAILURES:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes.",
        )

    user = db.scalar(select(User).where(User.email == email))
    ok = bool(user and user.is_active and verify_password(body.password, user.password_hash))
    db.add(LoginAttempt(email=email, at=now, succeeded=ok, ip=ip))

    if not ok:
        db.commit()
        # The same message either way, so the form cannot be used to discover emails.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")

    token, expires = create_access_token(user.id, user.role_id)
    user.last_login_at = now
    record(db, user.name, "security", "Signed in", user.role.label)
    db.commit()
    db.refresh(user)

    return LoginOut(
        token=token,
        expires_at=expires.isoformat(),
        user=_user_out(user),
        permissions=user.role.permission_codes,
    )


@router.get("/me", response_model=LoginOut)
def me(user: User = Depends(current_user)) -> LoginOut:
    return LoginOut(
        token="",
        expires_at="",
        user=_user_out(user),
        permissions=user.role.permission_codes,
    )


@router.post("/change-password")
def change_password(
    body: PasswordChangeIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not correct.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a password you have not used here before.")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    record(db, user.name, "security", "Password changed", user.email)
    db.commit()
    return {"ok": True}
