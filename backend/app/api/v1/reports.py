"""Dashboards and reports.

Every report is built once as a table — headings and rows — and then either
returned as JSON for the screen or rendered as CSV, Excel or PDF. The numbers
on the screen and in the file are therefore the same numbers, because they come
from the same place.
"""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import User
from app.models.books import NORMAL_SIDE, Account, JournalEntry, JournalLine
from app.models.kitchen import KitchenItem
from app.models.menu import Ingredient
from app.models.people import Attendance, Employee, PayrollRun
from app.models.sales import METHOD_LABELS, Order, OrderLine, Payment
from app.models.stock import StockLevel, StockMove
from app.services.exports import render

router = APIRouter(prefix="/reports", tags=["reports"])

can_see = requires("reports.view", "books.view")
LUSAKA = timezone(timedelta(hours=2))
FORMATS = ("csv", "xlsx", "pdf")


def _range(days: int) -> tuple[datetime, datetime]:
    today = datetime.now(LUSAKA).date()
    start = datetime.combine(today - timedelta(days=days - 1), datetime.min.time(), tzinfo=LUSAKA)
    end = datetime.combine(today, datetime.max.time(), tzinfo=LUSAKA)
    return start, end


def money(ngwee: int) -> str:
    return f"{ngwee / 100:,.2f}"


# ---------------------------------------------------------------------------
# the dashboard
# ---------------------------------------------------------------------------

@router.get("/dashboard")
def dashboard(days: int = Query(default=7, ge=1, le=92), db: Session = Depends(get_db), _: User = Depends(can_see)):
    start, end = _range(days)
    paid = db.scalars(
        select(Order).where(Order.created_at >= start, Order.created_at <= end, Order.status == "paid")
    ).all()
    payments = db.scalars(select(Payment).where(Payment.created_at >= start, Payment.created_at <= end)).all()

    # Sales by day, with every day present so the chart has no gaps.
    by_day: dict[str, dict] = {}
    for offset in range(days):
        day = (datetime.now(LUSAKA).date() - timedelta(days=days - 1 - offset)).isoformat()
        by_day[day] = {"date": day, "orders": 0, "sales_ngwee": 0}
    for order in paid:
        key = order.created_at.astimezone(LUSAKA).date().isoformat()
        if key in by_day:
            by_day[key]["orders"] += 1
            by_day[key]["sales_ngwee"] += order.total_ngwee

    # Busiest hours, for rostering.
    hours = {h: 0 for h in range(24)}
    for order in paid:
        hours[order.created_at.astimezone(LUSAKA).hour] += order.total_ngwee

    # What sells.
    sold: dict[str, dict] = {}
    for line in db.scalars(
        select(OrderLine).join(Order, Order.id == OrderLine.order_id)
        .where(Order.created_at >= start, Order.created_at <= end, Order.status == "paid")
    ).all():
        row = sold.setdefault(line.product_name, {"name": line.product_name, "quantity": 0, "sales_ngwee": 0})
        row["quantity"] += line.quantity
        row["sales_ngwee"] += line.line_ngwee

    methods: dict[str, int] = {}
    refunds = 0
    for payment in payments:
        if payment.is_refund:
            refunds += payment.amount_ngwee
            continue
        methods[payment.method] = methods.get(payment.method, 0) + payment.amount_ngwee

    sales = sum(o.total_ngwee for o in paid)
    cost = -(db.scalar(
        select(func.coalesce(func.sum(StockMove.value_ngwee), 0))
        .where(StockMove.kind == "sale", StockMove.created_at >= start, StockMove.created_at <= end)
    ) or 0)

    # How long the kitchen took, from paid to ready.
    ready = db.scalars(
        select(KitchenItem).where(KitchenItem.ready_at.isnot(None), KitchenItem.created_at >= start)
    ).all()
    minutes = [
        (item.ready_at - item.created_at).total_seconds() / 60 for item in ready
    ]

    levels = db.scalars(select(StockLevel)).all()
    ingredients = {i.id: i for i in db.scalars(select(Ingredient)).all()}
    low = [
        ingredients[l.ingredient_id].name
        for l in levels
        if l.ingredient_id in ingredients and l.quantity_milli <= l.reorder_milli
    ]
    stock_value = sum(
        round(ingredients[l.ingredient_id].cost_ngwee * l.quantity_milli / 1000)
        for l in levels if l.ingredient_id in ingredients
    )

    return {
        "days": days,
        "orders": len(paid),
        "sales_ngwee": sales,
        "refunds_ngwee": refunds,
        "vat_ngwee": sum(o.vat_ngwee for o in paid),
        "food_cost_ngwee": cost,
        "gross_margin_percent": round((sales - cost) / sales * 100, 1) if sales else 0,
        "average_order_ngwee": round(sales / len(paid)) if paid else 0,
        "by_day": list(by_day.values()),
        "by_hour": [{"hour": h, "sales_ngwee": v} for h, v in hours.items() if v],
        "top_items": sorted(sold.values(), key=lambda r: r["sales_ngwee"], reverse=True)[:8],
        "by_method": [
            {"method": m, "label": METHOD_LABELS.get(m, m), "amount_ngwee": v}
            for m, v in sorted(methods.items(), key=lambda kv: -kv[1])
        ],
        "kitchen_minutes": round(sum(minutes) / len(minutes), 1) if minutes else None,
        "stock_value_ngwee": stock_value,
        "low_stock": low,
        "staff_on_now": db.scalar(select(func.count(Attendance.id)).where(Attendance.clock_out.is_(None))) or 0,
    }


# ---------------------------------------------------------------------------
# the reports themselves
# ---------------------------------------------------------------------------

def _sales_by_day(db: Session, days: int):
    start, end = _range(days)
    orders = db.scalars(
        select(Order).where(Order.created_at >= start, Order.created_at <= end, Order.status == "paid")
    ).all()
    grouped: dict[str, dict] = {}
    for order in orders:
        key = order.created_at.astimezone(LUSAKA).date().isoformat()
        row = grouped.setdefault(key, {"orders": 0, "sales": 0, "vat": 0})
        row["orders"] += 1
        row["sales"] += order.total_ngwee
        row["vat"] += order.vat_ngwee
    rows = [
        [day, r["orders"], money(r["sales"]), money(r["vat"]), money(round(r["sales"] / r["orders"]))]
        for day, r in sorted(grouped.items())
    ]
    total = sum(r["sales"] for r in grouped.values())
    rows.append(["Total", sum(r["orders"] for r in grouped.values()), money(total),
                 money(sum(r["vat"] for r in grouped.values())), ""])
    return ["Day", "Orders", "Sales (K)", "VAT inside (K)", "Average order (K)"], rows


def _item_sales(db: Session, days: int):
    start, end = _range(days)
    lines = db.scalars(
        select(OrderLine).join(Order, Order.id == OrderLine.order_id)
        .where(Order.created_at >= start, Order.created_at <= end, Order.status == "paid")
    ).all()
    grouped: dict[str, dict] = {}
    for line in lines:
        row = grouped.setdefault(line.product_code, {"name": line.product_name, "qty": 0, "sales": 0})
        row["qty"] += line.quantity
        row["sales"] += line.line_ngwee
    rows = [
        [code, r["name"], r["qty"], money(r["sales"])]
        for code, r in sorted(grouped.items(), key=lambda kv: -kv[1]["sales"])
    ]
    rows.append(["", "Total", sum(r["qty"] for r in grouped.values()),
                 money(sum(r["sales"] for r in grouped.values()))])
    return ["Code", "Item", "Sold", "Sales (K)"], rows


def _payment_methods(db: Session, days: int):
    start, end = _range(days)
    payments = db.scalars(select(Payment).where(Payment.created_at >= start, Payment.created_at <= end)).all()
    grouped: dict[str, dict] = {}
    for payment in payments:
        row = grouped.setdefault(payment.method, {"count": 0, "taken": 0, "refunded": 0})
        if payment.is_refund:
            row["refunded"] += payment.amount_ngwee
        else:
            row["count"] += 1
            row["taken"] += payment.amount_ngwee
    rows = [
        [METHOD_LABELS.get(m, m), r["count"], money(r["taken"]), money(r["refunded"]),
         money(r["taken"] - r["refunded"])]
        for m, r in sorted(grouped.items(), key=lambda kv: -kv[1]["taken"])
    ]
    rows.append(["Total", sum(r["count"] for r in grouped.values()),
                 money(sum(r["taken"] for r in grouped.values())),
                 money(sum(r["refunded"] for r in grouped.values())),
                 money(sum(r["taken"] - r["refunded"] for r in grouped.values()))])
    return ["Method", "Payments", "Taken (K)", "Refunded (K)", "Net (K)"], rows


def _stock_report(db: Session, days: int):
    levels = {l.ingredient_id: l for l in db.scalars(select(StockLevel)).all()}
    rows = []
    total = 0
    for item in db.scalars(select(Ingredient).where(Ingredient.is_active.is_(True)).order_by(Ingredient.name)).all():
        level = levels.get(item.id)
        quantity = level.quantity_milli if level else 0
        reorder = level.reorder_milli if level else 0
        value = round(item.cost_ngwee * quantity / 1000)
        total += value
        unit = "g" if item.unit == "kg" else "ml" if item.unit == "l" else item.unit
        shown = f"{quantity} {unit}" if item.unit in ("kg", "l") else f"{quantity / 1000:g}"
        rows.append([
            item.name, shown, f"{reorder}" if reorder else "",
            money(item.cost_ngwee), money(value),
            "order more" if quantity <= reorder else "",
        ])
    rows.append(["Total", "", "", "", money(total), ""])
    return ["Ingredient", "On hand", "Reorder at", f"Cost per unit (K)", "Value (K)", ""], rows


def _stock_moves(db: Session, days: int):
    start, _ = _range(days)
    names = {i.id: i for i in db.scalars(select(Ingredient)).all()}
    rows = []
    for move in db.scalars(
        select(StockMove).where(StockMove.created_at >= start).order_by(StockMove.created_at.desc())
    ).all():
        item = names.get(move.ingredient_id)
        rows.append([
            move.created_at.astimezone(LUSAKA).strftime("%d %b %H:%M"),
            item.name if item else "(removed)", move.kind,
            f"{move.quantity_milli:+}", f"{move.balance_milli}",
            move.reference or move.note, move.created_by or "",
        ])
    return ["When", "Ingredient", "What", "Change", "Left", "Reference", "By"], rows


def _staff_hours(db: Session, days: int):
    start, end = _range(days)
    names = {e.id: e for e in db.scalars(select(Employee)).all()}
    grouped: dict[str, dict] = {}
    for row in db.scalars(
        select(Attendance).where(Attendance.clock_in >= start, Attendance.clock_in <= end)
    ).all():
        employee = names.get(row.employee_id)
        if not employee:
            continue
        entry = grouped.setdefault(employee.id, {"name": employee.name, "job": employee.job_title, "days": set(), "hours": 0.0})
        entry["days"].add(row.day)
        if row.clock_out:
            entry["hours"] += (row.clock_out - row.clock_in).total_seconds() / 3600
    rows = [
        [r["name"], r["job"], len(r["days"]), f"{r['hours']:.1f}",
         f"{r['hours'] / len(r['days']):.1f}" if r["days"] else "0"]
        for r in sorted(grouped.values(), key=lambda r: r["name"])
    ]
    return ["Employee", "Job", "Days worked", "Hours", "Average a day"], rows


def _payroll_report(db: Session, days: int):
    rows = []
    for run in db.scalars(select(PayrollRun).order_by(PayrollRun.period.desc())).all():
        for slip in sorted(run.payslips, key=lambda p: p.employee_name):
            rows.append([
                run.period, slip.employee_number, slip.employee_name, slip.job_title,
                money(slip.gross_ngwee), money(slip.paye_ngwee),
                money(slip.napsa_employee_ngwee), money(slip.nhima_employee_ngwee),
                money(slip.net_ngwee), run.status,
            ])
    return ["Month", "Number", "Employee", "Job", "Gross (K)", "PAYE (K)", "NAPSA (K)", "NHIMA (K)", "Net (K)", "State"], rows


def _trial_balance(db: Session, days: int):
    raw = db.execute(
        select(JournalLine.account_id,
               func.coalesce(func.sum(JournalLine.debit_ngwee), 0),
               func.coalesce(func.sum(JournalLine.credit_ngwee), 0))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalEntry.status == "posted")
        .group_by(JournalLine.account_id)
    ).all()
    accounts = {a.id: a for a in db.scalars(select(Account)).all()}
    rows = []
    total_debit = total_credit = 0
    for account_id, debit, credit in raw:
        account = accounts.get(account_id)
        if not account:
            continue
        net = debit - credit
        d, c = (net, 0) if net > 0 else (0, -net)
        if not d and not c:
            continue
        total_debit += d
        total_credit += c
        rows.append([account.code, account.name, money(d) if d else "", money(c) if c else ""])
    rows.sort(key=lambda r: r[0])
    rows.append(["", "Totals", money(total_debit), money(total_credit)])
    return ["Code", "Account", "Debit (K)", "Credit (K)"], rows


def _vat_report(db: Session, days: int):
    """What was collected inside prices, for the ZRA return."""
    start, end = _range(days)
    orders = db.scalars(
        select(Order).where(Order.created_at >= start, Order.created_at <= end, Order.status == "paid")
    ).all()
    grouped: dict[str, dict] = {}
    for order in orders:
        key = order.created_at.astimezone(LUSAKA).strftime("%Y-%m")
        row = grouped.setdefault(key, {"gross": 0, "vat": 0, "orders": 0})
        row["gross"] += order.total_ngwee
        row["vat"] += order.vat_ngwee
        row["orders"] += 1
    rows = [
        [month, r["orders"], money(r["gross"] - r["vat"]), money(r["vat"]), money(r["gross"])]
        for month, r in sorted(grouped.items())
    ]
    rows.append(["Total", sum(r["orders"] for r in grouped.values()),
                 money(sum(r["gross"] - r["vat"] for r in grouped.values())),
                 money(sum(r["vat"] for r in grouped.values())),
                 money(sum(r["gross"] for r in grouped.values()))])
    return ["Month", "Orders", "Sales before VAT (K)", "VAT (K)", "Total (K)"], rows


REPORTS = {
    "sales-by-day": ("Sales by day", _sales_by_day, "reports.view"),
    "item-sales": ("What sells", _item_sales, "reports.view"),
    "payment-methods": ("How people paid", _payment_methods, "reports.view"),
    "stock-on-hand": ("Stock on hand", _stock_report, "inventory.view"),
    "stock-movements": ("Stock movements", _stock_moves, "inventory.view"),
    "staff-hours": ("Hours worked", _staff_hours, "hr.view"),
    "payroll": ("Payroll", _payroll_report, "payroll.view"),
    "trial-balance": ("Trial balance", _trial_balance, "books.view"),
    "vat": ("VAT collected", _vat_report, "books.view"),
}


@router.get("/list")
def list_reports(_: User = Depends(can_see)):
    return [
        {"id": key, "name": name, "permission": permission}
        for key, (name, _builder, permission) in REPORTS.items()
    ]


def _check(user: User, permission: str) -> None:
    allowed = set(user.role.permission_codes)
    if permission not in allowed and "reports.view" not in allowed:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"{user.role.label} accounts cannot see this report.")


@router.get("/{report_id}")
def report(
    report_id: str, days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db), user: User = Depends(can_see),
):
    if report_id not in REPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report.")
    name, builder, permission = REPORTS[report_id]
    _check(user, permission)
    headings, rows = builder(db, days)
    return {"id": report_id, "name": name, "days": days, "headings": headings, "rows": rows}


@router.get("/{report_id}/download")
def download(
    report_id: str, fmt: str = Query(default="pdf"), days: int = Query(default=30, ge=1, le=366),
    db: Session = Depends(get_db), user: User = Depends(can_see),
):
    if report_id not in REPORTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such report.")
    if fmt not in FORMATS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose csv, xlsx or pdf.")
    name, builder, permission = REPORTS[report_id]
    _check(user, permission)
    headings, rows = builder(db, days)
    note = f"The last {days} days." if report_id not in ("stock-on-hand", "trial-balance", "payroll") else ""
    content, media, filename = render(fmt, headings, rows, name, note)
    return Response(
        content=content, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
