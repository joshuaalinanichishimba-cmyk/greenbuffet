"""Helpers for the technical side: emergency controls, the error log,
security events and a small rate limiter.

The rate limiter keeps its counts in memory. That is right for one server
process, which is how the restaurant runs. If the system is ever run on
several servers at once, each counts on its own, so the limits loosen; move
the counts to the database or Redis before doing that.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time
import traceback
from collections import defaultdict, deque
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import ErrorRecord, FeatureControl, SecurityEvent

APP_VERSION = "1.27.0"

# key: (default, label, what it means for the restaurant)
CONTROLS = {
    "electronic_payments": (True, "Mobile money and card at the till",
                            "Off: the till takes cash only. Payments already taken can still be matched."),
    "take_orders": (True, "Taking new orders",
                    "Off: no new orders anywhere. The kitchen finishes what it has."),
    "read_only": (False, "Read-only mode",
                  "On: nobody but owners and IT can change anything. Use while a problem is fixed."),
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def control(db: Session, key: str) -> bool:
    row = db.get(FeatureControl, key)
    return CONTROLS[key][0] if row is None else row.enabled


def all_controls(db: Session) -> list[dict]:
    out = []
    for key, (default, label, meaning) in CONTROLS.items():
        row = db.get(FeatureControl, key)
        out.append({
            "key": key, "label": label, "meaning": meaning, "default": default,
            "enabled": default if row is None else row.enabled,
            "changed_by": row.changed_by if row else "", "reason": row.reason if row else "",
            "changed_at": row.changed_at.isoformat() if row and row.changed_at else None,
        })
    return out


# ---- the error log ----------------------------------------------------------

SECRETISH = re.compile(r"(password|passwd|secret|token|authorization|api[_-]?key|pin)\S*\s*[=:]\s*\S+", re.I)
URL_CREDENTIALS = re.compile(r"://[^/\s:@]+:[^/\s@]+@")


def clean(text: str, limit: int = 400) -> str:
    """Takes anything that looks like a credential out of a message."""
    text = URL_CREDENTIALS.sub("://***:***@", text or "")
    text = SECRETISH.sub(lambda m: m.group(1) + "=***", text)
    return text[:limit]


def record_error(db: Session, exc: BaseException, path: str, method: str, reference: str) -> None:
    """Adds an error to the log, or counts a repeat of one already there."""
    frames = traceback.extract_tb(exc.__traceback__)
    ours = [f for f in frames if "/app/" in f.filename.replace("\\", "/")]
    last = (ours or frames or [None])[-1]
    where = f"{last.filename.replace(chr(92), '/').split('/app/')[-1]}:{last.lineno} in {last.name}" if last else ""
    kind = type(exc).__name__
    # The same fault on any order id is one fault.
    shape = re.sub(r"/[0-9a-f]{16,}", "/:id", path)
    fingerprint = hashlib.sha256(f"{kind}|{shape}|{where}".encode()).hexdigest()[:64]
    moment = now()
    row = db.scalar(select(ErrorRecord).where(ErrorRecord.fingerprint == fingerprint))
    if row:
        row.count += 1
        row.last_seen = moment
        row.reference = reference
        if row.status == "resolved":
            row.status = "new"   # it came back
    else:
        parts = shape.strip("/").split("/")
        module = parts[2] if len(parts) > 2 and parts[0] == "api" else (parts[0] if parts else "")
        db.add(ErrorRecord(
            fingerprint=fingerprint, reference=reference, kind=kind[:80], module=module[:40], path=shape[:160],
            method=method[:8], message=clean(str(exc)), where=where[:200], first_seen=moment, last_seen=moment,
            version=APP_VERSION,
        ))


# ---- security events --------------------------------------------------------

_event_gate: dict[tuple, float] = {}


def security_event(db: Session, kind: str, severity: str, detail: str, account: str = "", ip: str = "",
                   path: str = "", every_seconds: int = 300) -> None:
    """Records a security event. The same kind for the same account and
    address is recorded once per five minutes, so a burst is one line."""
    key = (kind, account, ip)
    moment = time.monotonic()
    if moment - _event_gate.get(key, 0) < every_seconds:
        return
    _event_gate[key] = moment
    db.add(SecurityEvent(at=now(), kind=kind, severity=severity, detail=clean(detail, 300),
                         account=account[:120], ip=ip[:60], path=path[:160]))


# ---- rate limiting ----------------------------------------------------------

class RateLimiter:
    """Counts requests per key in a sliding window."""

    def __init__(self) -> None:
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int, window: float) -> bool:
        moment = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and moment - hits[0] > window:
                hits.popleft()
            if len(hits) >= limit:
                return False
            hits.append(moment)
            if len(self._hits) > 20_000:   # keep memory bounded
                for k in [k for k, v in self._hits.items() if not v][:5000]:
                    self._hits.pop(k, None)
            return True


limiter = RateLimiter()

# (path prefix, method or None for any, requests, seconds). First match wins.
# Generous enough for a busy counter on one shared internet address, tight
# enough to stop guessing passwords or hammering the server.
# LOGIN_RATE_PER_MINUTE exists for the automated tests, which sign in
# dozens of test accounts a minute; leave it unset in real use.
import os as _os

SIGN_IN_PER_MINUTE = int(_os.environ.get("LOGIN_RATE_PER_MINUTE", "30"))

LIMITS = [
    ("/api/v1/auth/login", "POST", SIGN_IN_PER_MINUTE, 60),
    ("/api/v1/auth/unlock", "POST", 20, 60),
    ("/api/v1/auth/two-step", "POST", 20, 60),
    ("/api/v1/auth/password", "POST", 10, 60),
    ("/api/v1/auth/email", "POST", 20, 60),
    ("/api/v1/auth/login/", "POST", 20, 60),
    ("/api/v1/presence/heartbeat", "POST", 240, 60),
    ("/api/v1/", None, 1200, 60),
]
