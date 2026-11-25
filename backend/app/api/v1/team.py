"""Profiles, the team directory, presence, sessions and account notices.

Built on what was already there: the user accounts, the staff list
(employees), clocking, leave, the till shifts and the audit log. Nothing here
keeps a second copy of activity; the Activity tab reads the business records
and the audit log directly.

Who may see what:
    everyone             their own profile, all of its tabs
    team.view            other people's overview, activity, attendance and permissions
    hr.view / hr.manage  employment details
    payroll.view         pay and documents
    security.manage      sign-in history, devices, archiving, two-step reset
    staff.manage         suspend, restore, change role, reset a password
"""
from __future__ import annotations

import io
import json
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import PERMISSION_CATALOGUE, current_user
from app.models.access import AuditLog, LoginAttempt, Notification, User, UserSession
from app.models.files import Document
from app.models.kitchen import KitchenItem
from app.models.people import Attendance, Employee, LeaveRequest, Payslip
from app.models.sales import CashMovement, Order, Payment, Shift
from app.models.stock import StockMove
from app.services.accounts import (
    OPTIONAL_KINDS, end_sessions, has_two_step, notify, notify_owners, now, presence, session_out, setting_int,
    two_step_required,
)
from app.services.audit import record

router = APIRouter(tags=["team"])

LUSAKA = timezone(timedelta(hours=2))
PERMISSION_LABELS = {code: (label, area) for code, label, area, _ in PERMISSION_CATALOGUE}


def _can(user: User, *codes: str) -> bool:
    held = set(user.role.permission_codes)
    return any(c in held for c in codes)


def _initials(name: str) -> str:
    parts = [p for p in (name or "").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def _today() -> date:
    return datetime.now(LUSAKA).date()


def _employees_by_user(db: Session, user_ids: list[str]) -> dict[str, Employee]:
    rows = db.scalars(select(Employee).where(Employee.user_id.in_(user_ids))).all()
    return {e.user_id: e for e in rows if e.user_id}


def _account_status(u: User) -> dict:
    if u.archived_at:
        return {"code": "archived", "label": "Archived"}
    if not u.is_active:
        return {"code": "suspended", "label": "Suspended"}
    if u.must_change_password:
        return {"code": "new", "label": "Active · new password needed"}
    return {"code": "active", "label": "Active"}


def _duty(db: Session, employees: dict[str, Employee], users: list[User]) -> dict[str, dict]:
    """Who is clocked in, on leave, or has a till open: from clocking and the tills only."""
    today = _today()
    emp_ids = [e.id for e in employees.values()]
    open_clock = {
        a.employee_id: a for a in db.scalars(select(Attendance).where(
            Attendance.employee_id.in_(emp_ids), Attendance.clock_out.is_(None),
            Attendance.day >= today - timedelta(days=1))).all()
    } if emp_ids else {}
    on_leave = {
        lr.employee_id for lr in db.scalars(select(LeaveRequest).where(
            LeaveRequest.employee_id.in_(emp_ids), LeaveRequest.status == "approved",
            LeaveRequest.start <= today, LeaveRequest.end >= today)).all()
    } if emp_ids else set()
    tills = {s.opened_by_id: s for s in db.scalars(select(Shift).where(
        Shift.closed_at.is_(None), Shift.opened_by_id.in_([u.id for u in users]))).all()}
    out = {}
    for u in users:
        e = employees.get(u.id)
        clock = open_clock.get(e.id) if e else None
        till = tills.get(u.id)
        out[u.id] = {
            "on_staff_list": e is not None,
            "on_duty": clock is not None,
            "since": clock.clock_in.isoformat() if clock else None,
            "on_leave": bool(e and e.id in on_leave),
            "till_open": till is not None,
            "till_since": till.opened_at.isoformat() if till else None,
        }
    return out


def _duty_label(d: dict) -> str:
    if d["on_leave"]:
        return "On leave"
    if d["on_duty"]:
        return "On duty"
    if not d["on_staff_list"]:
        return "Not on the staff list"
    return "Off duty"


def _card(u: User, e: Employee | None, p: dict, d: dict) -> dict:
    return {
        "id": u.id, "name": u.name, "initials": _initials(u.name), "photo_id": u.photo_id,
        "role_id": u.role_id, "role_label": u.role.label,
        "job_title": (e.job_title if e and e.job_title else u.role.label),
        "department": e.department if e else "",
        "employee_number": e.number if e else "",
        "presence": p, "duty": d, "duty_label": _duty_label(d),
        "account": _account_status(u),
    }


def _target(db: Session, user_id: str) -> User:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such account.")
    return u


# ---- presence ----------------------------------------------------------------

class HeartbeatIn(BaseModel):
    # Someone touched the screen (key, tap, mouse) since the last heartbeat.
    active: bool = False
    # The page is being closed on purpose.
    closing: bool = False


@router.post("/presence/heartbeat")
def heartbeat(body: HeartbeatIn, request: Request, user: User = Depends(current_user),
              db: Session = Depends(get_db)) -> dict:
    """Sent by each open screen every 30 seconds, and once as it closes."""
    sid = getattr(request.state, "session_id", None)
    session = db.get(UserSession, sid) if sid else None
    moment = now()
    if session:
        session.last_seen_at = moment
        if body.closing:
            session.closed_at = moment
        else:
            session.closed_at = None
            if body.active and not session.locked_at:
                session.last_active_at = moment
    unread = db.scalar(select(func.count(Notification.id)).where(
        Notification.user_id == user.id, Notification.read_at.is_(None))) or 0
    db.commit()
    return {
        "tracked": session is not None,
        "locked": bool(session and session.locked_at),
        "unread": unread,
        "away_minutes": setting_int(db, "presence.away_minutes", 5),
        "lock_minutes": setting_int(db, "lock.after_minutes", 10),
        "server_time": moment.isoformat(),
    }


# ---- notifications -----------------------------------------------------------

@router.get("/notifications")
def notifications(unread: bool = False, limit: int = Query(default=40, le=200),
                  user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(stmt.order_by(Notification.at.desc()).limit(limit)).all()
    return [{"id": n.id, "at": n.at.isoformat(), "kind": n.kind, "level": n.level, "title": n.title,
             "body": n.body, "link": n.link, "read": n.read_at is not None} for n in rows]


class ReadIn(BaseModel):
    ids: list[str] = []
    all: bool = False


@router.post("/notifications/read")
def read_notifications(body: ReadIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    stmt = select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if not body.all:
        stmt = stmt.where(Notification.id.in_(body.ids or ["-"]))
    moment = now()
    count = 0
    for n in db.scalars(stmt).all():
        n.read_at = moment
        count += 1
    db.commit()
    return {"marked": count}


# ---- the profile -------------------------------------------------------------

TABS = ("overview", "activity", "attendance", "permissions", "logins", "sessions", "employment", "payroll", "security")


def _tabs(viewer: User, target: User) -> list[str]:
    me = viewer.id == target.id
    allowed = {
        "overview": True,
        "activity": me or _can(viewer, "team.view"),
        "attendance": me or _can(viewer, "team.view", "hr.view", "attendance.manage"),
        "permissions": me or _can(viewer, "team.view", "roles.manage", "staff.manage"),
        "logins": me or _can(viewer, "security.manage"),
        "sessions": me or _can(viewer, "security.manage"),
        "employment": me or _can(viewer, "hr.view", "hr.manage"),
        "payroll": me or _can(viewer, "payroll.view"),
        "security": me or _can(viewer, "security.manage"),
    }
    return [t for t in TABS if allowed[t]]


def _require_tab(viewer: User, target: User, tab: str) -> None:
    if tab not in _tabs(viewer, target):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{viewer.role.label} accounts cannot see this.")


def _actions(db: Session, viewer: User, t: User) -> dict:
    me = viewer.id == t.id
    other_owner = t.role_id == "owner" and not me
    staff = _can(viewer, "staff.manage")
    sec = _can(viewer, "security.manage")
    return {
        "edit_account": staff,
        "edit_employment": _can(viewer, "hr.manage"),
        "change_role": staff and not other_owner and not me,
        "suspend": staff and not me and not other_owner and t.is_active,
        "restore": (not t.is_active) and ((sec if t.archived_at else staff)),
        "archive": sec and not me and t.role_id != "owner" and not t.archived_at,
        "reset_password": staff and not me,
        "revoke_sessions": me or sec,
        "reset_two_step": sec and not me and t.role_id != "owner" and t.totp_enabled,
    }


def _responsibilities(u: User) -> list[dict]:
    groups: dict[str, list[str]] = {}
    for code in u.role.permission_codes:
        label, area = PERMISSION_LABELS.get(code, (code, "Other"))
        groups.setdefault(area, []).append(label)
    return [{"area": a, "items": sorted(items)} for a, items in groups.items()]


def _profile(db: Session, viewer: User, t: User) -> dict:
    me = viewer.id == t.id
    employees = _employees_by_user(db, [t.id])
    e = employees.get(t.id)
    p = presence(db, [t])[t.id]
    d = _duty(db, employees, [t])[t.id]
    out = _card(t, e, p, d)
    out.update({
        "email": t.email,
        "phone": (e.phone if e and e.phone else t.phone),
        "employment_status": (
            "On leave" if d["on_leave"] else
            ("Employed" if e.is_active else "Left") if e else "Not on the staff list"),
        "start_date": e.start_date.isoformat() if e and e.start_date else None,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "created_by": t.created_by or "",
        "responsibilities": _responsibilities(t),
        "two_step": {"enabled": has_two_step(t), "app": t.totp_enabled, "method": t.two_step_method or ("app" if t.totp_enabled else ""),
                     "required": two_step_required(db, t)},
        "email_verified": t.email_verified_at is not None,
        "tabs": _tabs(viewer, t),
        "can": _actions(db, viewer, t),
        "is_me": me,
    })
    if me or _can(viewer, "staff.manage", "security.manage"):
        out["suspended_reason"] = t.suspended_reason
        out["archived_at"] = t.archived_at.isoformat() if t.archived_at else None
    if me:
        try:
            prefs = json.loads(t.preferences or "{}")
        except ValueError:
            prefs = {}
        out["preferences"] = {
            "notify": {k: prefs.get("notify", {}).get(k, True) is not False for k in OPTIONAL_KINDS},
            "labels": OPTIONAL_KINDS,
        }
    return out


def _may_open(viewer: User, t: User) -> None:
    if viewer.id != t.id and not _can(viewer, "team.view", "staff.manage", "hr.view", "security.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{viewer.role.label} accounts cannot open other people's profiles.")


@router.get("/profile/me")
def my_profile(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    return _profile(db, user, user)


class MyProfileIn(BaseModel):
    # Only what a person may change about themselves. Role, pay, status and
    # employee number are not here, so they cannot be sent.
    phone: str | None = Field(default=None, max_length=24)
    notify: dict[str, bool] | None = None


@router.put("/profile/me")
def update_my_profile(body: MyProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    changes_before, changes_after = {}, {}
    if body.phone is not None:
        phone = "".join(ch for ch in body.phone if ch.isdigit() or ch in "+ ").strip()
        e = _employees_by_user(db, [user.id]).get(user.id)
        old = e.phone if e and e.phone else user.phone
        if phone != old:
            changes_before["phone"], changes_after["phone"] = old, phone
            user.phone = phone
            if e:
                e.phone = phone
    if body.notify is not None:
        try:
            prefs = json.loads(user.preferences or "{}")
        except ValueError:
            prefs = {}
        current = prefs.get("notify", {})
        wanted = {k: bool(v) for k, v in body.notify.items() if k in OPTIONAL_KINDS}
        if wanted != {k: current.get(k, True) for k in wanted}:
            changes_before["notify"], changes_after["notify"] = current, {**current, **wanted}
            prefs["notify"] = {**current, **wanted}
            user.preferences = json.dumps(prefs)
    if changes_after:
        record(db, user.name, "users", "Own profile changed", ", ".join(changes_after), user.id,
               before=changes_before, after=changes_after)
        db.commit()
    return _profile(db, user, user)


# ---- photographs ---------------------------------------------------------------

PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}
PHOTO_MAX = 4 * 1024 * 1024


def _uploads():
    from app.api.v1.settings_api import UPLOADS
    return UPLOADS


@router.post("/profile/me/photo")
async def set_my_photo(file: UploadFile = File(...), user: User = Depends(current_user),
                       db: Session = Depends(get_db)) -> dict:
    if file.content_type not in PHOTO_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Use a JPEG, PNG or WebP photograph.")
    data = await file.read(PHOTO_MAX + 1)
    if len(data) > PHOTO_MAX:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "That photograph is over 4 MB.")
    from PIL import Image, ImageOps
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(data))).convert("RGB")
    except Exception:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That file is not a photograph that can be read.")
    # A square, centred, small enough for an avatar: nothing else is kept.
    side = min(image.size)
    left, top = (image.width - side) // 2, (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize((320, 320))
    folder = _uploads() / "user"
    folder.mkdir(parents=True, exist_ok=True)
    _remove_photo(db, user)
    doc = Document(name=f"{user.name} photo.jpg", kind="photo", attached_to="user", attached_id=user.id,
                   path="", media_type="image/jpeg", is_primary=True, created_by=user.name)
    db.add(doc)
    db.flush()
    image.save(folder / f"{doc.id}.jpg", "JPEG", quality=85)
    doc.path = f"user/{doc.id}.jpg"
    doc.size_bytes = (folder / f"{doc.id}.jpg").stat().st_size
    user.photo_id = doc.id
    record(db, user.name, "users", "Profile photograph changed", "", user.id)
    db.commit()
    return {"photo_id": doc.id}


def _remove_photo(db: Session, user: User) -> None:
    if not user.photo_id:
        return
    old = db.get(Document, user.photo_id)
    if old:
        full = _uploads() / old.path
        try:
            if full.resolve().is_relative_to(_uploads().resolve()) and full.exists():
                full.unlink()
        except OSError:
            pass
        db.delete(old)
    user.photo_id = None


@router.delete("/profile/me/photo")
def remove_my_photo(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if user.photo_id:
        _remove_photo(db, user)
        record(db, user.name, "users", "Profile photograph removed", "", user.id)
        db.commit()
    return {"photo_id": None}


@router.get("/profile/photo/{user_id}")
def photo(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Profile photographs are seen by colleagues on the team pages and by the person."""
    t = _target(db, user_id)
    if t.id != user.id and not _can(user, "team.view", "staff.manage", "hr.view", "security.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available.")
    doc = db.get(Document, t.photo_id) if t.photo_id else None
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photograph.")
    full = _uploads() / doc.path
    if not full.resolve().is_relative_to(_uploads().resolve()) or not full.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No photograph.")
    return FileResponse(full, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


# ---- the directory -------------------------------------------------------------

can_see_team = ("team.view", "staff.manage", "hr.view", "security.manage")


def _team_guard(user: User = Depends(current_user)) -> User:
    if not _can(user, *can_see_team):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{user.role.label} accounts cannot see the team directory.")
    return user


@router.get("/team")
def team(archived: bool = False, user: User = Depends(_team_guard), db: Session = Depends(get_db)) -> list[dict]:
    stmt = select(User).order_by(User.name)
    if not archived:
        stmt = stmt.where(User.archived_at.is_(None))
    users = list(db.scalars(stmt).all())
    employees = _employees_by_user(db, [u.id for u in users])
    p = presence(db, users)
    d = _duty(db, employees, users)
    return [_card(u, employees.get(u.id), p[u.id], d[u.id]) for u in users]


@router.get("/team/summary")
def team_summary(user: User = Depends(_team_guard), db: Session = Depends(get_db)) -> dict:
    """The owner's Team status card."""
    users = list(db.scalars(select(User).where(User.archived_at.is_(None))).all())
    employees = _employees_by_user(db, [u.id for u in users])
    p = presence(db, users)
    d = _duty(db, employees, users)
    active_users = [u for u in users if u.is_active]
    count = lambda pred: sum(1 for u in active_users if pred(u))  # noqa: E731
    # Clocked in counts everyone on the staff list, accounts or not.
    today = _today()
    on_duty = db.scalar(select(func.count(Attendance.id)).where(
        Attendance.clock_out.is_(None), Attendance.day >= today - timedelta(days=1))) or 0
    on_leave = db.scalar(select(func.count(func.distinct(LeaveRequest.employee_id))).where(
        LeaveRequest.status == "approved", LeaveRequest.start <= today, LeaveRequest.end >= today)) or 0
    connected = [u for u in active_users if p[u.id]["status"] in ("online", "away", "lost")]
    connected.sort(key=lambda u: ({"online": 0, "away": 1, "lost": 2}[p[u.id]["status"]], u.name))
    return {
        "registered": len(active_users),
        "online": count(lambda u: p[u.id]["status"] == "online"),
        "away": count(lambda u: p[u.id]["status"] == "away"),
        "lost": count(lambda u: p[u.id]["status"] == "lost"),
        "offline": count(lambda u: p[u.id]["status"] in ("offline", "unknown")),
        "on_duty": on_duty,
        "on_leave": on_leave,
        "suspended": sum(1 for u in users if not u.is_active),
        "connected": [_card(u, employees.get(u.id), p[u.id], d[u.id]) for u in connected[:8]],
    }


@router.get("/team/{user_id}")
def profile(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _may_open(user, t)
    return _profile(db, user, t)


# ---- activity ------------------------------------------------------------------

# What each kind of work looks like in the audit log: (label, area, action).
ACTIVITY = {
    "Counter": [
        ("Orders taken", "sales", "Order taken"),
        ("Orders changed", "sales", "Order changed"),
        ("Discounts given", "sales", "Discount given"),
        ("Refunds", "money", "Refund given"),
        ("Receipts reprinted", "sales", "Receipt reprinted"),
        ("Orders cancelled", "sales", "Order cancelled"),
        ("Tills opened", "sales", "Till opened"),
        ("Tills closed", "sales", "Till closed"),
        ("Cash drops and petty cash", "money", "Cash movement "),
    ],
    "Kitchen": [
        ("Kitchen steps undone", "sales", "Kitchen step undone"),
        ("Stock counted", "stock", "Stock counted"),
    ],
    "Approvals and running the place": [
        ("Till counts reviewed", "sales", "Till count reviewed"),
        ("Payments confirmed", "money", "Payment confirmed"),
        ("Purchases drafted", "stock", "Purchase drafted"),
        ("Deliveries checked in", "stock", "Delivery checked in"),
        ("Staff records changed", "people", "Employee changed"),
        ("Staff added", "people", "Employee added"),
        ("Settings changed", "settings", "Settings changed"),
        ("Preparation time changed", "settings", "Preparation time changed"),
    ],
    "Money and payroll": [
        ("Journal entries written", "money", "Journal entry written"),
        ("Journal entries approved", "money", "Journal entry approved"),
        ("Journal entries reversed", "money", "Journal entry reversed"),
        ("Suppliers paid", "money", "Supplier paid"),
        ("Payroll prepared", "people", "Payroll prepared"),
        ("Payroll approved", "people", "Payroll approved"),
        ("Wages paid", "people", "Wages paid"),
        ("Accounts changed", "money", "Account changed"),
    ],
    "Owner": [
        ("Prices changed", "menu", "Price changed"),
        ("Menu items added", "menu", "Menu item added"),
        ("Role permissions changed", "security", "Role permissions changed"),
        ("Accounts made", "security", "User account created"),
        ("Accounts changed", "security", "User account changed"),
        ("Passwords reset", "security", "Password reset"),
        ("Payroll rates changed", "people", "Payroll rates changed"),
    ],
}


def _activity(db: Session, t: User, days: int) -> dict:
    since = now() - timedelta(days=days)
    name = t.name
    counts = {
        (area, action): n for area, action, n in db.execute(
            select(AuditLog.area, AuditLog.action, func.count(AuditLog.id))
            .where(AuditLog.actor == name, AuditLog.at >= since)
            .group_by(AuditLog.area, AuditLog.action)).all()
    }
    groups = []
    for title, items in ACTIVITY.items():
        rows = [{"label": label, "count": counts.get((area, action), 0)} for label, area, action in items]
        groups.append({"title": title, "rows": rows})

    # Figures straight from the business records, attributed by name.
    sales = db.scalar(select(func.coalesce(func.sum(Payment.amount_ngwee), 0)).where(
        Payment.created_by == name, Payment.created_at >= since, Payment.is_refund.is_(False),
        Payment.status != "failed")) or 0
    paid_orders = db.scalar(select(func.count(Order.id)).where(
        Order.created_by == name, Order.created_at >= since, Order.status == "paid")) or 0
    tickets = db.scalar(select(func.count(KitchenItem.id)).where(
        KitchenItem.handled_by == name, KitchenItem.ready_at.is_not(None), KitchenItem.ready_at >= since)) or 0
    started = db.scalar(select(func.count(KitchenItem.id)).where(
        KitchenItem.handled_by == name, KitchenItem.started_at.is_not(None), KitchenItem.started_at >= since)) or 0
    waste = db.scalar(select(func.count(StockMove.id)).where(
        StockMove.created_by == name, StockMove.kind == "waste", StockMove.created_at >= since)) or 0
    adjustments = db.scalar(select(func.count(StockMove.id)).where(
        StockMove.created_by == name, StockMove.kind == "adjustment", StockMove.created_at >= since)) or 0
    approvals = sum([
        db.scalar(select(func.count(Order.id)).where(Order.discount_approved_by == name, Order.created_at >= since)) or 0,
        db.scalar(select(func.count(CashMovement.id)).where(CashMovement.decided_by == name, CashMovement.decided_at >= since)) or 0,
        db.scalar(select(func.count(LeaveRequest.id)).where(LeaveRequest.decided_by == name, LeaveRequest.decided_at >= since)) or 0,
    ])
    closed = db.scalars(select(Shift).where(Shift.closed_by == name, Shift.closed_at >= since)
                        .order_by(Shift.closed_at.desc()).limit(10)).all()
    tills = [{"closed_at": s.closed_at.isoformat(), "variance_ngwee": s.variance_ngwee or 0,
              "reviewed": bool(s.reviewed_by), "note": s.review_note or ""} for s in closed]

    figures = [
        {"label": "Taken in payments", "money": sales, "kind": "Counter"},
        {"label": "Orders sold", "count": paid_orders, "kind": "Counter"},
        {"label": "Kitchen tickets started", "count": started, "kind": "Kitchen"},
        {"label": "Kitchen tickets marked ready", "count": tickets, "kind": "Kitchen"},
        {"label": "Waste recorded", "count": waste, "kind": "Kitchen"},
        {"label": "Stock adjustments", "count": adjustments, "kind": "Approvals and running the place"},
        {"label": "Discounts, cash moves and leave approved", "count": approvals,
         "kind": "Approvals and running the place"},
    ]
    for f in figures:
        for g in groups:
            if g["title"] == f["kind"]:
                g["rows"].insert(0, {k: v for k, v in f.items() if k != "kind"})
    # Groups where nothing happened are left out; the person's own kind of
    # work comes first.
    first = {"cashier": "Counter", "kitchen": "Kitchen", "manager": "Approvals and running the place",
             "accountant": "Money and payroll", "owner": "Owner"}.get(t.role_id)
    groups = [g for g in groups if any(r.get("count") or r.get("money") for r in g["rows"])]
    groups.sort(key=lambda g: 0 if g["title"] == first else 1)
    for g in groups:
        g["rows"] = [r for r in g["rows"] if r.get("count") or r.get("money")]

    recent = db.scalars(select(AuditLog).where(AuditLog.actor == name)
                        .order_by(AuditLog.at.desc()).limit(40)).all()
    return {
        "days": days,
        "groups": groups,
        "tills": tills,
        "recent": [{"at": a.at.isoformat(), "area": a.area, "action": a.action.strip(),
                    "detail": a.detail, "reference": a.reference} for a in recent],
        "note": "Work is matched by the name on the account. If someone's name was changed, "
                "work done under the old name is not counted here.",
    }


@router.get("/team/{user_id}/activity")
def activity(user_id: str, days: int = Query(default=30, ge=1, le=365),
             user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _require_tab(user, t, "activity")
    return _activity(db, t, days)


# ---- attendance and shifts -------------------------------------------------------

@router.get("/team/{user_id}/attendance")
def attendance(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _require_tab(user, t, "attendance")
    e = _employees_by_user(db, [t.id]).get(t.id)
    since = _today() - timedelta(days=30)
    rows = db.scalars(select(Attendance).where(Attendance.employee_id == e.id, Attendance.day >= since)
                      .order_by(Attendance.day.desc(), Attendance.clock_in.desc())).all() if e else []
    leave = db.scalars(select(LeaveRequest).where(LeaveRequest.employee_id == e.id)
                       .order_by(LeaveRequest.start.desc()).limit(10)).all() if e else []
    shifts = db.scalars(select(Shift).where(Shift.opened_by_id == t.id)
                        .order_by(Shift.opened_at.desc()).limit(15)).all()
    hours = 0.0
    for a in rows:
        end = a.clock_out or now()
        hours += max(0.0, (end - a.clock_in).total_seconds() / 3600)
    return {
        "on_staff_list": e is not None,
        "duty": _duty(db, {t.id: e} if e else {}, [t])[t.id],
        "hours_30_days": round(hours, 1),
        "days_30": len({a.day for a in rows}),
        "clocking": [{"day": a.day.isoformat(), "in": a.clock_in.isoformat(),
                      "out": a.clock_out.isoformat() if a.clock_out else None, "note": a.note} for a in rows],
        "leave": [{"kind": lr.kind, "start": lr.start.isoformat(), "end": lr.end.isoformat(),
                   "days": lr.days, "status": lr.status} for lr in leave],
        "tills": [{"opened_at": s.opened_at.isoformat(), "closed_at": s.closed_at.isoformat() if s.closed_at else None,
                   "variance_ngwee": s.variance_ngwee if s.closed_at else None} for s in shifts],
        "note": "Attendance comes from clocking in and out only. Being offline in the system "
                "is not counted as absence.",
    }


# ---- roles and permissions -------------------------------------------------------

@router.get("/team/{user_id}/permissions")
def permissions(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _require_tab(user, t, "permissions")
    return {"role_id": t.role_id, "role_label": t.role.label, "description": t.role.description,
            "groups": _responsibilities(t)}


# ---- sign-in history and devices ---------------------------------------------------

@router.get("/team/{user_id}/logins")
def logins(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[dict]:
    t = _target(db, user_id)
    _require_tab(user, t, "logins")
    rows = db.scalars(select(LoginAttempt).where(LoginAttempt.email == t.email)
                      .order_by(LoginAttempt.at.desc()).limit(60)).all()
    return [{"at": r.at.isoformat(), "ok": r.succeeded, "ip": r.ip, "device": r.device} for r in rows]


@router.get("/team/{user_id}/sessions")
def sessions(user_id: str, request: Request, user: User = Depends(current_user),
             db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _require_tab(user, t, "sessions")
    away = setting_int(db, "presence.away_minutes", 5)
    moment = now()
    open_rows = db.scalars(select(UserSession).where(
        UserSession.user_id == t.id, UserSession.ended_at.is_(None), UserSession.expires_at > moment)
        .order_by(UserSession.started_at.desc())).all()
    ended = db.scalars(select(UserSession).where(
        UserSession.user_id == t.id, or_(UserSession.ended_at.is_not(None), UserSession.expires_at <= moment))
        .order_by(UserSession.started_at.desc()).limit(15)).all()
    current = getattr(request.state, "session_id", None)
    REASONS = {"signed_out": "Signed out", "switched": "Handed to someone else", "revoked": "Signed out by",
               "password": "Password changed or reset", "suspended": "Account suspended",
               "archived": "Account archived", "": "Expired"}

    def old(s: UserSession) -> dict:
        d = session_out(s, current, away)
        reason = REASONS.get(s.end_reason, s.end_reason) if s.ended_at else "Expired"
        if s.end_reason == "revoked":
            reason = f"Signed out by {s.ended_by}"
        d.update({"ended_at": (s.ended_at or s.expires_at).isoformat(), "reason": reason})
        return d

    return {"open": [session_out(s, current, away) for s in open_rows], "ended": [old(s) for s in ended]}


class RevokeIn(BaseModel):
    # One device, or every device but this one when empty.
    session_id: str | None = None
    include_this: bool = False


@router.post("/team/{user_id}/sessions/revoke")
def revoke(user_id: str, body: RevokeIn, request: Request, user: User = Depends(current_user),
           db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    if t.id != user.id and not _can(user, "security.manage"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{user.role.label} accounts cannot sign other people out.")
    if t.role_id == "owner" and t.id != user.id:
        # Owners are equal: signing the other owner out is allowed (it is how
        # a stolen device is stopped), and the other owner is told.
        notify(db, [t], "security", f"{user.name} signed out your devices",
               "If you did not expect this, check Security.", "/profile/security", "warn", optional=False)
    current = getattr(request.state, "session_id", None)
    moment = now()
    if body.session_id:
        s = db.get(UserSession, body.session_id)
        if not s or s.user_id != t.id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "That device is not signed in.")
        targets = [s] if not s.ended_at else []
    else:
        targets = [s for s in db.scalars(select(UserSession).where(
            UserSession.user_id == t.id, UserSession.ended_at.is_(None))).all()
            if body.include_this or s.id != current]
    for s in targets:
        s.ended_at, s.end_reason, s.ended_by = moment, "revoked", user.name
    if targets:
        what = f"{targets[0].device}, {targets[0].browser}" if body.session_id else f"{len(targets)} device(s)"
        record(db, user.name, "security", "Signed out remotely", f"{t.name}: {what}", t.id)
        if t.id != user.id:
            notify_owners(db, "access_changed", f"{t.name} was signed out", f"{what}, by {user.name}.",
                          f"/team/{t.id}", exclude=user.id)
    db.commit()
    return {"ended": len(targets)}


# ---- account actions -------------------------------------------------------------

class ReasonIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


def _guard_action(db: Session, viewer: User, t: User, action: str) -> None:
    if not _actions(db, viewer, t).get(action):
        if t.role_id == "owner" and t.id != viewer.id:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                "One owner cannot do this to the other. Use scripts\\reset-owner.ps1 on the "
                                "server computer if an owner account is compromised.")
        if t.id == viewer.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "You cannot do this to your own account.")
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{viewer.role.label} accounts cannot do this.")


@router.post("/team/{user_id}/suspend")
def suspend(user_id: str, body: ReasonIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _guard_action(db, user, t, "suspend")
    t.is_active = False
    t.suspended_reason = body.reason.strip()
    t.token_version = (t.token_version or 0) + 1
    ended = end_sessions(db, t, "suspended", user.name)
    record(db, user.name, "security", "Account suspended", f"{t.name}: {t.suspended_reason}", t.id,
           before={"active": True}, after={"active": False, "reason": t.suspended_reason})
    notify_owners(db, "account_suspended", f"{t.name}'s account suspended",
                  f"By {user.name}: {t.suspended_reason}. {ended} device(s) signed out.", f"/team/{t.id}",
                  level="warn", exclude=user.id)
    db.commit()
    return _profile(db, user, t)


@router.post("/team/{user_id}/restore")
def restore(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _guard_action(db, user, t, "restore")
    was = {"active": t.is_active, "archived": bool(t.archived_at), "reason": t.suspended_reason}
    t.is_active = True
    t.archived_at = None
    t.suspended_reason = ""
    db.query(LoginAttempt).filter(LoginAttempt.email == t.email, LoginAttempt.succeeded.is_(False)).delete()
    record(db, user.name, "security", "Account restored", t.name, t.id, before=was, after={"active": True})
    notify_owners(db, "account_suspended", f"{t.name}'s account restored", f"By {user.name}.", f"/team/{t.id}",
                  exclude=user.id)
    db.commit()
    return _profile(db, user, t)


@router.post("/team/{user_id}/archive")
def archive(user_id: str, body: ReasonIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """For someone who has left: switched off and out of the directory. Nothing they did is removed."""
    t = _target(db, user_id)
    _guard_action(db, user, t, "archive")
    t.is_active = False
    t.archived_at = now()
    t.suspended_reason = body.reason.strip()
    t.token_version = (t.token_version or 0) + 1
    end_sessions(db, t, "archived", user.name)
    record(db, user.name, "security", "Account archived", f"{t.name}: {t.suspended_reason}", t.id)
    notify_owners(db, "account_suspended", f"{t.name}'s account archived", f"By {user.name}: {t.suspended_reason}.",
                  f"/team/{t.id}", exclude=user.id)
    db.commit()
    return _profile(db, user, t)


@router.post("/team/{user_id}/two-step/reset")
def reset_two_step(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """For a lost phone. The person sets it up again at their next sign-in."""
    t = _target(db, user_id)
    _guard_action(db, user, t, "reset_two_step")
    t.totp_enabled, t.totp_secret, t.recovery_codes = False, "", "[]"
    record(db, user.name, "security", "Two-step sign-in reset", t.name, t.id)
    notify(db, [t], "security", "Your two-step sign-in was reset", f"By {user.name}. Set it up again under Security.",
           "/profile/security", "warn", optional=False)
    notify_owners(db, "security_changed", f"{t.name}'s two-step sign-in reset", f"By {user.name}.",
                  f"/team/{t.id}", exclude=user.id)
    db.commit()
    return _profile(db, user, t)


# ---- employment and pay ------------------------------------------------------------

@router.get("/team/{user_id}/employment")
def employment(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _require_tab(user, t, "employment")
    e = _employees_by_user(db, [t.id]).get(t.id)
    if not e:
        return {"on_staff_list": False}
    from app.api.v1.people import _leave_taken
    year = _today().year
    taken = _leave_taken(db, e.id, year)
    return {
        "on_staff_list": True, "employee_id": e.id, "number": e.number, "job_title": e.job_title,
        "department": e.department, "phone": e.phone,
        "start_date": e.start_date.isoformat() if e.start_date else None,
        "status": "Employed" if e.is_active else "Left",
        "leave_days_per_year": e.leave_days_per_year, "leave_taken": taken,
        "leave_left": e.leave_days_per_year - taken,
    }


@router.get("/team/{user_id}/payroll")
def payroll(user_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    t = _target(db, user_id)
    _require_tab(user, t, "payroll")
    e = _employees_by_user(db, [t.id]).get(t.id)
    if not e:
        return {"on_staff_list": False}
    from app.models.people import PayrollRun
    pairs = db.execute(select(Payslip, PayrollRun).join(PayrollRun, PayrollRun.id == Payslip.run_id)
                       .where(Payslip.employee_id == e.id).order_by(PayrollRun.period.desc()).limit(6)).all()
    slips = [s for s, _ in pairs]
    runs = {r.id: r for _, r in pairs}
    docs = db.scalars(select(Document).where(Document.attached_to == "employee", Document.attached_id == e.id)
                      .order_by(Document.created_at.desc())).all()
    account = e.pay_account or ""
    return {
        "on_staff_list": True,
        "basic_ngwee": e.basic_ngwee, "allowances_ngwee": e.allowances_ngwee,
        "pay_method": e.pay_method,
        # Only the last four digits: enough to recognise the account.
        "pay_account": ("•••• " + account[-4:]) if len(account) > 4 else account,
        "napsa_number": e.napsa_number, "tpin": e.tpin,
        "payslips": sorted([
            {"period": runs[s.run_id].period if s.run_id in runs else "", "status": runs[s.run_id].status if s.run_id in runs else "",
             "gross_ngwee": s.gross_ngwee, "net_ngwee": s.net_ngwee} for s in slips], key=lambda x: x["period"], reverse=True),
        "documents": [{"id": d.id, "name": d.name, "kind": d.kind, "at": d.created_at.isoformat() if d.created_at else None}
                      for d in docs],
    }
