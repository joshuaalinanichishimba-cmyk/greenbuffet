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


def create_access_token(user_id: str, role_id: str, version: int = 0) -> tuple[str, datetime]:
    expires = datetime.now(timezone.utc) + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    payload = {"sub": user_id, "role": role_id, "exp": expires, "v": version}
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
