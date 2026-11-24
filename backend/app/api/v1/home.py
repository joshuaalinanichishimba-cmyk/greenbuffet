"""The first screen after sign-in, one for each kind of account.

The demo opens every account on the same Overview, with only its sidebar
trimmed, and sends the kitchen straight to its board. The Green Buffet has
seven starting roles, and each one walks in with different questions:

    owner         how is the business doing, today and this month?
    administrator are the accounts, backups and server in order?
    manager       how is service going, and who is on today?
    accountant    what came in, what is owed, what needs approving?
    cashier       is my till open, what have I taken, who is waiting?
    kitchen       (straight to the kitchen board, as in the demo)
    inventory     what is running out, what is on order, what moved?

The owner and manager keep the demo's Overview and add the panels below; the
other roles get a home built for their job. Each endpoint has its own
permission guard, so a custom role sees exactly the panels its permissions
allow and nothing more.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.dashboard import (
    MOBILE, STATE_LABELS, _day_bounds, _initials, _items_text, _local, _paid_between, _today,
    kitchen_state,
)
from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import AuditLog, LoginAttempt, Role, User
from app.models.books import JournalEntry
from app.models.kitchen import KitchenItem
from app.models.menu import Ingredient
from app.models.people import Attendance, Employee, LeaveRequest, PayrollRun
from app.models.sales import METHOD_LABELS, Order, Payment, Shift
from app.models.stock import Purchase, StockMove

router = APIRouter(prefix="/home", tags=["home"])


def _month_start(day: date) -> date:
    return day.replace(day=1)


def _change(now: int, before: int) -> int | None:
    """Percentage change, or None when there is nothing to compare with."""
    if not before:
        return None
    return round((now - before) / before * 100)


def _employee_for(db: Session, user: User) -> Employee | None:
    return db.scalar(select(Employee).where(Employee.user_id == user.id, Employee.is_active.is_(True)))


# --------------------------------------------------------------------------
# cashier: my till
# --------------------------------------------------------------------------

@router.get("/cashier")
def cashier_home(db: Session = Depends(get_db), user: User = Depends(requires("pos.use"))):
    """My till, my sales today, and the orders waiting at the counter."""
    from app.api.v1.sales import _open_shift, _shift_out

    today = _today()
    start, end = _day_bounds(today)

    shift = _open_shift(db, user)
    last_closed = None
    if not shift:
        closed = db.scalar(
            select(Shift).where(Shift.opened_by_id == user.id, Shift.closed_at.is_not(None))
            .order_by(Shift.closed_at.desc())
        )
        if closed:
            last_closed = {
                "closed_at": _local(closed.closed_at).strftime("%a %d %b, %H:%M"),
                "variance_ngwee": closed.variance_ngwee or 0,
            }

    mine = list(db.scalars(
        select(Order).where(
            Order.created_by == user.name, Order.created_at >= start, Order.created_at < end,
        ).order_by(Order.created_at.desc())
    ).all())
    paid = [o for o in mine if o.status == "paid"]
    open_orders = [o for o in mine if o.status == "open"]

    # Orders ready at the pass, for anyone at the counter: the kitchen has
    # finished them and someone has to call the name and hand them over.
    todays = list(db.scalars(
        select(Order).where(Order.created_at >= start, Order.created_at < end, Order.status == "paid")
        .order_by(Order.created_at)
    ).all())
    items = db.scalars(select(KitchenItem).where(KitchenItem.order_id.in_([o.id for o in todays]))).all() if todays else []
    by_order: dict[str, list[KitchenItem]] = defaultdict(list)
    for item in items:
        by_order[item.order_id].append(item)
    waiting = []
    preparing = 0
    for o in todays:
        state = kitchen_state(by_order.get(o.id, []), o)
        if state == "ready":
            waiting.append({
                "id": o.id, "number": o.number, "customer": o.customer_name or "Walk-in",
                "initials": _initials(o.customer_name or "Walk in"), "items": _items_text(o),
                "at": _local(o.created_at).strftime("%H:%M"),
            })
        elif state in ("received", "preparing"):
            preparing += 1

    employee = _employee_for(db, user)
    clocked = None
    if employee:
        row = db.scalar(
            select(Attendance).where(Attendance.employee_id == employee.id, Attendance.day == today)
            .order_by(Attendance.clock_in.desc())
        )
        clocked = {
            "linked": True,
            "in": bool(row and row.clock_out is None),
            "since": _local(row.clock_in).strftime("%H:%M") if row else None,
            "out_at": _local(row.clock_out).strftime("%H:%M") if row and row.clock_out else None,
        }

    return {
        "shift": _shift_out(db, shift, user).model_dump() if shift else None,
        "last_closed": last_closed,
        "my_orders": len(paid),
        "my_sales_ngwee": sum(o.total_ngwee for o in paid),
        "unpaid": [
            {"id": o.id, "number": o.number, "customer": o.customer_name or "Walk-in", "total_ngwee": o.total_ngwee}
            for o in open_orders[:5]
        ],
        "waiting": waiting[:8],
        "preparing": preparing,
        "recent": [
            {
                "id": o.id, "number": o.number, "customer": o.customer_name or "Walk-in",
                "items": _items_text(o), "at": _local(o.created_at).strftime("%H:%M"),
                "total_ngwee": o.total_ngwee, "status": o.status,
            }
            for o in mine[:6]
        ],
        "attendance": clocked,
    }


# --------------------------------------------------------------------------
# inventory: the store room
# --------------------------------------------------------------------------

@router.get("/stock")
def stock_home(
    db: Session = Depends(get_db),
    _: User = Depends(requires("inventory.view", "inventory.adjust", "purchases.manage")),
):
    """What is running out, what is on order, and what moved."""
    from app.api.v1.stock import levels

    # The same rows the Inventory screen shows, so the numbers always agree.
    rows = levels(low_only=False, db=db, _=None)
    value = sum(r.value_ngwee for r in rows if r.value_ngwee > 0)
    below_zero = sum(1 for r in rows if r.quantity_milli < 0)
    low = [
        {
            "name": r.name, "unit": r.unit, "on_hand_milli": r.quantity_milli,
            "reorder_milli": r.reorder_milli, "ratio": r.quantity_milli / r.reorder_milli,
        }
        for r in rows if r.is_low and r.reorder_milli > 0
    ]
    low.sort(key=lambda r: r["ratio"])

    on_order = list(db.scalars(
        select(Purchase).where(Purchase.status == "draft").order_by(Purchase.created_at)
    ).all())
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    received_week = db.scalar(
        select(func.count(Purchase.id)).where(Purchase.status == "received", Purchase.received_at >= week_ago)
    ) or 0

    names = {i.id: (i.name, i.unit) for i in db.scalars(select(Ingredient)).all()}
    moves = db.scalars(select(StockMove).order_by(StockMove.created_at.desc()).limit(8)).all()

    from app.api.v1.stock import owed as owed_rows
    owed = owed_rows(overdue_days=30, db=db, _=None)

    return {
        "value_ngwee": value,
        "ingredients": len(rows),
        "low_count": len(low),
        "below_zero": below_zero,
        "low": [{k: v for k, v in r.items() if k != "ratio"} for r in low[:8]],
        "on_order": [
            {
                "id": p.id, "number": p.number, "supplier": p.supplier.name,
                "total_ngwee": p.total_ngwee, "lines": len(p.lines),
                "days": (datetime.now(timezone.utc) - p.created_at).days,
            }
            for p in on_order[:6]
        ],
        "on_order_count": len(on_order),
        "received_week": received_week,
        "moves": [
            {
                "name": names.get(m.ingredient_id, ("?", ""))[0],
                "unit": names.get(m.ingredient_id, ("", ""))[1],
                "kind": m.kind, "quantity_milli": m.quantity_milli,
                "at": _local(m.created_at).strftime("%d %b %H:%M"),
                "by": m.created_by or "",
            }
            for m in moves
        ],
        "owed_ngwee": sum(r.owed_ngwee for r in owed),
        "overdue_ngwee": sum(r.overdue_ngwee for r in owed),
    }


# --------------------------------------------------------------------------
# accountant: the money
# --------------------------------------------------------------------------

@router.get("/money")
def money_home(
    db: Session = Depends(get_db),
    user: User = Depends(requires("books.view", "payroll.view", "reports.view")),
):
    """What came in, what is owed, and what is waiting for a decision."""
    codes = set(user.role.permission_codes)
    today = _today()
    start, end = _day_bounds(today)

    pays = db.scalars(select(Payment).where(Payment.status != "failed", Payment.created_at >= start, Payment.created_at < end)).all()
    by_method: dict[str, int] = defaultdict(int)
    for p in pays:
        by_method[p.method] += -p.amount_ngwee if p.is_refund else p.amount_ngwee
    takings = [
        {"method": m, "label": METHOD_LABELS.get(m, m.title()), "amount_ngwee": v}
        for m, v in sorted(by_method.items(), key=lambda kv: -kv[1]) if v
    ]

    # Month to date against the same number of days last month.
    m_start = _month_start(today)
    prev_start = _month_start(m_start - timedelta(days=1))
    days_in = (today - m_start).days + 1
    prev_cut = min(prev_start + timedelta(days=days_in), m_start)
    mtd = _paid_between(db, _day_bounds(m_start)[0], end)
    prev = _paid_between(db, _day_bounds(prev_start)[0], _day_bounds(prev_cut)[0])
    mtd_sales = sum(o.total_ngwee for o in mtd)
    prev_sales = sum(o.total_ngwee for o in prev)

    # Till counts this week: every closed till, with what it was out by.
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    shifts = db.scalars(
        select(Shift).where(Shift.closed_at.is_not(None), Shift.closed_at >= week_ago).order_by(Shift.closed_at.desc())
    ).all()
    tills = [
        {
            "who": s.opened_by, "closed": _local(s.closed_at).strftime("%a %d %b %H:%M"),
            "expected_ngwee": s.expected_ngwee or 0, "counted_ngwee": s.counted_ngwee or 0,
            "variance_ngwee": s.variance_ngwee or 0,
        }
        for s in shifts[:8]
    ]
    open_tills = db.scalar(select(func.count(Shift.id)).where(Shift.closed_at.is_(None))) or 0

    out: dict = {
        "takings": takings,
        "takings_ngwee": sum(t["amount_ngwee"] for t in takings),
        "mobile_ngwee": sum(v for m, v in by_method.items() if m in MOBILE),
        "mtd_sales_ngwee": mtd_sales,
        "mtd_change": _change(mtd_sales, prev_sales),
        "mtd_orders": len(mtd),
        "month_label": today.strftime("%B"),
        "tills": tills,
        "tills_short_ngwee": sum(t["variance_ngwee"] for t in tills if t["variance_ngwee"] < 0),
        "open_tills": open_tills,
        "books": None,
        "payroll": None,
        "owed": None,
    }

    if codes & {"books.view", "purchases.manage", "inventory.view"}:
        from app.api.v1.stock import owed as owed_rows
        rows = owed_rows(overdue_days=30, db=db, _=None)
        out["owed"] = {
            "total_ngwee": sum(r.owed_ngwee for r in rows),
            "overdue_ngwee": sum(r.overdue_ngwee for r in rows),
            "suppliers": [
                {"name": r.supplier_name, "owed_ngwee": r.owed_ngwee, "oldest_days": r.oldest_days}
                for r in rows[:5]
            ],
        }

    if "books.view" in codes:
        from app.api.v1.books import profit_and_loss, trial_balance
        month = today.strftime("%Y-%m")
        try:
            pl = profit_and_loss(month=month, db=db, _=user)
            tb = trial_balance(month=month, db=db, _=user)
            balanced = tb.get("balanced") if isinstance(tb, dict) else getattr(tb, "balanced", None)
        except Exception:
            pl, balanced = None, None
        drafts = db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.status == "draft")) or 0
        out["books"] = {
            "income_ngwee": pl["total_income_ngwee"] if pl else 0,
            "gross_margin_percent": pl["gross_margin_percent"] if pl else 0,
            "profit_ngwee": pl["profit_ngwee"] if pl else 0,
            "balanced": balanced,
            "drafts": drafts,
            "can_approve": "journal.approve" in codes,
        }

    if "payroll.view" in codes:
        latest = db.scalar(select(PayrollRun).order_by(PayrollRun.created_at.desc()))
        period = today.strftime("%Y-%m")
        this_month = db.scalar(select(PayrollRun).where(PayrollRun.period == period))
        out["payroll"] = {
            "period": period,
            "this_month": this_month.status if this_month else None,
            "latest": {
                "period": latest.period, "status": latest.status,
                "net_ngwee": latest.net_ngwee, "employer_cost_ngwee": latest.employer_cost_ngwee,
            } if latest else None,
            "can_approve": "payroll.approve" in codes,
        }
    return out


# --------------------------------------------------------------------------
# manager and owner: the team today, and the month
# --------------------------------------------------------------------------

@router.get("/team")
def team_home(
    db: Session = Depends(get_db),
    _: User = Depends(requires("hr.view", "attendance.manage")),
):
    """Who is on today, who is off, and what leave is waiting."""
    today = _today()
    employees = db.scalars(select(Employee).where(Employee.is_active.is_(True)).order_by(Employee.name)).all()
    rows = db.scalars(select(Attendance).where(Attendance.day == today)).all()
    latest: dict[str, Attendance] = {}
    for r in rows:
        if r.employee_id not in latest or r.clock_in > latest[r.employee_id].clock_in:
            latest[r.employee_id] = r

    on_leave_ids = set(db.scalars(
        select(LeaveRequest.employee_id).where(
            LeaveRequest.status == "approved", LeaveRequest.start <= today, LeaveRequest.end >= today,
        )
    ).all())
    pending = db.scalars(select(LeaveRequest).where(LeaveRequest.status == "pending").order_by(LeaveRequest.start)).all()
    names = {e.id: e.name for e in employees}

    on, done, off, leave = [], [], [], []
    for e in employees:
        r = latest.get(e.id)
        who = {"name": e.name, "job": e.job_title}
        if e.id in on_leave_ids:
            leave.append(who)
        elif r and r.clock_out is None:
            on.append({**who, "since": _local(r.clock_in).strftime("%H:%M")})
        elif r:
            done.append({**who, "since": _local(r.clock_in).strftime("%H:%M"), "until": _local(r.clock_out).strftime("%H:%M")})
        else:
            off.append(who)
    return {
        "staff": len(employees),
        "on": on, "done": done, "not_in": off, "on_leave": leave,
        "leave_pending": [
            {"name": names.get(l.employee_id, "?"), "kind": l.kind, "days": l.days,
             "from": l.start.strftime("%d %b"), "to": l.end.strftime("%d %b")}
            for l in pending[:5]
        ],
        "leave_pending_count": len(pending),
    }


@router.get("/month")
def month_home(
    db: Session = Depends(get_db),
    user: User = Depends(requires("reports.view", "books.view")),
):
    """The month so far, for the owner: sales against last month, the best
    day, and the profit when the books are kept."""
    today = _today()
    m_start = _month_start(today)
    prev_start = _month_start(m_start - timedelta(days=1))
    days_in = (today - m_start).days + 1
    prev_cut = min(prev_start + timedelta(days=days_in), m_start)
    end = _day_bounds(today)[1]

    mtd = _paid_between(db, _day_bounds(m_start)[0], end)
    prev = _paid_between(db, _day_bounds(prev_start)[0], _day_bounds(prev_cut)[0])
    by_day: dict[date, int] = defaultdict(int)
    for o in mtd:
        by_day[_local(o.paid_at).date()] += o.total_ngwee
    days = [m_start + timedelta(days=i) for i in range(days_in)]
    best = max(by_day.items(), key=lambda kv: kv[1]) if by_day else None

    sales = sum(o.total_ngwee for o in mtd)
    prev_sales = sum(o.total_ngwee for o in prev)
    out = {
        "month_label": today.strftime("%B %Y"),
        "days": days_in,
        "sales_ngwee": sales,
        "sales_change": _change(sales, prev_sales),
        "orders": len(mtd),
        "orders_change": _change(len(mtd), len(prev)),
        "daily_average_ngwee": round(sales / days_in) if days_in else 0,
        "by_day": [by_day.get(d, 0) for d in days],
        "best_day": {"day": best[0].strftime("%a %d %b"), "sales_ngwee": best[1]} if best else None,
        "profit": None,
    }
    if "books.view" in set(user.role.permission_codes):
        from app.api.v1.books import profit_and_loss
        try:
            pl = profit_and_loss(month=today.strftime("%Y-%m"), db=db, _=user)
            out["profit"] = {
                "income_ngwee": pl["total_income_ngwee"],
                "gross_margin_percent": pl["gross_margin_percent"],
                "profit_ngwee": pl["profit_ngwee"],
            }
        except Exception:
            pass
    return out


# --------------------------------------------------------------------------
# administrator: accounts, security, backups
# --------------------------------------------------------------------------

@router.get("/system")
def system_home(
    db: Session = Depends(get_db),
    _: User = Depends(requires("staff.manage", "settings.edit")),
):
    """Are the accounts, sign-ins, backups and server in order?"""
    from app.api.v1.settings_api import BACKUPS

    users = db.scalars(select(User)).all()
    roles = {r.id: r.label for r in db.scalars(select(Role)).all()}
    by_role: dict[str, int] = defaultdict(int)
    for u in users:
        if u.is_active:
            by_role[roles.get(u.role_id, u.role_id)] += 1

    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    attempts = db.scalars(select(LoginAttempt).where(LoginAttempt.at >= day_ago)).all()
    failed = [a for a in attempts if not a.succeeded]
    lock_from = now - timedelta(minutes=15)
    recent_fails: dict[str, int] = defaultdict(int)
    for a in failed:
        if a.at >= lock_from:
            recent_fails[a.email] += 1
    locked = sorted(e for e, n in recent_fails.items() if n >= 5)

    backup = None
    if BACKUPS.exists():
        dumps = sorted(BACKUPS.glob("*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
        if dumps:
            newest = dumps[0]
            made = datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc)
            backup = {
                "name": newest.name, "size_kb": round(newest.stat().st_size / 1024),
                "at": _local(made).strftime("%a %d %b %H:%M"),
                "age_hours": round((now - made).total_seconds() / 3600),
                "count": len(dumps),
            }

    # Sign-ins are counted above; listed here they would bury the changes.
    audit = db.scalars(
        select(AuditLog).where(AuditLog.action.not_in(["Signed in", "Signed out"]))
        .order_by(AuditLog.at.desc()).limit(8)
    ).all()
    return {
        "users_active": sum(1 for u in users if u.is_active),
        "users_disabled": sum(1 for u in users if not u.is_active),
        "must_change": sum(1 for u in users if u.is_active and u.must_change_password),
        "never_signed_in": sum(1 for u in users if u.is_active and not u.last_login_at),
        "by_role": [{"role": k, "count": v} for k, v in sorted(by_role.items(), key=lambda kv: -kv[1])],
        "sign_ins_24h": sum(1 for a in attempts if a.succeeded),
        "failed_24h": len(failed),
        "locked": locked,
        "backup": backup,
        "environment": settings.ENVIRONMENT,
        "activity": [
            {"at": _local(a.at).strftime("%d %b %H:%M"), "who": a.actor, "area": a.area, "action": a.action,
             "detail": a.detail}
            for a in audit
        ],
    }



# --------------------------------------------------------------------------
# what is waiting for this person to decide
# --------------------------------------------------------------------------

@router.get("/attention")
def attention(db: Session = Depends(get_db), user: User = Depends(requires(
    "payments.confirm", "cash.approve", "journal.approve", "leave.approve", "payroll.approve",
))):
    """Everything waiting on a decision this account is allowed to make, in
    one list, with where to go to make it. Only counts from real records."""
    from app.api.v1.sales import _shift_out
    from app.models.sales import CashMovement

    codes = set(user.role.permission_codes)
    items: list[dict] = []
    if "payments.confirm" in codes:
        rows = db.scalars(select(Payment).where(Payment.status == "pending", Payment.is_refund.is_(False))).all()
        if rows:
            items.append({"key": "payments", "count": len(rows), "amount_ngwee": sum(p.amount_ngwee for p in rows),
                          "text": "mobile money or card payment(s) not yet matched to a statement",
                          "to": "/payments", "level": "high" if len(rows) > 10 else "routine"})
    if "cash.approve" in codes:
        moves = db.scalars(select(CashMovement).where(CashMovement.status == "pending")).all()
        if moves:
            items.append({"key": "cash", "count": len(moves), "amount_ngwee": sum(m.amount_ngwee for m in moves),
                          "text": "cash drop(s) or petty cash to confirm", "to": "/end-of-day", "level": "routine"})
        since = datetime.now(timezone.utc) - timedelta(days=31)
        closed = db.scalars(select(Shift).where(Shift.closed_at.is_not(None), Shift.closed_at >= since,
                                                Shift.reviewed_by.is_(None))).all()
        review = [s_ for s_ in closed if _shift_out(db, s_, user).needs_review]
        if review:
            items.append({"key": "tills", "count": len(review),
                          "amount_ngwee": sum(abs(s_.variance_ngwee or 0) for s_ in review),
                          "text": "till count(s) out by more than the limit, to review", "to": "/end-of-day",
                          "level": "high"})
        still_open = db.scalars(select(Shift).where(
            Shift.closed_at.is_(None), Shift.opened_at < datetime.now(timezone.utc) - timedelta(hours=16))).all()
        if still_open:
            items.append({"key": "open_tills", "count": len(still_open), "amount_ngwee": 0,
                          "text": "till(s) left open since yesterday or earlier", "to": "/end-of-day", "level": "high"})
    if "journal.approve" in codes:
        n = db.scalar(select(func.count(JournalEntry.id)).where(JournalEntry.status == "draft")) or 0
        if n:
            items.append({"key": "journal", "count": n, "amount_ngwee": 0,
                          "text": "journal entr(ies) waiting for approval", "to": "/books/journal", "level": "routine"})
    if "leave.approve" in codes:
        n = db.scalar(select(func.count(LeaveRequest.id)).where(LeaveRequest.status == "pending")) or 0
        if n:
            items.append({"key": "leave", "count": n, "amount_ngwee": 0,
                          "text": "leave request(s) to decide", "to": "/people", "level": "routine"})
    if "payroll.approve" in codes:
        n = db.scalar(select(func.count(PayrollRun.id)).where(PayrollRun.status == "draft")) or 0
        if n:
            items.append({"key": "payroll", "count": n, "amount_ngwee": 0,
                          "text": "payroll run(s) waiting for approval", "to": "/payroll", "level": "high"})
    return {"items": items}
