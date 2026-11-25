"""Sending email, and the one-time codes and links that go by email.

Sending is plain SMTP, so any provider works: Gmail with an App Password to
start, then a business mailbox or a transactional service (Resend, Brevo,
Postmark, Amazon SES all offer SMTP) once the restaurant has its own domain.
Changing provider is a change to `.env`, not to the code.

Codes are six digits from the operating system's secure random source. Only
an HMAC of each code (keyed with the server's secret) is stored, so a copy of
the database does not reveal live codes. Every message is logged without its
body: who, why, whether it went.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage as Mime
from email.utils import formataddr, make_msgid
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.access import EmailChallenge, EmailMessage, User

CODE_MINUTES = 5          # sign-in and address codes
RESET_MINUTES = 30        # password reset links
MAX_TRIES = 5             # wrong codes before a challenge is spent
RESEND_SECONDS = 60       # between two codes for the same purpose
MAX_PER_15_MIN = 5        # codes per person per purpose in 15 minutes


def now() -> datetime:
    return datetime.now(timezone.utc)


def configured() -> bool:
    mode = settings.EMAIL_MODE.lower()
    if mode == "smtp":
        return bool(settings.SMTP_HOST and settings.SMTP_USER and settings.SMTP_PASSWORD and from_address())
    if mode == "file":
        return settings.ENVIRONMENT != "production" and bool(settings.EMAIL_FILE_DIR)
    return False


def from_address() -> str:
    return settings.EMAIL_FROM or settings.SMTP_USER


def status() -> dict:
    """For the IT workspace. Never includes the password."""
    mode = settings.EMAIL_MODE.lower()
    return {
        "configured": configured(), "mode": mode,
        "host": settings.SMTP_HOST if mode == "smtp" else "",
        "from": from_address() if mode == "smtp" else "",
    }


def mask(email: str) -> str:
    """j***@gmail.com: enough to recognise, not enough to harvest."""
    name, _, domain = email.partition("@")
    return (name[:1] + "***@" + domain) if domain else "***"


class EmailNotSent(Exception):
    pass


def send(db: Session, to: str, subject: str, text: str, purpose: str) -> None:
    """Sends one plain-text email and logs the attempt. Raises EmailNotSent."""
    started = time.perf_counter()
    mode = settings.EMAIL_MODE.lower()
    # Subjects of code emails carry the code, so the log keeps a description instead.
    logged = subject if purpose in ("alert", "test", "reset") else {
        "sign_in": "Sign-in code", "verify": "Address confirmation code", "change_old": "Email change code (old address)",
        "change_new": "Email change code (new address)"}.get(purpose, purpose)
    entry = EmailMessage(at=now(), to=to[:160], purpose=purpose[:20], subject=logged[:160], status="failed",
                         provider=mode)
    db.add(entry)
    if not configured():
        entry.status, entry.error = "skipped", "Email is not set up on this server"
        db.flush()
        raise EmailNotSent("Email is not set up yet, so the code cannot be sent. Ask IT.")
    message = Mime()
    message["From"] = formataddr((settings.EMAIL_FROM_NAME, from_address()))
    message["To"] = to
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=from_address().partition("@")[2] or "greenbuffet.local")
    message.set_content(text + "\n\n-- \nThe Green Buffet\nThis is an automatic message from the restaurant's system.\n")
    try:
        if mode == "file":
            folder = Path(settings.EMAIL_FILE_DIR)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{int(time.time() * 1000)}-{secrets.token_hex(3)}.eml").write_bytes(bytes(message))
        else:
            context = ssl.create_default_context()
            if settings.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20, context=context) as smtp:
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=20) as smtp:
                    smtp.starttls(context=context)
                    smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
                    smtp.send_message(message)
        entry.status = "sent"
    except Exception as exc:
        from app.services.ops import clean
        entry.error = clean(f"{type(exc).__name__}: {exc}", 300)
        db.flush()
        raise EmailNotSent("The email could not be sent just now. Try again in a minute, or ask IT.") from exc
    finally:
        entry.ms = int((time.perf_counter() - started) * 1000)
    db.flush()


# ---- codes and links ---------------------------------------------------------

def _hash(value: str) -> str:
    return hmac.new(settings.JWT_SECRET.encode(), value.encode(), hashlib.sha256).hexdigest()


def _open(db: Session, user: User, purpose: str) -> list[EmailChallenge]:
    return list(db.scalars(select(EmailChallenge).where(
        EmailChallenge.user_id == user.id, EmailChallenge.purpose == purpose,
        EmailChallenge.used_at.is_(None), EmailChallenge.cancelled_at.is_(None))).all())


def issue(db: Session, user: User, purpose: str, email: str, group_id: str = "",
          link: bool = False) -> tuple[EmailChallenge, str]:
    """A new code (or link token) for one purpose. Cancels earlier ones and
    refuses if asked for too often. Returns the challenge and the secret,
    which goes into the email and nowhere else."""
    moment = now()
    recent = db.scalars(select(EmailChallenge).where(
        EmailChallenge.user_id == user.id, EmailChallenge.purpose == purpose,
        EmailChallenge.created_at >= moment - timedelta(minutes=15))).all()
    if len(recent) >= MAX_PER_15_MIN:
        raise TooSoon("Too many codes asked for. Wait 15 minutes and try again.")
    if recent and (moment - max(r.created_at for r in recent)).total_seconds() < RESEND_SECONDS and not group_id:
        wait = RESEND_SECONDS - int((moment - max(r.created_at for r in recent)).total_seconds())
        raise TooSoon(f"A code was sent a moment ago. You can ask for another in {wait} seconds.")
    for old in _open(db, user, purpose):
        old.cancelled_at = moment
    secret = secrets.token_urlsafe(32) if link else f"{secrets.randbelow(1_000_000):06d}"
    challenge = EmailChallenge(
        user_id=user.id, purpose=purpose, email=email, code_hash=_hash(secret), created_at=moment,
        expires_at=moment + timedelta(minutes=RESET_MINUTES if link else CODE_MINUTES), group_id=group_id)
    db.add(challenge)
    db.flush()
    return challenge, secret


class TooSoon(Exception):
    pass


class CodeProblem(Exception):
    pass


def check(db: Session, challenge: EmailChallenge | None, code: str) -> None:
    """Uses up the challenge if the code is right; otherwise counts the try.
    Raises CodeProblem with a message the person can act on."""
    code = (code or "").strip().replace(" ", "")
    if challenge is None or challenge.cancelled_at is not None:
        raise CodeProblem("That code has been replaced by a newer one. Use the latest email.")
    if challenge.used_at is not None:
        raise CodeProblem("That code has already been used.")
    if challenge.expires_at <= now():
        raise CodeProblem("That code has expired. Ask for a new one.")
    if challenge.attempts >= MAX_TRIES:
        raise CodeProblem("Too many wrong codes. Ask for a new one.")
    if not hmac.compare_digest(challenge.code_hash, _hash(code)):
        challenge.attempts += 1
        db.flush()
        left = MAX_TRIES - challenge.attempts
        raise CodeProblem("That code is not right." + (f" {left} tries left." if left else " Ask for a new one."))
    challenge.used_at = now()
    db.flush()


def find_link(db: Session, token: str, purpose: str = "reset") -> EmailChallenge | None:
    return db.scalar(select(EmailChallenge).where(
        EmailChallenge.code_hash == _hash(token or ""), EmailChallenge.purpose == purpose))


def cancel_all(db: Session, user: User) -> None:
    db.execute(update(EmailChallenge).where(
        EmailChallenge.user_id == user.id, EmailChallenge.used_at.is_(None),
        EmailChallenge.cancelled_at.is_(None)).values(cancelled_at=now()))


# ---- the messages ----------------------------------------------------------------

def send_code(db: Session, user: User, purpose: str, email: str, code: str) -> None:
    what = {
        "sign_in": ("Your sign-in code", "Someone (we hope you) is signing in to The Green Buffet with your password."),
        "verify": ("Confirm your email address", "This confirms that this address belongs to you."),
        "change_old": ("Confirm changing your email address",
                       "Someone asked to move your Green Buffet account to a different email address."),
        "change_new": ("Confirm your new email address", "This confirms the new address for your Green Buffet account."),
    }[purpose]
    send(db, email, f"{code} is your Green Buffet code", (
        f"Hello {user.name.split()[0]},\n\n{what[1]}\n\nYour code is: {code}\n\n"
        f"It works once, for {CODE_MINUTES} minutes. Never tell this code to anyone, "
        "including staff or IT: nobody at the restaurant will ever ask for it.\n\n"
        "If you did not ask for this, change your password and tell an owner."), purpose)


def send_reset(db: Session, user: User, token: str) -> None:
    link = f"{settings.APP_URL.rstrip('/')}/reset-password?token={token}"
    send(db, user.email, "Reset your Green Buffet password", (
        f"Hello {user.name.split()[0]},\n\nSomeone asked to reset the password for this account.\n\n"
        f"Choose a new password here (the link works once, for {RESET_MINUTES} minutes):\n{link}\n\n"
        "If you did not ask for this, ignore this email; your password has not changed."), "reset")


def send_alert(db: Session, user: User, title: str, body: str) -> None:
    """A security notice by email, if the person has a confirmed address. Never fails the caller."""
    if not user.email_verified_at or not configured():
        return
    try:
        send(db, user.email, f"Security notice: {title}",
             f"Hello {user.name.split()[0]},\n\n{title}.\n{body}\n\n"
             "If this was not you, change your password and tell an owner straight away.", "alert")
    except EmailNotSent:
        pass
