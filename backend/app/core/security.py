"""Password hashing and JSON web tokens.

Passwords use argon2, the current recommendation for new systems. Plain
passwords are never stored or logged.
"""
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError
from jose import JWTError, jwt

from app.core.config import settings

_hasher = PasswordHasher()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, plain)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def create_access_token(
    user_id: str, role_id: str, version: int = 0, session_id: str | None = None,
    expires: datetime | None = None,
) -> tuple[str, datetime]:
    expires = expires or datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "role": role_id, "exp": expires, "v": version}
    if session_id:
        # The device this token belongs to, so it can be signed out on its own.
        payload["sid"] = session_id
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, expires


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# Deliberately no 0/O, 1/l/I: these are read off a screen and typed by hand,
# and a misread character looks exactly like a wrong password.
_SAFE_ALPHABET = "abcdefghijkmnpqrstuvwxyzACDEFGHJKLMNPQRTUVWXY23456789"


def generate_temp_password(length: int = 10) -> str:
    """A temporary password that is easy to read aloud and type."""
    return "".join(secrets.choice(_SAFE_ALPHABET) for _ in range(length))


def create_ticket(user_id: str, version: int, minutes: int = 5, challenge: str = "") -> str:
    """A short-lived pass between the password and the two-step code.

    It proves the password was right a moment ago and nothing else: the API
    refuses it everywhere except the code check.
    """
    expires = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": user_id, "purpose": "two_step", "exp": expires, "v": version}
    if challenge:
        # The emailed code this ticket waits for; a resend issues a new ticket.
        payload["cid"] = challenge
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


COMMON_PASSWORDS = {
    "password", "password1", "password123", "1234567890", "12345678910", "qwertyuiop", "iloveyou12",
    "greenbuffet", "greenbuffet1", "greenbuffet123", "zambia2026", "lusaka2026", "kitwe2026", "welcome123",
    "letmein123", "admin12345", "changeme123", "abc1234567", "0987654321", "1111111111", "qwerty1234",
}


def password_problem(password: str, email: str = "", name: str = "") -> str | None:
    """Why a new password is too weak, or None. Length matters most; the rest
    stops the guesses an attacker tries first."""
    if len(password) < 10:
        return "Use at least 10 characters. A short sentence you will remember works well."
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS or len(set(lowered)) < 4:
        return "That password is too easy to guess. Choose something less common."
    local = email.split("@")[0].lower()
    if len(local) >= 4 and local in lowered:
        return "Do not use your email address in your password."
    first = (name.split() or [""])[0].lower()
    if len(first) >= 3 and first in lowered:
        return "Do not use your name in your password."
    return None
