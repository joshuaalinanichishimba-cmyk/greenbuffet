"""Sign in, sign out, who am I, and changing your own password."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import current_user
from app.core.security import create_access_token, create_ticket, decode_token, hash_password, verify_password
from app.models.access import LoginAttempt, Role, Setting, User, UserSession
from app.schemas.access import (
    CodeIn, LoginIn, LoginOut, LogoutIn, PasswordChangeIn, PasswordIn, TwoStepConfirmIn, TwoStepOffIn, UserOut,
)
from app.services import twostep
from app.services.accounts import (
    describe_device, end_sessions, notify, notify_owners, start_session, two_step_required,
)
from app.services.audit import record

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_FAILURES = 5
LOCKOUT_MINUTES = 15


def _user_out(user: User, db: Session | None = None) -> UserOut:
    return UserOut(
        id=user.id,
        name=user.name,
        email=user.email,
        role_id=user.role_id,
        role_label=user.role.label,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        photo_id=user.photo_id,
        totp_enabled=user.totp_enabled,
        two_step_required=bool(db and not user.totp_enabled and two_step_required(db, user)),
    )


def _failed(db: Session, email: str, request: Request, why: str) -> None:
    """Counts a failed try and, the moment an account locks, tells the owners."""
    moment = datetime.now(timezone.utc)
    device, browser = describe_device(request.headers.get("user-agent", ""))
    db.add(LoginAttempt(email=email, at=moment, succeeded=False,
                        ip=request.client.host if request.client else "", device=f"{device}, {browser}"))
    from app.services.ops import security_event
    security_event(db, "failed_sign_in", "low", f"Wrong {why}", account=email,
                   ip=request.client.host if request.client else "", path=request.url.path, every_seconds=60)
    db.flush()
    since = moment - timedelta(minutes=LOCKOUT_MINUTES)
    failures = db.scalar(select(func.count(LoginAttempt.id)).where(
        LoginAttempt.email == email, LoginAttempt.succeeded.is_(False), LoginAttempt.at >= since)) or 0
    if failures == MAX_FAILURES:
        known = db.scalar(select(User).where(User.email == email))
        record(db, "System", "security", "Sign-in locked", f"{MAX_FAILURES} wrong {why} in {LOCKOUT_MINUTES} min", email)
        security_event(db, "sign_in_locked", "high", f"{MAX_FAILURES} wrong {why} in {LOCKOUT_MINUTES} minutes",
                       account=email, ip=request.client.host if request.client else "", path=request.url.path,
                       every_seconds=0)
        notify_owners(db, "failed_logins", f"{known.name if known else email}: sign-in locked",
                      f"{MAX_FAILURES} wrong {why} in {LOCKOUT_MINUTES} minutes from {device}, {browser}. "
                      "It unlocks by itself; a password reset unlocks it now.",
                      f"/team/{known.id}" if known else "/team", level="warn")
        if known:
            notify(db, [known], "failed_logins", "Someone is trying to sign in as you",
                   f"{MAX_FAILURES} wrong {why} on your account.", "/profile/security", "warn", optional=False)


def _locked_out(db: Session, email: str) -> None:
    since = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)
    failures = db.scalar(select(func.count(LoginAttempt.id)).where(
        LoginAttempt.email == email, LoginAttempt.succeeded.is_(False), LoginAttempt.at >= since)) or 0
    if failures >= MAX_FAILURES:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed attempts. Try again in {LOCKOUT_MINUTES} minutes.",
        )


def _signed_in(db: Session, user: User, request: Request) -> LoginOut:
    """The last step of every sign-in: a session, a token, a record."""
    moment = datetime.now(timezone.utc)
    device, browser = describe_device(request.headers.get("user-agent", ""))
    db.add(LoginAttempt(email=user.email, at=moment, succeeded=True,
                        ip=request.client.host if request.client else "", device=f"{device}, {browser}"))
    token, expires, session = start_session(db, user, request)
    user.last_login_at = moment
    record(db, user.name, "security", "Signed in", f"{user.role.label} · {device}, {browser}")
    db.commit()
    db.refresh(user)
    return LoginOut(
        token=token,
        expires_at=expires.isoformat(),
        user=_user_out(user, db),
        permissions=user.role.permission_codes,
        session_id=session.id,
    )


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


# What each kind of account opens on, in the words of the sign-in screen.
SIGN_IN_ORDER = ["owner", "manager", "accountant", "cashier", "kitchen", "it"]
SIGN_IN_SEES = {
    "owner": "Everything: sales, money, staff and settings",
    "manager": "Service, approvals at the till, menu, stock, staff and reports",
    "accountant": "Takings, the books, suppliers and payroll",
    "cashier": "The till, orders and collection",
    "kitchen": "The kitchen display, sold-out items, stock counts and waste",
}


@router.get("/roles")
def sign_in_roles(db: Session = Depends(get_db)) -> list[dict]:
    """The kinds of account someone can sign in as, for the sign-in screen.

    Public, because it is shown before anyone signs in. The seven standard
    roles always appear, like the demo's account cards; a role the owner made
    up appears once someone has an account with it. Each card carries the
    names and emails of its active accounts unless the owner has switched
    that off; never a password, and never a disabled account.
    """
    roles = db.scalars(select(Role)).all()
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.name)).all()
    in_use = {u.role_id for u in users}
    rows = [r for r in roles if r.id in SIGN_IN_ORDER or r.id in in_use]
    rows.sort(key=lambda r: (SIGN_IN_ORDER.index(r.id) if r.id in SIGN_IN_ORDER else 99, r.label))

    # One tap to sign in, like the demo: each card lists its people, and a tap
    # fills the email. This is a counter system on the restaurant's own
    # network, where everyone already knows who works there; the owner can
    # still switch it off in Settings, and the password is always typed.
    setting = db.get(Setting, "signin.show_accounts")
    show = (setting.value if setting else "true") != "false"
    # Test mode (scripts\test-sign-in.ps1): the shared test password rides
    # along so a tap and Enter signs in, like the demo. Never in production,
    # whatever the switch says.
    fill = db.get(Setting, "signin.fill_passwords")
    test_password = None
    if show and fill and fill.value == "true" and settings.ENVIRONMENT != "production":
        from app.test_sign_in import TEST_PASSWORD
        test_password = TEST_PASSWORD
    by_role: dict[str, list[dict]] = {}
    if show:
        for u in users:
            entry = {"name": u.name, "email": u.email}
            if test_password:
                entry["password"] = test_password
            by_role.setdefault(u.role_id, []).append(entry)
    return [
        {"id": r.id, "label": r.label, "sees": SIGN_IN_SEES.get(r.id) or r.description,
         "accounts": by_role.get(r.id, [])}
        for r in rows
    ]


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    email = body.email.strip().lower()
    _locked_out(db, email)

    user = db.scalar(select(User).where(User.email == email))
    ok = bool(user and user.is_active and verify_password(body.password, user.password_hash))
    if not ok:
        _failed(db, email, request, "passwords")
        db.commit()
        # The same message either way, so the form cannot be used to discover emails.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email or password is incorrect.")

    # Checked only after the password, so it reveals nothing to a guesser,
    # and not counted as a failure: the person knows their password, they
    # just picked the wrong kind of account.
    if body.role_id and body.role_id != user.role_id:
        chosen = db.get(Role, body.role_id)
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"This is {_article(user.role.label)} {user.role.label} account, not "
            f"{_article(chosen.label if chosen else body.role_id)} {chosen.label if chosen else body.role_id} one. "
            f"Choose {user.role.label} and sign in again.",
        )

    if user.totp_enabled:
        # Right password; now the code from the phone.
        return LoginOut(token="", expires_at="", user=_user_out(user, db), permissions=[],
                        needs_code=True, ticket=create_ticket(user.id, user.token_version or 0))
    return _signed_in(db, user, request)


@router.post("/login/code", response_model=LoginOut)
def login_code(body: CodeIn, request: Request, db: Session = Depends(get_db)) -> LoginOut:
    """The second step: the six-digit code, or one of the recovery codes."""
    payload = decode_token(body.ticket)
    if not payload or payload.get("purpose") != "two_step":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That took too long. Enter your password again.")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active or payload.get("v", 0) != (user.token_version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Enter your password again.")
    _locked_out(db, user.email)
    if twostep.check_code(user.totp_secret, body.code):
        return _signed_in(db, user, request)
    remaining = twostep.use_recovery_code(user.recovery_codes, body.code)
    if remaining is not None:
        user.recovery_codes = remaining
        left = len(__import__("json").loads(remaining))
        record(db, user.name, "security", "Recovery code used", f"{left} left")
        notify(db, [user], "security", "A recovery code was used to sign in",
               f"{left} recovery codes are left. Make new ones under Security if you are running low.",
               "/profile/security", "warn", optional=False)
        return _signed_in(db, user, request)
    _failed(db, user.email, request, "two-step codes")
    db.commit()
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That code is not right. Check the time on your phone.")


def _session_of(request: Request, db: Session) -> UserSession | None:
    sid = getattr(request.state, "session_id", None)
    return db.get(UserSession, sid) if sid else None


@router.post("/logout")
def logout(body: LogoutIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Ends this device's session. The token stops working at once."""
    session = _session_of(request, db)
    if session and not session.ended_at:
        session.ended_at = datetime.now(timezone.utc)
        session.end_reason = "switched" if body.switch else "signed_out"
        session.ended_by = user.name
    record(db, user.name, "security", "Switched person" if body.switch else "Signed out",
           f"{session.device}, {session.browser}" if session else "")
    db.commit()
    return {"ok": True}


@router.post("/lock")
def lock(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Locks this screen. Until it is unlocked the server refuses its token."""
    session = _session_of(request, db)
    if not session:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sign in again to use the lock screen.")
    if not session.locked_at:
        session.locked_at = datetime.now(timezone.utc)
        record(db, user.name, "security", "Screen locked", f"{session.device}, {session.browser}")
        db.commit()
    return {"ok": True}


@router.post("/unlock")
def unlock(body: PasswordIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Only the person who locked the screen can unlock it, with their password."""
    session = _session_of(request, db)
    if not session:
        raise HTTPException(status.HTTP_409_CONFLICT, "Sign in again.")
    _locked_out(db, user.email)
    if not verify_password(body.password, user.password_hash):
        _failed(db, user.email, request, "passwords at the lock screen")
        since = datetime.now(timezone.utc) - timedelta(minutes=LOCKOUT_MINUTES)
        failures = db.scalar(select(func.count(LoginAttempt.id)).where(
            LoginAttempt.email == user.email, LoginAttempt.succeeded.is_(False), LoginAttempt.at >= since)) or 0
        if failures >= MAX_FAILURES:
            # Too many guesses at a locked screen: sign this device out.
            session.ended_at, session.end_reason, session.ended_by = datetime.now(timezone.utc), "signed_out", "System"
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That password is not right.")
    session.locked_at = None
    now = datetime.now(timezone.utc)
    session.last_active_at = session.last_seen_at = now
    record(db, user.name, "security", "Screen unlocked", f"{session.device}, {session.browser}")
    db.commit()
    return {"ok": True}


@router.get("/me", response_model=LoginOut)
def me(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> LoginOut:
    return LoginOut(
        token="",
        expires_at="",
        user=_user_out(user, db),
        permissions=user.role.permission_codes,
        session_id=getattr(request.state, "session_id", None) or "",
    )


@router.post("/change-password")
def change_password(
    body: PasswordChangeIn,
    request: Request,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password is not correct.")
    if body.new_password == body.current_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a password you have not used here before.")
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    # Sessions on other devices end; this one gets a fresh token.
    user.token_version = (user.token_version or 0) + 1
    sid = getattr(request.state, "session_id", None)
    ended = end_sessions(db, user, "password", user.name, keep=sid)
    record(db, user.name, "security", "Password changed", f"{user.email}; {ended} other device(s) signed out")
    notify(db, [user], "security", "Your password was changed",
           "If this was not you, tell an owner straight away.", "/profile/security", optional=False)
    if user.role_id == "owner":
        notify_owners(db, "security_changed", f"{user.name} changed their password", "", f"/team/{user.id}",
                      exclude=user.id)
    session = db.get(UserSession, sid) if sid else None
    db.commit()
    token, expires = create_access_token(
        user.id, user.role_id, user.token_version, sid, session.expires_at if session else None)
    return {"ok": True, "token": token, "expires_at": expires.isoformat()}


# ---- two-step sign-in ---------------------------------------------------------

@router.post("/two-step/start")
def two_step_start(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """A new secret for the authenticator app. Not in use until a code confirms it."""
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is already on.")
    user.totp_secret = twostep.new_secret()
    db.commit()
    # Shown once, to this person, to put into their app. Never logged.
    return {"secret": user.totp_secret, "uri": twostep.setup_uri(user.totp_secret, user.email)}


@router.post("/two-step/confirm")
def two_step_confirm(body: TwoStepConfirmIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is already on.")
    if not twostep.check_code(user.totp_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code is not right. Check the time on your phone and try the newest code.")
    codes, stored = twostep.new_recovery_codes()
    user.totp_enabled = True
    user.recovery_codes = stored
    record(db, user.name, "security", "Two-step sign-in turned on", user.email)
    notify(db, [user], "security", "Two-step sign-in is on",
           "Each sign-in now needs a code from your phone.", "/profile/security", optional=False)
    if user.role_id != "owner":
        notify_owners(db, "security_changed", f"{user.name} turned on two-step sign-in", "", f"/team/{user.id}")
    else:
        notify_owners(db, "security_changed", f"{user.name} turned on two-step sign-in", "", f"/team/{user.id}",
                      exclude=user.id)
    db.commit()
    return {"ok": True, "recovery_codes": codes}


@router.post("/two-step/recovery-codes")
def new_recovery(body: PasswordIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Turn on two-step sign-in first.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That password is not right.")
    codes, stored = twostep.new_recovery_codes()
    user.recovery_codes = stored
    record(db, user.name, "security", "Recovery codes replaced", user.email)
    db.commit()
    return {"recovery_codes": codes}


@router.post("/two-step/off")
def two_step_off(body: TwoStepOffIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if two_step_required(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Owner accounts must keep two-step sign-in on.")
    if not user.totp_enabled:
        return {"ok": True}
    if not verify_password(body.password, user.password_hash) or not twostep.check_code(user.totp_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The password or the code is not right.")
    user.totp_enabled, user.totp_secret, user.recovery_codes = False, "", "[]"
    record(db, user.name, "security", "Two-step sign-in turned off", user.email)
    notify(db, [user], "security", "Two-step sign-in was turned off", "", "/profile/security", "warn", optional=False)
    notify_owners(db, "security_changed", f"{user.name} turned off two-step sign-in", "", f"/team/{user.id}",
                  level="warn", exclude=user.id)
    db.commit()
    return {"ok": True}
