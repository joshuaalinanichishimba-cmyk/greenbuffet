"""Two-step sign-in: six-digit codes from an authenticator app (RFC 6238).

Written out here rather than taken from a package: it is thirty lines of
standard HMAC, and one dependency fewer to install on the restaurant PC.
Works with Google Authenticator, Microsoft Authenticator, Authy and others.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

from app.core.security import hash_password, verify_password

STEP = 30      # seconds per code
DIGITS = 6
DRIFT = 1      # accept the code before and after, for a phone clock a little out


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(number % (10 ** DIGITS)).zfill(DIGITS)


def code_now(secret: str, at: float | None = None) -> str:
    return _code(secret, int((at or time.time()) // STEP))


def check_code(secret: str, code: str, at: float | None = None) -> bool:
    code = "".join(ch for ch in (code or "") if ch.isdigit())
    if not secret or len(code) != DIGITS:
        return False
    counter = int((at or time.time()) // STEP)
    return any(hmac.compare_digest(_code(secret, counter + d), code) for d in range(-DRIFT, DRIFT + 1))


def setup_uri(secret: str, email: str) -> str:
    """What the QR code holds: the authenticator app reads it to add the account."""
    issuer = "The Green Buffet"
    return (f"otpauth://totp/{quote(issuer)}:{quote(email)}"
            f"?secret={secret}&issuer={quote(issuer)}&digits={DIGITS}&period={STEP}")


def new_recovery_codes(count: int = 8) -> tuple[list[str], str]:
    """Codes to write down for a lost phone. Returns the codes and what is stored (hashed)."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    codes = ["".join(secrets.choice(alphabet) for _ in range(4)) + "-" +
             "".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(count)]
    return codes, json.dumps([hash_password(c) for c in codes])


def use_recovery_code(stored: str, code: str) -> str | None:
    """If the code is one of the stored ones, returns the store without it. Each works once."""
    code = (code or "").strip().lower()
    if len(code) != 9:
        return None
    hashes = json.loads(stored or "[]")
    for h in hashes:
        if verify_password(code, h):
            hashes.remove(h)
            return json.dumps(hashes)
    return None
