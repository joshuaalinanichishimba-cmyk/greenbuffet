"""The IT workspace: system health, diagnostics, integrity checks, controlled
repairs, emergency controls, incidents, support tickets, errors and
security events.

Rules this module keeps:

- Every status comes from a check that actually ran. Something that cannot
  be checked from here says "not configured" or "unknown", never "ok".
- Repairs are a fixed list. Each one says what it touches, how risky it is,
  what it needs, and is checked afterwards; the dashboard cannot send
  commands, SQL or code of its own.
- The IT role has no access to money, pay, prices or refunds. A repair that
  touches business records goes through the same code the till uses.
"""
from __future__ import annotations

import os
import platform
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, inspect as sa_inspect, select, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import engine, get_db
from app.core.permissions import current_user, requires
from app.core.security import verify_password
from app.models.access import AuditLog, User, UserSession
from app.models.base import Base
from app.models.books import JournalEntry, JournalLine
from app.models.kitchen import KitchenItem
from app.models.ops import (
    INCIDENT_STATES, PRIORITIES, SEVERITIES, TICKET_STATES, CaseNote, ErrorRecord, FeatureControl, Incident,
    RepairRun, SecurityEvent, Ticket,
)
from app.models.sales import Order, Payment, Shift
from app.services.accounts import describe_device, end_sessions, notify, notify_owners, owners
from app.services.audit import record
from app.services.numbering import numbered
from app.services.ops import APP_VERSION, CONTROLS, all_controls, clean

router = APIRouter(tags=["it"])
can_view = requires("it.view")
can_repair = requires("it.repair")
can_control = requires("it.control")
can_report = requires("tickets.report")

STARTED = time.time()
LUSAKA = timezone(timedelta(hours=2))


def now() -> datetime:
    return datetime.now(timezone.utc)


def _check(key: str, label: str, state: str, detail: str, **extra) -> dict:
    """state: operational, degraded, critical, offline, unknown, not_configured."""
    return {"key": key, "label": label, "status": state, "detail": detail,
            "measured_at": now().isoformat(), **extra}


# ---- health -------------------------------------------------------------------

def _database(db: Session) -> dict:
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        ms = round((time.perf_counter() - started) * 1000, 1)
        state = "operational" if ms < 300 else "degraded"
        return _check("database", "Database", state, f"Answered in {ms} ms", ms=ms)
    except Exception as exc:
        return _check("database", "Database", "offline", clean(str(exc).splitlines()[0]))


def _schema(db: Session) -> dict:
    """Every table and column the code expects is in the database."""
    try:
        inspector = sa_inspect(db.connection())
        missing = []
        tables = set(inspector.get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in tables:
                missing.append(table.name)
                continue
            have = {c["name"] for c in inspector.get_columns(table.name)}
            missing += [f"{table.name}.{c.name}" for c in table.columns if c.name not in have]
        if missing:
            return _check("schema", "Database structure", "critical",
                          f"Missing: {', '.join(missing[:6])}{'…' if len(missing) > 6 else ''}. "
                          "Restart the server; it adds missing columns on start.")
        return _check("schema", "Database structure", "operational",
                      f"All {len(Base.metadata.tables)} tables match the code")
    except Exception as exc:
        return _check("schema", "Database structure", "unknown", clean(str(exc)))


def _books(db: Session) -> dict:
    debit, credit = db.execute(select(func.coalesce(func.sum(JournalLine.debit_ngwee), 0),
                                      func.coalesce(func.sum(JournalLine.credit_ngwee), 0))).one()
    if debit == credit:
        return _check("books", "Books in balance", "operational", "Debits equal credits")
    return _check("books", "Books in balance", "critical",
                  f"Out by K{abs(debit - credit) / 100:,.2f}. See Integrity for the entries.")


def _kitchen_link() -> dict:
    from app.api.v1.kitchen import board
    watching = len(board._watchers)
    return _check("realtime", "Kitchen live link", "operational" if watching else "unknown",
                  f"{watching} screen(s) connected" if watching else
                  "No kitchen screen is connected right now, so the link cannot be checked",
                  connected=watching)


def _backups() -> dict:
    from app.api.v1.settings_api import BACKUPS
    files = sorted(BACKUPS.glob("*.dump"), key=lambda p: p.stat().st_mtime, reverse=True) if BACKUPS.exists() else []
    if not files:
        return _check("backups", "Backups", "critical",
                      "No backup file on this server. Run a backup, and keep a copy off this machine.")
    newest = files[0]
    age_h = (time.time() - newest.stat().st_mtime) / 3600
    state = "operational" if age_h < 26 else "degraded" if age_h < 72 else "critical"
    return _check("backups", "Backups", state,
                  f"Newest {newest.name}, {age_h:.0f} h old, {newest.stat().st_size / 1e6:.1f} MB. "
                  "Only a restore test proves a backup works (scripts\\restore.ps1).",
                  last=datetime.fromtimestamp(newest.stat().st_mtime, timezone.utc).isoformat())


def _frontend() -> dict:
    from app.main import BUILT
    if (BUILT / "index.html").exists():
        return _check("frontend", "Screens (front end)", "operational", "Built and served by this server")
    return _check("frontend", "Screens (front end)", "unknown",
                  "Not served by this server (development, or hosted separately)")


def _configuration() -> list[dict]:
    out = []
    weak = settings.JWT_SECRET in ("change-me-in-env", "") or len(settings.JWT_SECRET) < 32
    out.append(_check("secrets", "Sign-in signing secret", "critical" if weak else "operational",
                      "Too short or still the example value; set JWT_SECRET in .env" if weak
                      else "Set and long enough"))
    out.append(_check("environment", "Environment", "operational" if settings.ENVIRONMENT != "development"
                      else "degraded",
                      f"{settings.ENVIRONMENT}" + (" (test sign-in mode allowed)" if settings.ENVIRONMENT != "production"
                                                    else "")))
    # Integrations not built or not set up yet: said plainly, never "ok".
    from app.services import email as mail
    from app.models.access import EmailMessage
    info = mail.status()
    if not info["configured"]:
        out.append(_check("email", "Email delivery", "not_configured",
                          "No email provider is set up yet, so codes and alerts are in the system only"))
    else:
        with __import__("app.core.database", fromlist=["SessionLocal"]).SessionLocal() as db2:
            day = now() - timedelta(hours=24)
            sent = db2.scalar(select(func.count(EmailMessage.id)).where(EmailMessage.at >= day, EmailMessage.status == "sent")) or 0
            failed = db2.scalar(select(func.count(EmailMessage.id)).where(EmailMessage.at >= day, EmailMessage.status == "failed")) or 0
        state = "operational" if not failed else ("critical" if not sent else "degraded")
        if not sent and not failed:
            state = "unknown"
        out.append(_check("email", "Email delivery", state,
                          f"{info['mode']} via {info['host'] or 'files'} from {info['from']}. Last 24 h: {sent} sent, {failed} failed"
                          + ("" if sent or failed else " (nothing sent yet, so not proven; use Send a test email)")))
    out.append(_check("lenco", "Lenco payments", "not_configured",
                      "Not connected yet; mobile money and card are recorded by hand with their reference"))
    out.append(_check("storage", "File storage", "degraded" if os.environ.get("RENDER") else "operational",
                      "Photos and documents are on this server's disk"
                      + (", which a cloud host may wipe on restart" if os.environ.get("RENDER") else "")))
    return out


def _counts(db: Session) -> dict:
    day = now() - timedelta(hours=24)
    return {
        "errors_24h": db.scalar(select(func.coalesce(func.sum(ErrorRecord.count), 0)).where(ErrorRecord.last_seen >= day)) or 0,
        "error_groups_open": db.scalar(select(func.count(ErrorRecord.id)).where(ErrorRecord.status == "new")) or 0,
        "security_open": db.scalar(select(func.count(SecurityEvent.id)).where(SecurityEvent.status == "open")) or 0,
        "security_high": db.scalar(select(func.count(SecurityEvent.id)).where(
            SecurityEvent.status == "open", SecurityEvent.severity.in_(("high", "critical")))) or 0,
        "incidents_open": db.scalar(select(func.count(Incident.id)).where(
            Incident.status.notin_(("resolved", "closed")))) or 0,
        "tickets_open": db.scalar(select(func.count(Ticket.id)).where(Ticket.status.notin_(("resolved", "closed")))) or 0,
        "sessions_open": db.scalar(select(func.count(UserSession.id)).where(
            UserSession.ended_at.is_(None), UserSession.expires_at > now())) or 0,
    }


@router.get("/it/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(can_view)) -> dict:
    checks = [_database(db), _books(db), _kitchen_link(), _backups(), _frontend()] + _configuration()
    counts = _counts(db)
    worst = "operational"
    for c in checks:
        if c["status"] in ("critical", "offline"):
            worst = "critical"
        elif c["status"] == "degraded" and worst == "operational":
            worst = "degraded"
    return {
        "overall": worst, "checks": checks, "counts": counts, "controls": all_controls(db),
        "version": APP_VERSION, "environment": settings.ENVIRONMENT,
        "uptime_minutes": round((time.time() - STARTED) / 60), "server_time": now().isoformat(),
    }


# ---- integrity checks (read-only) ------------------------------------------------

def _paid_sums(db: Session):
    return (select(Payment.order_id, func.sum(Payment.amount_ngwee).label("paid"))
            .where(Payment.status != "failed").group_by(Payment.order_id).subquery())


CHECKS: dict[str, tuple[str, str, str | None]] = {
    # key: (label, what it means, repair that fixes it)
    "unbalanced_journals": ("Journal entries that do not balance",
                            "Each entry's debits must equal its credits. Needs the accountant: reverse and re-post.", None),
    "sales_without_journal": ("Paid orders missing from the books",
                              "The sale was paid but never posted. Safe to post now.", "post_missing_sale_journals"),
    "paid_but_short": ("Orders marked paid that are not fully paid",
                       "A mobile money payment later marked failed. The order owes money and should show at "
                       "the till as waiting for payment.", "reopen_orders_owing"),
    "fully_paid_still_open": ("Orders fully paid but still open",
                              "Payments cover the total but the order did not close.", None),
    "duplicate_references": ("Mobile money or card references used twice",
                             "The same transaction number on two payments. Check the statement.", None),
    "paid_without_kitchen": ("Paid orders in the last 3 hours with no kitchen ticket",
                             "The kitchen may not know about them.", "create_missing_kitchen_tickets"),
    "inactive_with_sessions": ("Switched-off accounts still signed in somewhere",
                               "Their token is already refused; this tidies the device list.", "end_sessions_of_inactive_accounts"),
    "expired_sessions_open": ("Expired sign-ins still listed as open",
                              "Housekeeping only.", "close_expired_sessions"),
    "old_open_tills": ("Tills open for more than 24 hours",
                       "Someone forgot to close. A manager should count and close it.", None),
}


def _integrity(db: Session, key: str, limit: int = 50) -> list[dict]:
    moment = now()
    if key == "unbalanced_journals":
        rows = db.execute(
            select(JournalEntry.number, JournalEntry.entry_date, func.sum(JournalLine.debit_ngwee),
                   func.sum(JournalLine.credit_ngwee))
            .join(JournalLine, JournalLine.entry_id == JournalEntry.id)
            .group_by(JournalEntry.id, JournalEntry.number, JournalEntry.entry_date)
            .having(func.sum(JournalLine.debit_ngwee) != func.sum(JournalLine.credit_ngwee)).limit(limit)).all()
        return [{"ref": n, "detail": f"{d}: debits K{dr / 100:,.2f}, credits K{cr / 100:,.2f}"} for n, d, dr, cr in rows]
    if key == "sales_without_journal":
        posted = select(JournalEntry.reference).where(JournalEntry.source == "sale")
        rows = db.execute(select(Order.id, Order.number, Order.total_ngwee).where(
            Order.status == "paid", Order.total_ngwee > 0, Order.created_at >= moment - timedelta(days=90),
            Order.number.notin_(posted)).limit(limit)).all()
        return [{"id": i, "ref": n, "detail": f"K{t / 100:,.2f}"} for i, n, t in rows]
    if key in ("paid_but_short", "fully_paid_still_open"):
        sums = _paid_sums(db)
        paid = func.coalesce(sums.c.paid, 0)
        cond = and_(Order.status == "paid", paid < Order.total_ngwee) if key == "paid_but_short" else \
            and_(Order.status == "open", paid >= Order.total_ngwee, Order.total_ngwee > 0)
        rows = db.execute(select(Order.number, Order.total_ngwee, paid).outerjoin(sums, sums.c.order_id == Order.id)
                          .where(cond).limit(limit)).all()
        return [{"ref": n, "detail": f"Total K{t / 100:,.2f}, paid K{p / 100:,.2f}"} for n, t, p in rows]
    if key == "duplicate_references":
        rows = db.execute(select(Payment.reference, func.count(Payment.id)).where(
            Payment.reference != "", Payment.status != "failed", Payment.is_refund.is_(False))
            .group_by(Payment.reference).having(func.count(Payment.id) > 1).limit(limit)).all()
        return [{"ref": r, "detail": f"Used {c} times"} for r, c in rows]
    if key == "paid_without_kitchen":
        has = select(KitchenItem.order_id)
        rows = db.execute(select(Order.id, Order.number).where(
            Order.status == "paid", Order.created_at >= moment - timedelta(hours=3), Order.id.notin_(has)).limit(limit)).all()
        return [{"id": i, "ref": n, "detail": "No kitchen ticket"} for i, n in rows]
    if key == "inactive_with_sessions":
        rows = db.execute(select(UserSession.id, User.name, UserSession.device, UserSession.browser)
                          .join(User, User.id == UserSession.user_id)
                          .where(User.is_active.is_(False), UserSession.ended_at.is_(None)).limit(limit)).all()
        return [{"id": i, "ref": n, "detail": f"{d}, {b}"} for i, n, d, b in rows]
    if key == "expired_sessions_open":
        rows = db.execute(select(UserSession.id, UserSession.expires_at).where(
            UserSession.ended_at.is_(None), UserSession.expires_at <= moment).limit(limit)).all()
        return [{"id": i, "ref": i[:8], "detail": f"Expired {e.astimezone(LUSAKA):%d %b %H:%M}"} for i, e in rows]
    if key == "old_open_tills":
        rows = db.execute(select(Shift.id, Shift.opened_by, Shift.opened_at).where(
            Shift.closed_at.is_(None), Shift.opened_at < moment - timedelta(hours=24)).limit(limit)).all()
        return [{"id": i, "ref": who, "detail": f"Open since {at.astimezone(LUSAKA):%d %b %H:%M}"} for i, who, at in rows]
    raise HTTPException(status.HTTP_404_NOT_FOUND, "No such check.")


@router.get("/it/integrity")
def integrity(db: Session = Depends(get_db), _: User = Depends(can_view)) -> list[dict]:
    out = []
    for key, (label, meaning, repair) in CHECKS.items():
        found = _integrity(db, key)
        out.append({"key": key, "label": label, "meaning": meaning, "repair": repair,
                    "count": len(found), "examples": found[:5], "more": len(found) >= 50,
                    "status": "operational" if not found else ("critical" if key in (
                        "unbalanced_journals", "paid_but_short") else "degraded")})
    return out


@router.post("/it/diagnostics")
def diagnostics(db: Session = Depends(get_db), user: User = Depends(can_view)) -> dict:
    """The full check: health, structure, configuration and every integrity check."""
    started = time.perf_counter()
    results = [_database(db), _schema(db), _books(db), _kitchen_link(), _backups(), _frontend()] + _configuration()
    for item in integrity(db, user):
        results.append(_check(f"integrity.{item['key']}", item["label"], item["status"],
                              f"{item['count']} found. {item['meaning']}" if item["count"] else "None found",
                              repair=item["repair"]))
    took = round(time.perf_counter() - started, 2)
    bad = [r for r in results if r["status"] in ("critical", "offline", "degraded")]
    record(db, user.name, "it", "Diagnostics run", f"{len(results)} checks, {len(bad)} need attention, {took}s")
    db.commit()
    return {"ran_at": now().isoformat(), "seconds": took, "results": results}


# ---- repairs ---------------------------------------------------------------------

class RepairIn(BaseModel):
    reason: str = Field(min_length=5, max_length=300)
    email: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, max_length=200)


REPAIRS = {
    "post_missing_sale_journals": {
        "label": "Post paid sales missing from the books", "risk": "moderate", "check": "sales_without_journal",
        "does": "Posts each paid order's sale and cost of ingredients, exactly as the till would have. "
                "An order already in the books is skipped, so running it twice changes nothing.",
        "touches": "Journal (books)",
    },
    "reopen_orders_owing": {
        "label": "Show owing orders at the till again", "risk": "low", "check": "paid_but_short",
        "does": "Orders whose mobile money failed after hand-over go back to Waiting for payment, so the "
                "money can be taken. The books already hold the debt; nothing else changes.",
        "touches": "Order status",
    },
    "create_missing_kitchen_tickets": {
        "label": "Send recent paid orders to the kitchen", "risk": "moderate", "check": "paid_without_kitchen",
        "does": "Puts orders paid in the last 3 hours that have no kitchen ticket onto the board.",
        "touches": "Kitchen board",
    },
    "end_sessions_of_inactive_accounts": {
        "label": "Sign out switched-off accounts", "risk": "low", "check": "inactive_with_sessions",
        "does": "Marks the sign-ins of suspended or archived accounts as ended.", "touches": "Devices list",
    },
    "close_expired_sessions": {
        "label": "Tidy expired sign-ins", "risk": "low", "check": "expired_sessions_open",
        "does": "Marks sign-ins past their expiry as ended.", "touches": "Devices list",
    },
    "revoke_account_sessions": {
        "label": "Sign one account out everywhere", "risk": "moderate", "check": None, "needs_email": True,
        "does": "Ends every sign-in of one staff account, for a lost phone or a suspected break-in. "
                "Owner accounts are excluded: owners do this for each other from the Team page.",
        "touches": "That account's devices",
    },
    "run_backup": {
        "label": "Take a database backup now", "risk": "moderate", "check": None,
        "does": "Runs pg_dump into the backups folder, like scripts\\backup.ps1.", "touches": "Backups folder",
    },
}

# Things the brief asks for that this server cannot do by itself. Listed so
# the screen says so, instead of showing a button that does nothing.
NOT_AVAILABLE = [
    ("Restart the server", "Needs the hosting provider's API key (Render). On the restaurant PC: scripts\\update.ps1."),
    ("Roll back a deployment", "Needs the hosting provider's API and a deployed copy; not set up yet."),
    ("Re-check pending Lenco payments", "Lenco is not connected yet."),
    ("Retry failed emails", "Not offered on purpose: codes expire in minutes, so a person asks for a new one instead. Use Email, Send a test to check the settings."),
    ("Restore a backup", "Critical: only on the server computer with scripts\\restore.ps1, which tests it in a separate database first."),
]


@router.get("/it/repairs")
def repairs(db: Session = Depends(get_db), _: User = Depends(can_view)) -> dict:
    out = []
    for key, r in REPAIRS.items():
        pending = len(_integrity(db, r["check"])) if r["check"] else None
        out.append({"key": key, **{k: v for k, v in r.items() if k != "check"}, "check": r["check"],
                    "pending": pending, "needs_password": r["risk"] in ("high", "critical")})
    history = db.scalars(select(RepairRun).order_by(RepairRun.started_at.desc()).limit(30)).all()
    return {
        "repairs": out,
        "not_available": [{"label": a, "why": b} for a, b in NOT_AVAILABLE],
        "history": [{"id": h.id, "operation": h.operation, "label": REPAIRS.get(h.operation, {}).get("label", h.operation),
                     "risk": h.risk, "status": h.status, "affected": h.affected, "reason": h.reason,
                     "result": h.result, "verification": h.verification, "by": h.started_by,
                     "at": h.started_at.isoformat(),
                     "finished_at": h.finished_at.isoformat() if h.finished_at else None} for h in history],
    }


@router.post("/it/repairs/{key}/preview")
def preview(key: str, body: RepairIn | None = None, db: Session = Depends(get_db), _: User = Depends(can_repair)) -> dict:
    """A dry run: what the repair would touch, without touching it."""
    r = REPAIRS.get(key)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such repair.")
    if key == "revoke_account_sessions":
        target = _account_for_revoke(db, (body.email if body else "") or "")
        rows = db.scalars(select(UserSession).where(UserSession.user_id == target.id, UserSession.ended_at.is_(None))).all()
        return {"affected": len(rows), "items": [{"ref": f"{s.device}, {s.browser}", "detail": f"since {s.started_at.astimezone(LUSAKA):%d %b %H:%M}"} for s in rows]}
    if key == "run_backup":
        return {"affected": 1, "items": [{"ref": "Whole database", "detail": "Read only; nothing changes"}]}
    items = _integrity(db, r["check"], limit=500)
    return {"affected": len(items), "items": items[:50]}


def _account_for_revoke(db: Session, email: str) -> User:
    target = db.scalar(select(User).where(User.email == email.strip().lower()))
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No account with that email.")
    if target.role_id == "owner":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner accounts are signed out by the other owner, not from IT.")
    return target


@router.post("/it/repairs/{key}/run")
def run_repair(key: str, body: RepairIn, db: Session = Depends(get_db), user: User = Depends(can_repair)) -> dict:
    r = REPAIRS.get(key)
    if not r:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such repair.")
    if r["risk"] in ("high", "critical") and not (body.password and verify_password(body.password, user.password_hash)):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Type your password to confirm a high-risk repair.")
    # Preconditions are checked before anything is recorded as started.
    if key == "revoke_account_sessions":
        _account_for_revoke(db, body.email or "")
    # One at a time: a second press while the first is running does nothing.
    running = db.scalar(select(RepairRun).where(RepairRun.operation == key, RepairRun.status == "running",
                                                RepairRun.started_at > now() - timedelta(minutes=10)))
    if running:
        raise HTTPException(status.HTTP_409_CONFLICT, "This repair is already running. Wait for it to finish.")
    run = RepairRun(operation=key, risk=r["risk"], reason=body.reason.strip(), status="running",
                    started_by=user.name, started_at=now())
    db.add(run)
    db.commit()

    done, notes = 0, []
    try:
        if key == "post_missing_sale_journals":
            from app.services.posting import post_sale
            for item in _integrity(db, "sales_without_journal", limit=500):
                order = db.get(Order, item["id"])
                # Dated on the day of the sale, so each month's books stay right.
                day = (order.paid_at or order.created_at).astimezone(LUSAKA).date() if order else None
                if order and post_sale(db, order, when=day) is not None:
                    done += 1
            db.flush()
        elif key == "reopen_orders_owing":
            for item in _integrity(db, "paid_but_short", limit=500):
                order = db.scalar(select(Order).where(Order.number == item["ref"]))
                if order and order.outstanding_ngwee > 0:
                    order.status = "open"
                    done += 1
        elif key == "create_missing_kitchen_tickets":
            from app.api.v1.kitchen import send_to_kitchen
            for item in _integrity(db, "paid_without_kitchen", limit=500):
                order = db.get(Order, item["id"])
                if order and send_to_kitchen(db, order) > 0:
                    done += 1
        elif key == "end_sessions_of_inactive_accounts":
            for item in _integrity(db, "inactive_with_sessions", limit=500):
                s = db.get(UserSession, item["id"])
                s.ended_at, s.end_reason, s.ended_by = now(), "suspended", user.name
                done += 1
        elif key == "close_expired_sessions":
            for item in _integrity(db, "expired_sessions_open", limit=5000):
                s = db.get(UserSession, item["id"])
                s.ended_at, s.end_reason, s.ended_by = s.expires_at, "", "expiry"
                done += 1
        elif key == "revoke_account_sessions":
            target = _account_for_revoke(db, body.email or "")
            done = end_sessions(db, target, "revoked", user.name)
            notes.append(f"{target.name}: {done} device(s)")
            notify(db, [target], "security", "You were signed out of all devices",
                   f"By IT ({user.name}): {body.reason.strip()}", "/profile/security", "warn", optional=False)
            notify_owners(db, "access_changed", f"IT signed {target.name} out everywhere",
                          f"{user.name}: {body.reason.strip()}", f"/team/{target.id}")
        elif key == "run_backup":
            from app.api.v1.settings_api import make_backup
            made = make_backup(db, user)
            done = 1
            notes.append(getattr(made, "name", "") or str(made)[:120])
        db.commit()
        run.status = "succeeded"
        run.result = f"{done} record(s) handled." + (" " + "; ".join(notes) if notes else "")
    except HTTPException as exc:
        db.rollback()
        run = db.get(RepairRun, run.id)
        run.status, run.result = "failed", str(exc.detail)
    except Exception as exc:
        db.rollback()
        run = db.get(RepairRun, run.id)
        run.status, run.result = "failed", clean(f"{type(exc).__name__}: {exc}")

    # Checked afterwards, by running the same check again, not assumed.
    if r["check"] and run.status == "succeeded":
        left = len(_integrity(db, r["check"], limit=500))
        run.verification = "Checked again: none left." if not left else f"Checked again: {left} still found."
        if left:
            run.status = "partial"
    elif run.status == "succeeded":
        run.verification = "Nothing further to check." if key != "run_backup" else "Backup file written; test it with restore.ps1."
    run.affected, run.finished_at = done, now()
    record(db, user.name, "it", "Repair run", f"{r['label']}: {run.status}. {run.result} {run.verification}".strip(),
           run.id)
    db.commit()
    return {"id": run.id, "status": run.status, "result": run.result, "verification": run.verification,
            "affected": run.affected}


# ---- emergency controls --------------------------------------------------------------

class ControlIn(BaseModel):
    enabled: bool
    reason: str = Field(min_length=5, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@router.get("/it/controls")
def controls(db: Session = Depends(get_db), _: User = Depends(can_view)) -> list[dict]:
    return all_controls(db)


@router.post("/it/controls/{key}")
def set_control(key: str, body: ControlIn, db: Session = Depends(get_db), user: User = Depends(can_control)) -> list[dict]:
    """High risk: changes what everyone at the restaurant can do. Needs the password again."""
    if key not in CONTROLS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such control.")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "That password is not right.")
    row = db.get(FeatureControl, key)
    before = CONTROLS[key][0] if row is None else row.enabled
    if row is None:
        row = FeatureControl(key=key, enabled=body.enabled)
        db.add(row)
    row.enabled, row.reason, row.changed_by, row.changed_at = body.enabled, body.reason.strip(), user.name, now()
    label = CONTROLS[key][1]
    state = "on" if body.enabled else "off"
    record(db, user.name, "it", "Emergency control changed", f"{label}: {state}. {body.reason.strip()}", key,
           before={"enabled": before}, after={"enabled": body.enabled})
    if before != body.enabled:
        notify_owners(db, "security_changed", f"{label} switched {state}", f"By {user.name}: {body.reason.strip()}",
                      "/it/controls", level="warn", exclude=user.id)
    db.commit()
    return all_controls(db)


# ---- incidents ------------------------------------------------------------------------

class IncidentIn(BaseModel):
    title: str = Field(min_length=4, max_length=140)
    service: str = Field(default="", max_length=40)
    severity: str = Field(default="medium")
    impact: str = Field(default="", max_length=300)


class IncidentPatch(BaseModel):
    status: str | None = None
    severity: str | None = None
    assigned_to: str | None = Field(default=None, max_length=80)
    root_cause: str | None = Field(default=None, max_length=4000)
    resolution: str | None = Field(default=None, max_length=4000)
    prevention: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=2000)


def _notes(db: Session, kind: str, case_id: str) -> list[dict]:
    return [{"at": n.at.isoformat(), "by": n.by, "note": n.note} for n in db.scalars(
        select(CaseNote).where(CaseNote.case_kind == kind, CaseNote.case_id == case_id).order_by(CaseNote.at)).all()]


def _incident_out(db: Session, i: Incident, notes: bool = False) -> dict:
    out = {"id": i.id, "number": i.number, "title": i.title, "service": i.service, "severity": i.severity,
           "status": i.status, "impact": i.impact, "detected_at": i.detected_at.isoformat(),
           "reported_by": i.reported_by, "assigned_to": i.assigned_to, "root_cause": i.root_cause,
           "resolution": i.resolution, "prevention": i.prevention,
           "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
           "tickets": db.scalar(select(func.count(Ticket.id)).where(Ticket.incident_id == i.id)) or 0}
    if notes:
        out["notes"] = _notes(db, "incident", i.id)
    return out


@router.get("/it/incidents")
def incidents(open_only: bool = False, db: Session = Depends(get_db), _: User = Depends(can_view)) -> list[dict]:
    stmt = select(Incident).order_by(Incident.detected_at.desc()).limit(200)
    if open_only:
        stmt = stmt.where(Incident.status.notin_(("resolved", "closed")))
    return [_incident_out(db, i) for i in db.scalars(stmt).all()]


@router.post("/it/incidents", status_code=status.HTTP_201_CREATED)
def open_incident(body: IncidentIn, db: Session = Depends(get_db), user: User = Depends(can_view)) -> dict:
    if body.severity not in SEVERITIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown severity.")
    i = Incident(number=numbered(db, "INC", width=4), title=body.title.strip(), service=body.service.strip(),
                 severity=body.severity, impact=body.impact.strip(), detected_at=now(), reported_by=user.name,
                 assigned_to=user.name if user.role_id == "it" else "")
    db.add(i)
    db.flush()
    record(db, user.name, "it", "Incident opened", f"{i.number} {i.title} ({i.severity})", i.id)
    if i.severity in ("high", "critical"):
        notify_owners(db, "security_changed", f"{i.severity.title()} incident: {i.title}", i.impact,
                      f"/it/incidents/{i.id}", level="warn", exclude=user.id)
    db.commit()
    return _incident_out(db, i, notes=True)


@router.get("/it/incidents/{incident_id}")
def incident(incident_id: str, db: Session = Depends(get_db), _: User = Depends(can_view)) -> dict:
    i = db.get(Incident, incident_id)
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such incident.")
    return _incident_out(db, i, notes=True)


@router.patch("/it/incidents/{incident_id}")
def update_incident(incident_id: str, body: IncidentPatch, db: Session = Depends(get_db),
                    user: User = Depends(can_view)) -> dict:
    i = db.get(Incident, incident_id)
    if not i:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such incident.")
    if body.status and body.status not in INCIDENT_STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status.")
    if body.severity and body.severity not in SEVERITIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown severity.")
    if body.status in ("resolved", "closed") and not ((body.resolution or i.resolution).strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write what fixed it before resolving.")
    changes = []
    for field in ("status", "severity", "assigned_to", "root_cause", "resolution", "prevention"):
        value = getattr(body, field)
        if value is not None and value != getattr(i, field):
            changes.append(field.replace("_", " "))
            setattr(i, field, value.strip() if isinstance(value, str) else value)
    if body.status in ("resolved", "closed") and not i.resolved_at:
        i.resolved_at = now()
    if body.note and body.note.strip():
        db.add(CaseNote(case_kind="incident", case_id=i.id, at=now(), by=user.name, note=body.note.strip()))
        changes.append("note")
    if changes:
        record(db, user.name, "it", "Incident updated", f"{i.number}: {', '.join(changes)}" +
               (f" now {i.status}" if body.status else ""), i.id)
    db.commit()
    return _incident_out(db, i, notes=True)


# ---- support tickets ------------------------------------------------------------------

class TicketIn(BaseModel):
    module: str = Field(default="", max_length=40)
    description: str = Field(min_length=5, max_length=4000)
    page: str = Field(default="", max_length=160)
    app_version: str = Field(default="", max_length=40)
    error_reference: str = Field(default="", max_length=40)
    priority: str = "normal"


class TicketPatch(BaseModel):
    status: str | None = None
    priority: str | None = None
    assigned_to: str | None = Field(default=None, max_length=80)
    resolution: str | None = Field(default=None, max_length=4000)
    incident_id: str | None = None
    note: str | None = Field(default=None, max_length=2000)


def _ticket_out(db: Session, t: Ticket, notes: bool = False) -> dict:
    out = {"id": t.id, "number": t.number, "reporter": t.reporter, "module": t.module, "description": t.description,
           "page": t.page, "device": t.device, "app_version": t.app_version, "error_reference": t.error_reference,
           "priority": t.priority, "status": t.status, "assigned_to": t.assigned_to, "resolution": t.resolution,
           "incident_id": t.incident_id, "created_at": t.created_at.isoformat(), "updated_at": t.updated_at.isoformat()}
    if notes:
        out["notes"] = _notes(db, "ticket", t.id)
    return out


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
def report_problem(body: TicketIn, request: Request, db: Session = Depends(get_db),
                   user: User = Depends(can_report)) -> dict:
    """Anyone can report a problem. The device is taken from the browser, not typed."""
    if body.priority not in PRIORITIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown priority.")
    device, browser = describe_device(request.headers.get("user-agent", ""))
    moment = now()
    t = Ticket(number=numbered(db, "TKT", width=4), reporter_id=user.id, reporter=user.name,
               module=body.module.strip(), description=body.description.strip(), page=body.page.strip(),
               device=f"{device}, {browser}", app_version=body.app_version.strip() or APP_VERSION,
               error_reference=body.error_reference.strip(), priority=body.priority, created_at=moment,
               updated_at=moment)
    db.add(t)
    db.flush()
    record(db, user.name, "it", "Problem reported", f"{t.number}: {t.description[:80]}", t.id)
    it_people = db.scalars(select(User).where(User.role_id == "it", User.is_active.is_(True))).all()
    notify(db, list(it_people), "ticket", f"New problem report {t.number}", f"{user.name}: {t.description[:120]}",
           f"/it/tickets/{t.id}", "warn" if t.priority in ("high", "urgent") else "info", optional=False)
    db.commit()
    return _ticket_out(db, t)


@router.get("/tickets/mine")
def my_tickets(db: Session = Depends(get_db), user: User = Depends(can_report)) -> list[dict]:
    rows = db.scalars(select(Ticket).where(Ticket.reporter_id == user.id).order_by(Ticket.created_at.desc()).limit(50)).all()
    return [_ticket_out(db, t, notes=True) for t in rows]


@router.get("/it/tickets")
def tickets(open_only: bool = False, db: Session = Depends(get_db), _: User = Depends(can_view)) -> list[dict]:
    stmt = select(Ticket).order_by(Ticket.created_at.desc()).limit(300)
    if open_only:
        stmt = stmt.where(Ticket.status.notin_(("resolved", "closed")))
    return [_ticket_out(db, t) for t in db.scalars(stmt).all()]


@router.get("/it/tickets/{ticket_id}")
def ticket(ticket_id: str, db: Session = Depends(get_db), _: User = Depends(can_view)) -> dict:
    t = db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such ticket.")
    return _ticket_out(db, t, notes=True)


@router.patch("/it/tickets/{ticket_id}")
def update_ticket(ticket_id: str, body: TicketPatch, db: Session = Depends(get_db), user: User = Depends(can_view)) -> dict:
    t = db.get(Ticket, ticket_id)
    if not t:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such ticket.")
    if body.status and body.status not in TICKET_STATES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown status.")
    if body.priority and body.priority not in PRIORITIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown priority.")
    if body.incident_id and not db.get(Incident, body.incident_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such incident.")
    if body.status in ("resolved", "closed") and not ((body.resolution or t.resolution).strip()):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Write what was done before resolving.")
    changes = []
    for field in ("status", "priority", "assigned_to", "resolution", "incident_id"):
        value = getattr(body, field)
        if value is not None and value != getattr(t, field):
            changes.append(field.replace("_", " "))
            setattr(t, field, value.strip() if isinstance(value, str) else value)
    if body.note and body.note.strip():
        db.add(CaseNote(case_kind="ticket", case_id=t.id, at=now(), by=user.name, note=body.note.strip()))
        changes.append("note")
    if changes:
        t.updated_at = now()
        record(db, user.name, "it", "Ticket updated", f"{t.number}: {', '.join(changes)}", t.id)
        reporter = db.get(User, t.reporter_id)
        if reporter and reporter.id != user.id and (body.status or body.note):
            notify(db, [reporter], "ticket", f"Your problem report {t.number}: {t.status}",
                   (body.note or body.resolution or "")[:200], "/profile/support", optional=False)
    db.commit()
    return _ticket_out(db, t, notes=True)


# ---- errors and security events ---------------------------------------------------------

@router.get("/it/errors")
def errors(show: str = Query(default="new"), db: Session = Depends(get_db), _: User = Depends(can_view)) -> list[dict]:
    stmt = select(ErrorRecord).order_by(ErrorRecord.last_seen.desc()).limit(200)
    if show in ("new", "resolved"):
        stmt = stmt.where(ErrorRecord.status == show)
    return [{"id": e.id, "reference": e.reference, "kind": e.kind, "module": e.module, "path": e.path,
             "method": e.method, "message": e.message, "where": e.where, "count": e.count,
             "first_seen": e.first_seen.isoformat(), "last_seen": e.last_seen.isoformat(), "status": e.status,
             "version": e.version} for e in db.scalars(stmt).all()]


@router.post("/it/errors/{error_id}/resolve")
def resolve_error(error_id: str, db: Session = Depends(get_db), user: User = Depends(can_view)) -> dict:
    e = db.get(ErrorRecord, error_id)
    if not e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such error.")
    e.status = "resolved"
    record(db, user.name, "it", "Error marked resolved", f"{e.kind} at {e.path}", e.id)
    db.commit()
    return {"ok": True}


@router.get("/it/security")
def security_events(show: str = Query(default="open"), db: Session = Depends(get_db),
                    _: User = Depends(can_view)) -> list[dict]:
    stmt = select(SecurityEvent).order_by(SecurityEvent.at.desc()).limit(300)
    if show in ("open", "reviewed"):
        stmt = stmt.where(SecurityEvent.status == show)
    return [{"id": s.id, "at": s.at.isoformat(), "kind": s.kind, "severity": s.severity, "detail": s.detail,
             "account": s.account, "ip": s.ip, "path": s.path, "status": s.status, "note": s.note,
             "reviewed_by": s.reviewed_by} for s in db.scalars(stmt).all()]


class ReviewIn(BaseModel):
    note: str = Field(min_length=3, max_length=300)


@router.post("/it/security/{event_id}/review")
def review_event(event_id: str, body: ReviewIn, db: Session = Depends(get_db), user: User = Depends(can_view)) -> dict:
    s = db.get(SecurityEvent, event_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such event.")
    s.status, s.note, s.reviewed_by = "reviewed", body.note.strip(), user.name
    record(db, user.name, "it", "Security event reviewed", f"{s.kind}: {body.note.strip()}", s.id)
    db.commit()
    return {"ok": True}


# ---- technical audit and resources --------------------------------------------------------

@router.get("/it/audit")
def technical_audit(db: Session = Depends(get_db), _: User = Depends(can_view)) -> list[dict]:
    """What IT and security-related actions happened. IT cannot change or remove these rows."""
    rows = db.scalars(select(AuditLog).where(AuditLog.area.in_(("it", "security", "settings")))
                      .order_by(AuditLog.at.desc()).limit(300)).all()
    return [{"at": a.at.isoformat(), "actor": a.actor, "area": a.area, "action": a.action, "detail": a.detail,
             "reference": a.reference} for a in rows]


@router.get("/it/resources")
def resources(db: Session = Depends(get_db), _: User = Depends(can_view)) -> dict:
    size = db.scalar(text("SELECT pg_database_size(current_database())"))
    tables = db.execute(text(
        "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 12")).all()
    connections = db.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"))
    from app.api.v1.settings_api import UPLOADS
    uploads = sum(p.stat().st_size for p in Path(UPLOADS).rglob("*") if p.is_file()) if Path(UPLOADS).exists() else 0
    try:
        import resource
        rss_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    except Exception:
        rss_mb = None
    return {
        "database_mb": round((size or 0) / 1e6, 1), "connections": connections,
        "largest_tables": [{"table": t, "rows": n} for t, n in tables],
        "uploads_mb": round(uploads / 1e6, 1), "server_memory_mb": rss_mb,
        "python": sys.version.split()[0], "platform": platform.platform(terse=True),
        "uptime_minutes": round((time.time() - STARTED) / 60), "version": APP_VERSION,
        "hosting_costs": "Not connected to a hosting account. See documentation\\HOSTING-COSTS.md for the estimate.",
    }



# ---- email ----------------------------------------------------------------------------

@router.get("/it/email")
def email_overview(db: Session = Depends(get_db), _: User = Depends(can_view)) -> dict:
    """Delivery records without bodies: no code or link is ever shown here."""
    from app.services import email as mail
    from app.models.access import EmailMessage
    rows = db.scalars(select(EmailMessage).order_by(EmailMessage.at.desc()).limit(100)).all()
    return {"status": mail.status(),
            "messages": [{"at": m.at.isoformat(), "to": mail.mask(m.to), "purpose": m.purpose, "subject": m.subject
                          if m.purpose == "alert" or m.purpose == "test" else m.purpose.replace("_", " "),
                          "status": m.status, "error": m.error, "ms": m.ms} for m in rows]}


@router.post("/it/email/test")
def email_test(db: Session = Depends(get_db), user: User = Depends(can_view)) -> dict:
    """A test message to the IT person's own confirmed address, nobody else's."""
    from app.services import email as mail
    if not user.email_verified_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirm your own email address first (Profile, Security).")
    try:
        mail.send(db, user.email, "Green Buffet test email", f"Sent from the IT workspace by {user.name}. "
                  "If you can read this, email from the system works.", "test")
        result = {"ok": True, "detail": f"Sent to {mail.mask(user.email)}. Check that it arrived."}
    except mail.EmailNotSent as exc:
        result = {"ok": False, "detail": str(exc)}
    record(db, user.name, "it", "Test email", result["detail"])
    db.commit()
    return result
