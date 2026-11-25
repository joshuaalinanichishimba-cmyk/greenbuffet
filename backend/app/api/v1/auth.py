"""Sign in, sign out, who am I, and changing your own password."""
from datetime import datetime, timedelta, timezone
from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import current_user
from app.core.security import (
    create_access_token, create_ticket, decode_token, hash_password, password_problem, verify_password,
)
from app.models.access import EmailChallenge, LoginAttempt, Role, Setting, User, UserSession
from app.services import email as mail
from app.schemas.access import (
    CodeIn, LoginIn, LoginOut, LogoutIn, PasswordChangeIn, PasswordIn, TwoStepConfirmIn, TwoStepOffIn, UserOut,
)
from app.services import twostep
from app.services.accounts import (
    describe_device, end_sessions, has_two_step, notify, notify_owners, start_session, two_step_required,
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
        two_step_required=bool(db and not has_two_step(user) and two_step_required(db, user)),
        email_verified=user.email_verified_at is not None,
        two_step_method=user.two_step_method or ("app" if user.totp_enabled else ""),
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
                        needs_code=True, code_by="app", ticket=create_ticket(user.id, user.token_version or 0))
    if user.two_step_method == "email" and user.email_verified_at:
        return _email_sign_in_code(db, user)
    return _signed_in(db, user, request)


def _email_sign_in_code(db: Session, user: User) -> LoginOut:
    """Right password; now a code by email. No session exists until it is entered."""
    try:
        challenge, code = mail.issue(db, user, "sign_in", user.email)
        mail.send_code(db, user, "sign_in", user.email, code)
    except mail.TooSoon as exc:
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except mail.EmailNotSent as exc:
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"{exc} If you have recovery codes, ask IT to switch you to the app, "
                            "or use reset-owner on the server computer.")
    record(db, user.name, "security", "Sign-in code emailed", mail.mask(user.email))
    db.commit()
    return LoginOut(token="", expires_at="", user=_user_out(user, db), permissions=[], needs_code=True,
                    code_by="email", sent_to=mail.mask(user.email),
                    ticket=create_ticket(user.id, user.token_version or 0, challenge=challenge.id))


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
    cid = payload.get("cid")
    if cid:
        challenge = db.get(EmailChallenge, cid)
        if challenge and challenge.user_id != user.id:
            challenge = None
        try:
            mail.check(db, challenge, body.code)
            return _signed_in(db, user, request)
        except mail.CodeProblem as exc:
            if len(body.code.strip()) != 9:   # a recovery code is tried below
                _failed(db, user.email, request, "email codes")
                db.commit()
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))
    elif twostep.check_code(user.totp_secret, body.code):
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
    weak = password_problem(body.new_password, user.email, user.name)
    if weak:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, weak)
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
    if two_step_required(db, user) and not (user.two_step_method == "email" and user.email_verified_at):
        raise HTTPException(status.HTTP_409_CONFLICT, "Owner and IT accounts must keep two-step sign-in on. "
                            "Switch to email codes first if you want to stop using the app.")
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



# ---- email: sign-in code resend, confirming an address, changing it -----------

class TicketIn(BaseModel):
    ticket: str = Field(min_length=10, max_length=1000)


@router.post("/login/resend", response_model=LoginOut)
def resend_code(body: TicketIn, db: Session = Depends(get_db)) -> LoginOut:
    """A new emailed code for the same sign-in. The old code stops working."""
    payload = decode_token(body.ticket)
    if not payload or payload.get("purpose") != "two_step" or not payload.get("cid"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Enter your password again.")
    user = db.get(User, payload.get("sub"))
    if not user or not user.is_active or payload.get("v", 0) != (user.token_version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Enter your password again.")
    _locked_out(db, user.email)
    return _email_sign_in_code(db, user)


class CodeOnlyIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)


@router.post("/email/verify/start")
def verify_start(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if user.email_verified_at:
        return {"verified": True}
    try:
        challenge, code = mail.issue(db, user, "verify", user.email)
        mail.send_code(db, user, "verify", user.email, code)
    except mail.TooSoon as exc:
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except mail.EmailNotSent as exc:
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    db.commit()
    return {"sent_to": mail.mask(user.email), "minutes": mail.CODE_MINUTES}


@router.post("/email/verify/confirm")
def verify_confirm(body: CodeOnlyIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    challenge = db.scalar(select(EmailChallenge).where(
        EmailChallenge.user_id == user.id, EmailChallenge.purpose == "verify",
        EmailChallenge.used_at.is_(None), EmailChallenge.cancelled_at.is_(None)))
    try:
        mail.check(db, challenge, body.code)
    except mail.CodeProblem as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if challenge.email != user.email:
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "Your email changed since the code was sent. Ask for a new one.")
    user.email_verified_at = datetime.now(timezone.utc)
    record(db, user.name, "security", "Email address confirmed", mail.mask(user.email))
    db.commit()
    return {"verified": True}


class MethodIn(BaseModel):
    method: str = Field(pattern="^(email|app)$")


@router.post("/email/two-step")
def choose_method(body: MethodIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Use emailed codes for the second step. An authenticator app, if set up,
    keeps working too. Recovery codes are made if there are none yet, so a
    day without email does not lock anyone out."""
    import json
    if body.method == "email":
        if not user.email_verified_at:
            raise HTTPException(status.HTTP_409_CONFLICT, "Confirm your email address first.")
        if not mail.configured():
            raise HTTPException(status.HTTP_409_CONFLICT, "Email is not set up on this server yet. Ask IT.")
    elif not user.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Set up the authenticator app first.")
    user.two_step_method = body.method
    codes = []
    if not json.loads(user.recovery_codes or "[]"):
        codes, user.recovery_codes = twostep.new_recovery_codes()
    record(db, user.name, "security", "Two-step method chosen", body.method)
    notify(db, [user], "security", f"Two-step sign-in now uses {'email codes' if body.method == 'email' else 'the app'}",
           "", "/profile/security", optional=False)
    db.commit()
    return {"method": user.two_step_method, "recovery_codes": codes}


class EmailChangeIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    new_email: str = Field(min_length=5, max_length=160)


@router.post("/email/change/start")
def change_email_start(body: EmailChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Step one: password again, then a code to the new address and, if the
    current one is confirmed, a code to that too. Nothing changes until both
    are entered."""
    new_email = body.new_email.strip().lower()
    if "@" not in new_email or "." not in new_email.split("@")[-1] or " " in new_email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That is not an email address.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That password is not right.")
    if new_email == user.email:
        raise HTTPException(status.HTTP_409_CONFLICT, "That is already your email address.")
    if db.scalar(select(User.id).where(User.email == new_email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account.")
    group = __import__("uuid").uuid4().hex
    try:
        needs_old = user.email_verified_at is not None
        if needs_old:
            _, old_code = mail.issue(db, user, "change_old", user.email, group_id=group)
            mail.send_code(db, user, "change_old", user.email, old_code)
        _, new_code = mail.issue(db, user, "change_new", new_email, group_id=group)
        mail.send_code(db, user, "change_new", new_email, new_code)
    except mail.TooSoon as exc:
        db.commit()
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc))
    except mail.EmailNotSent as exc:
        db.commit()
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc))
    record(db, user.name, "security", "Email change started", f"{mail.mask(user.email)} to {mail.mask(new_email)}")
    db.commit()
    return {"group": group, "needs_old": needs_old, "old": mail.mask(user.email), "new": mail.mask(new_email)}


class EmailChangeConfirmIn(BaseModel):
    group: str = Field(min_length=10, max_length=40)
    new_code: str = Field(min_length=6, max_length=12)
    old_code: str = Field(default="", max_length=12)


@router.post("/email/change/confirm")
def change_email_confirm(body: EmailChangeConfirmIn, request: Request, user: User = Depends(current_user),
                         db: Session = Depends(get_db)) -> dict:
    found = {c.purpose: c for c in db.scalars(select(EmailChallenge).where(
        EmailChallenge.user_id == user.id, EmailChallenge.group_id == body.group)).all()}
    new = found.get("change_new")
    if not new:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Start the change again.")
    try:
        if "change_old" in found:
            mail.check(db, found["change_old"], body.old_code)
        mail.check(db, new, body.new_code)
    except mail.CodeProblem as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if db.scalar(select(User.id).where(User.email == new.email, User.id != user.id)):
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, "That email has just been taken by another account.")
    old_email = user.email
    # Tell the old address first, so a takeover is noticed even if it worked.
    mail.send_alert(db, user, "Your Green Buffet email address was changed", f"It is now {mail.mask(new.email)}.")
    user.email = new.email
    user.email_verified_at = datetime.now(timezone.utc)
    mail.cancel_all(db, user)
    db.query(LoginAttempt).filter(LoginAttempt.email == new.email).delete()
    ended = end_sessions(db, user, "password", user.name, keep=getattr(request.state, "session_id", None))
    mail.send_alert(db, user, "This is now your Green Buffet email address", f"It replaced {mail.mask(old_email)}.")
    record(db, user.name, "security", "Email address changed", f"{mail.mask(old_email)} to {mail.mask(new.email)}; "
           f"{ended} other device(s) signed out", user.id, before={"email": mail.mask(old_email)},
           after={"email": mail.mask(new.email)})
    notify_owners(db, "security_changed", f"{user.name} changed their email address", "", f"/team/{user.id}",
                  exclude=user.id)
    db.commit()
    return {"email": user.email}


# ---- forgotten passwords ------------------------------------------------------------

class ForgotIn(BaseModel):
    email: str = Field(min_length=3, max_length=160)


@router.post("/password/forgot")
def forgot(body: ForgotIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Always the same answer, so it cannot be used to find out who has an
    account. A link goes only to a confirmed address of an active account."""
    email = body.email.strip().lower()
    answer = {"message": "If that address belongs to an account with a confirmed email, a reset link is on its way. "
                         "It works for 30 minutes. If nothing arrives, ask an owner or manager."}
    user = db.scalar(select(User).where(User.email == email))
    from app.services.ops import security_event
    security_event(db, "password_reset_asked", "low", "Reset link requested", account=email,
                   ip=request.client.host if request.client else "", path=request.url.path, every_seconds=60)
    if user and user.is_active and user.email_verified_at:
        try:
            _, token = mail.issue(db, user, "reset", user.email, link=True)
            mail.send_reset(db, user, token)
            record(db, "System", "security", "Password reset link sent", mail.mask(email), user.id)
        except (mail.TooSoon, mail.EmailNotSent):
            pass
    db.commit()
    return answer


class ResetIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Field(min_length=1, max_length=100)


@router.post("/password/reset")
def reset(body: ResetIn, db: Session = Depends(get_db)) -> dict:
    challenge = mail.find_link(db, body.token)
    user = db.get(User, challenge.user_id) if challenge else None
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That link is not valid. Ask for a new one.")
    weak = password_problem(body.new_password, user.email, user.name)
    if weak:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, weak)
    try:
        mail.check(db, challenge, body.token)
    except mail.CodeProblem as exc:
        db.commit()
        msg = str(exc).replace("code", "link")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    user.password_hash = hash_password(body.new_password)
    user.must_change_password = False
    user.token_version = (user.token_version or 0) + 1
    end_sessions(db, user, "password", "password reset")
    mail.cancel_all(db, user)
    db.query(LoginAttempt).filter(LoginAttempt.email == user.email, LoginAttempt.succeeded.is_(False)).delete()
    record(db, user.name, "security", "Password reset by email link", mail.mask(user.email), user.id)
    notify(db, [user], "security", "Your password was reset", "Every device was signed out.", "/profile/security",
           "warn", optional=False)
    if user.role_id in ("owner", "it"):
        notify_owners(db, "security_changed", f"{user.name} reset their password by email", "", f"/team/{user.id}",
                      exclude=user.id)
    db.commit()
    return {"ok": True}
