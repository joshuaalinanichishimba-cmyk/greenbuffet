"""Sign-in sessions, who is online, and account notices.

Presence is worked out from each open session's heartbeat, never assumed from
a session simply existing:

    Online           a screen answered in the last 90 seconds and someone used
                     it within the away time (5 minutes to start, in Settings)
    Away             a screen is answering, but nobody has touched it for the
                     away time, or it is locked
    Connection lost  signed in and not signed out, but the screen stopped
                     answering 90 seconds to 30 minutes ago: a dropped network,
                     load shedding, a closed laptop
    Offline          signed out, or nothing has answered for 30 minutes
    Unknown          signed in, but the screen has never sent a heartbeat (a
                     sign-in from before this was added, or a script)

Being offline says nothing about attendance: that comes from clocking only.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.access import Notification, Setting, User, UserSession

SEEN_SECONDS = 90
LOST_MINUTES = 30

STATUS_LABELS = {
    "online": "Online", "away": "Away", "lost": "Connection lost",
    "offline": "Offline", "unknown": "Unknown",
}


def now() -> datetime:
    return datetime.now(timezone.utc)


def setting_int(db: Session, key: str, fallback: int) -> int:
    row = db.get(Setting, key)
    try:
        return int(row.value) if row and str(row.value).strip() else fallback
    except ValueError:
        return fallback


# ---- devices -----------------------------------------------------------------

def describe_device(user_agent: str) -> tuple[str, str]:
    """('Phone', 'Chrome on Android') from a browser's user agent. Nothing else is kept."""
    ua = user_agent or ""
    low = ua.lower()
    if "ipad" in low or ("tablet" in low and "android" in low):
        device = "Tablet"
    elif "mobi" in low or "iphone" in low or "android" in low:
        device = "Phone"
    elif not ua:
        device = "Unknown"
    else:
        device = "Computer"
    if "edg/" in low:
        browser = "Edge"
    elif "opr/" in low or "opera" in low:
        browser = "Opera"
    elif "firefox/" in low:
        browser = "Firefox"
    elif "chrome/" in low or "crios/" in low:
        browser = "Chrome"
    elif "safari/" in low:
        browser = "Safari"
    elif "python" in low or "curl" in low or "requests" in low:
        browser = "Script"
    else:
        browser = "Browser"
    system = ""
    for pattern, name in (("windows", "Windows"), ("android", "Android"), ("iphone|ipad|ios", "iOS"),
                          ("mac os", "Mac"), ("linux", "Linux")):
        if re.search(pattern, low):
            system = name
            break
    return device, f"{browser} on {system}" if system else browser


def client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


# ---- sessions ----------------------------------------------------------------

def start_session(db: Session, user: User, request: Request) -> tuple[str, datetime, UserSession]:
    """Opens a session for a successful sign-in and returns its token."""
    from app.core.config import settings

    moment = now()
    device, browser = describe_device(request.headers.get("user-agent", ""))
    expires = moment + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)
    seen_before = db.scalar(select(UserSession.id).where(
        UserSession.user_id == user.id, UserSession.device == device, UserSession.browser == browser).limit(1))
    had_any = db.scalar(select(UserSession.id).where(UserSession.user_id == user.id).limit(1))
    session = UserSession(
        user_id=user.id, started_at=moment, expires_at=expires, last_seen_at=moment,
        last_active_at=moment, device=device, browser=browser, ip=client_ip(request),
    )
    db.add(session)
    db.flush()
    if had_any and not seen_before:
        notify(db, [user], "new_device", "Signed in on a new device",
               f"{device}, {browser}, at {local_time(moment)}. If this was not you, change your password "
               "and sign out the other devices.", "/profile/security", level="warn",
               optional=False)
        if user.role_id == "owner":
            notify_owners(db, "new_device", f"{user.name} signed in on a new device",
                          f"{device}, {browser}.", f"/team/{user.id}", level="warn", exclude=user.id)
    token, expires = create_access_token(user.id, user.role_id, user.token_version or 0, session.id, expires)
    return token, expires, session


def end_sessions(db: Session, user: User, reason: str, by: str, keep: str | None = None) -> int:
    """Ends every open session of an account (but `keep`). Returns how many."""
    moment = now()
    rows = db.scalars(select(UserSession).where(
        UserSession.user_id == user.id, UserSession.ended_at.is_(None))).all()
    count = 0
    for s in rows:
        if s.id == keep:
            continue
        s.ended_at, s.end_reason, s.ended_by = moment, reason, by
        count += 1
    return count


def open_sessions(db: Session, user_ids: list[str] | None = None) -> list[UserSession]:
    stmt = select(UserSession).where(UserSession.ended_at.is_(None), UserSession.expires_at > now())
    if user_ids is not None:
        stmt = stmt.where(UserSession.user_id.in_(user_ids))
    return list(db.scalars(stmt).all())


def session_state(s: UserSession, moment: datetime, away_minutes: int) -> str:
    """The state of one session on its own."""
    if s.ended_at or s.expires_at <= moment:
        return "offline"
    if s.closed_at and (not s.last_seen_at or s.closed_at >= s.last_seen_at - timedelta(seconds=5)):
        return "offline"
    if not s.last_seen_at:
        return "unknown"
    gap = moment - s.last_seen_at
    if gap <= timedelta(seconds=SEEN_SECONDS):
        if s.locked_at:
            return "away"
        active = s.last_active_at or s.last_seen_at
        return "online" if moment - active <= timedelta(minutes=away_minutes) else "away"
    if gap <= timedelta(minutes=LOST_MINUTES):
        return "lost"
    return "offline"


RANK = {"online": 0, "away": 1, "lost": 2, "unknown": 3, "offline": 4}


def presence(db: Session, users: list[User]) -> dict[str, dict]:
    """Each user's presence: status, label, last active time, and devices open."""
    moment = now()
    away = setting_int(db, "presence.away_minutes", 5)
    by_user: dict[str, list[UserSession]] = {}
    for s in open_sessions(db, [u.id for u in users]):
        by_user.setdefault(s.user_id, []).append(s)
    # The latest activity, including sessions that have ended.
    last_rows = db.execute(
        select(UserSession.user_id, UserSession.last_active_at)
        .where(UserSession.user_id.in_([u.id for u in users]), UserSession.last_active_at.is_not(None))
    ).all()
    last_active: dict[str, datetime] = {}
    for uid, at in last_rows:
        if uid not in last_active or at > last_active[uid]:
            last_active[uid] = at
    out: dict[str, dict] = {}
    for u in users:
        sessions = by_user.get(u.id, [])
        states = [session_state(s, moment, away) for s in sessions]
        status = min(states, key=lambda st: RANK[st]) if states else "offline"
        # A sign-in from before sessions were tracked, still within its eight hours.
        if not sessions and u.last_login_at and moment - u.last_login_at < timedelta(hours=8) \
                and u.id not in last_active:
            status = "unknown"
        if not u.is_active:
            status = "offline"
        locked = any(s.locked_at for s in sessions if session_state(s, moment, away) == "away")
        seen = last_active.get(u.id) or u.last_login_at
        out[u.id] = {
            "status": status,
            "label": "Away · screen locked" if status == "away" and locked else STATUS_LABELS[status],
            "last_active": seen.isoformat() if seen else None,
            "devices": sum(1 for st in states if st in ("online", "away", "lost")),
        }
    return out


def session_out(s: UserSession, current: str | None, away_minutes: int) -> dict:
    state = session_state(s, now(), away_minutes)
    return {
        "id": s.id, "device": s.device, "browser": s.browser, "ip": s.ip,
        "started_at": s.started_at.isoformat(),
        "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
        "last_active_at": s.last_active_at.isoformat() if s.last_active_at else None,
        "expires_at": s.expires_at.isoformat(),
        "state": state, "state_label": STATUS_LABELS[state] + (" · locked" if s.locked_at and state == "away" else ""),
        "this_device": s.id == current,
    }


# ---- notices -----------------------------------------------------------------

LUSAKA = timezone(timedelta(hours=2))


def local_time(at: datetime) -> str:
    return at.astimezone(LUSAKA).strftime("%d %b %H:%M")


# Owner notices people may switch off on their Notifications tab. Security
# notices about a person's own account cannot be switched off.
OPTIONAL_KINDS = {
    "account_created": "A new staff account is made",
    "account_suspended": "An account is suspended, restored or archived",
    "access_changed": "Someone's role or permissions change",
    "failed_logins": "Repeated wrong passwords on an account",
    "security_changed": "Someone's security settings change",
    "new_device": "An owner signs in on a new device",
    "offline_sales": "An offline sale arrives at a different price, or after its till closed",
}


def wants(user: User, kind: str) -> bool:
    try:
        prefs = json.loads(user.preferences or "{}")
    except ValueError:
        prefs = {}
    return prefs.get("notify", {}).get(kind, True) is not False


def notify(db: Session, users: list[User], kind: str, title: str, body: str = "",
           link: str = "", level: str = "info", optional: bool = True) -> None:
    moment = now()
    for u in users:
        if optional and not wants(u, kind):
            continue
        db.add(Notification(user_id=u.id, at=moment, kind=kind, level=level,
                            title=title[:120], body=body[:300], link=link[:120]))
        if not optional:
            # Security notices about a person's own account also go by email,
            # to a confirmed address, so a stolen session is noticed off-site.
            from app.services.email import send_alert
            send_alert(db, u, title, body)


def owners(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.role_id == "owner", User.is_active.is_(True))).all())


def notify_owners(db: Session, kind: str, title: str, body: str = "", link: str = "",
                  level: str = "info", exclude: str | None = None) -> None:
    notify(db, [o for o in owners(db) if o.id != exclude], kind, title, body, link, level)


def has_two_step(user: User) -> bool:
    """An authenticator app, or email codes to a confirmed address."""
    return bool(user.totp_enabled or (user.two_step_method == "email" and user.email_verified_at))


def two_step_required(db: Session, user: User) -> bool:
    """Owners and the IT administrator must use two-step sign-in. The one
    exception is test sign-in mode on a development machine, which already
    shares one password."""
    if user.role_id not in ("owner", "it"):
        return False
    from app.core.config import settings
    test_mode = db.get(Setting, "signin.fill_passwords")
    if test_mode and test_mode.value == "true" and settings.ENVIRONMENT != "production":
        return False
    return True
