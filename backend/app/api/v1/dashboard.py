"""The screens the demo has under Today, Money and Business.

Overview, Payments, End of day and Sales analytics all read the same few
tables - orders, payments, the kitchen board and the stock levels - and add
them up the way the demo's screens show them. Nothing here writes money; that
stays with the till.

Promotions and Feedback are here too, because they are small and the demo
puts them beside the others.

Every time is Lusaka time. A trading day runs midnight to midnight at UTC+2,
which is how the restaurant counts its day, not how the server's clock does.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import Setting, User
from app.models.business import FEEDBACK_SOURCES, PROMO_KINDS, Feedback, Promotion
from app.models.kitchen import KitchenItem
from app.models.menu import Ingredient
from app.models.sales import METHOD_LABELS, Order, OrderLine, OrderLineOption, Payment, Shift
from app.models.stock import StockLevel, StockMove
from app.services.audit import record

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

can_look = requires("pos.use", "orders.view", "reports.view", "books.view", "kitchen.view")
can_report = requires("reports.view", "books.view", "pos.use")
can_analyse = requires("reports.view", "books.view")
can_promote = requires("promos.manage")
can_feedback = requires("feedback.view", "pos.use")

LUSAKA = timezone(timedelta(hours=2))

# How the demo groups payment methods on its charts.
MOBILE = ("airtel", "mtn", "zamtel")


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=LUSAKA)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _today() -> date:
    return datetime.now(LUSAKA).date()


def _setting(db: Session, key: str, fallback: str) -> str:
    row = db.get(Setting, key)
    return row.value if row and row.value else fallback


def _local(when: datetime | None) -> datetime | None:
    if when is None:
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(LUSAKA)


def _paid_between(db: Session, start: datetime, end: datetime) -> list[Order]:
    return list(db.scalars(
        select(Order).where(Order.status == "paid", Order.paid_at >= start, Order.paid_at < end)
    ).all())


def _change(now: float, before: float) -> int | None:
    """Percentage change, or None when there is nothing to compare against."""
    if not before:
        return None
    return round((now - before) / before * 100)


def kitchen_state(items: list[KitchenItem], order: Order) -> str:
    """Where an order stands, in the demo's words, from its kitchen tickets."""
    if order.status == "cancelled":
        return "cancelled"
    if order.status == "open":
        return "awaiting_payment"
    if not items:
        return "collected"
    states = {i.status for i in items}
    if states == {"served"}:
        return "collected"
    if states <= {"ready", "served"}:
        return "ready"
    if "preparing" in states or "ready" in states:
        return "preparing"
    return "received"


STATE_LABELS = {
    "awaiting_payment": "Awaiting payment",
    "received": "Received",
    "preparing": "Preparing",
    "ready": "Ready for pickup",
    "collected": "Collected",
    "cancelled": "Cancelled",
}


def _items_text(order: Order) -> str:
    return ", ".join(f"{line.quantity}× {line.product_name}" for line in order.lines)


def _initials(name: str) -> str:
    parts = [p for p in (name or "").replace(".", " ").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "—"


# ---------------------------------------------------------------------------
# the service line in the top bar
# ---------------------------------------------------------------------------

@router.get("/service")
def service(db: Session = Depends(get_db), _: User = Depends(can_look)):
    """How long a customer is told to wait: base time plus 2 minutes an order."""
    base = int(_setting(db, "service.prep_minutes", "12") or 12)
    # Today's tickets only. A ticket from yesterday that nobody cleared is not
    # food anyone is waiting for, and counting it would quote a customer an
    # hour's wait on a quiet morning.
    # And within today, only the last two hours: an order that has sat for
    # longer was handed over and nobody tapped it. Counting those quoted a
    # wait of hours on a busy day's evening.
    start, _ = _day_bounds(_today())
    start = max(start, datetime.now(timezone.utc) - timedelta(hours=2))
    in_kitchen = db.scalar(
        select(func.count(func.distinct(KitchenItem.order_id))).where(
            KitchenItem.status.in_(("waiting", "preparing")),
            KitchenItem.created_at >= start,
        )
    ) or 0
    return {"prep_minutes": base, "in_kitchen": in_kitchen, "wait_minutes": base + 2 * in_kitchen}


class PrepIn(BaseModel):
    minutes: int = Field(ge=1, le=120)


@router.post("/service/prep")
def set_prep(body: PrepIn, db: Session = Depends(get_db),
             user: User = Depends(requires("service.control", "settings.edit"))):
    """The − and + on the Overview: the base preparation time."""
    row = db.get(Setting, "service.prep_minutes")
    if row:
        row.value = str(body.minutes)
    else:
        db.add(Setting(key="service.prep_minutes", value=str(body.minutes), label="Base preparation time (minutes)"))
    record(db, user.name, "settings", "Preparation time changed", f"{body.minutes} minutes", "service.prep_minutes")
    db.commit()
    return service(db, user)


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("/overview")
def overview(db: Session = Depends(get_db), _: User = Depends(can_look)):
    """Everything on the demo's Overview, worked out from the real tables."""
    today = _today()
    start, end = _day_bounds(today)
    y_start, y_end = _day_bounds(today - timedelta(days=1))
    # "vs same time yesterday": yesterday up to the same minute as now.
    now_utc = datetime.now(timezone.utc)
    y_cut = now_utc - timedelta(days=1)

    paid_today = _paid_between(db, start, end)
    paid_y_sofar = _paid_between(db, y_start, min(y_cut, y_end))
    paid_y = _paid_between(db, y_start, y_end)

    sales = sum(o.total_ngwee for o in paid_today)
    sales_y = sum(o.total_ngwee for o in paid_y_sofar)
    count = len(paid_today)
    count_y = len(paid_y_sofar)
    avg = round(sales / count) if count else 0
    avg_y = round(sales_y / count_y) if count_y else 0

    # Sales by hour, 08:00 to 19:00, today against all of yesterday.
    hours = list(range(8, 20))
    by_hour_today = {h: 0 for h in hours}
    by_hour_y = {h: 0 for h in hours}
    for o in paid_today:
        h = _local(o.paid_at).hour
        if h in by_hour_today:
            by_hour_today[h] += o.total_ngwee
    for o in paid_y:
        h = _local(o.paid_at).hour
        if h in by_hour_y:
            by_hour_y[h] += o.total_ngwee

    # The kitchen, order by order.
    live_items = db.scalars(
        select(KitchenItem).where(KitchenItem.created_at >= start - timedelta(hours=6))
    ).all()
    by_order: dict[str, list[KitchenItem]] = defaultdict(list)
    for item in live_items:
        by_order[item.order_id].append(item)

    todays_orders = list(db.scalars(
        select(Order).where(Order.created_at >= start, Order.created_at < end).order_by(Order.created_at.desc())
    ).all())
    pipeline = Counter()
    for o in todays_orders:
        pipeline[kitchen_state(by_order.get(o.id, []), o)] += 1
    in_kitchen = pipeline["received"] + pipeline["preparing"] + pipeline["ready"]

    # How customers paid today: mobile money, card, cash.
    pays = db.scalars(
        select(Payment).where(Payment.status != "failed", Payment.created_at >= start, Payment.created_at < end, Payment.is_refund.is_(False))
    ).all()
    mix = {"mobile": 0, "card": 0, "cash": 0, "account": 0}
    for p in pays:
        if p.method in MOBILE:
            mix["mobile"] += p.amount_ngwee
        elif p.method in mix:
            mix[p.method] += p.amount_ngwee
    collected = sum(mix.values())

    latest = [
        {
            "id": o.id, "number": o.number,
            "customer": o.customer_name or "Walk-in",
            "initials": _initials(o.customer_name or "Walk in"),
            "items": _items_text(o),
            "at": _local(o.created_at).strftime("%H:%M"),
            "total_ngwee": o.total_ngwee,
            "state": kitchen_state(by_order.get(o.id, []), o),
        }
        for o in todays_orders[:6]
    ]
    for row in latest:
        row["state_label"] = STATE_LABELS[row["state"]]

    sellers = Counter()
    for o in paid_today:
        for line in o.lines:
            sellers[line.product_name] += line.quantity
    best = [{"name": n, "sold": q} for n, q in sellers.most_common(5)]

    alerts = []
    for level, ingredient in db.execute(
        select(StockLevel, Ingredient).join(Ingredient, Ingredient.id == StockLevel.ingredient_id)
        .where(StockLevel.reorder_milli > 0, StockLevel.quantity_milli < StockLevel.reorder_milli)
        .order_by((StockLevel.quantity_milli * 1.0 / StockLevel.reorder_milli))
    ).all()[:5]:
        alerts.append({
            "name": ingredient.name, "unit": ingredient.unit,
            "on_hand_milli": level.quantity_milli, "reorder_milli": level.reorder_milli,
        })

    ratings = db.scalars(select(Feedback).order_by(Feedback.created_at.desc())).all()
    rating = {
        "average": round(sum(f.rating for f in ratings) / len(ratings), 1) if ratings else None,
        "count": len(ratings),
        "latest": ratings[0].comment if ratings and ratings[0].comment else "",
    }

    # Small trend lines under the KPIs: the last seven days, oldest first.
    spark_sales, spark_count, spark_avg = [], [], []
    for back in range(6, -1, -1):
        d_start, d_end = _day_bounds(today - timedelta(days=back))
        day = _paid_between(db, d_start, d_end)
        total = sum(o.total_ngwee for o in day)
        spark_sales.append(total)
        spark_count.append(len(day))
        spark_avg.append(round(total / len(day)) if day else 0)

    base = int(_setting(db, "service.prep_minutes", "12") or 12)
    return {
        "date": today.isoformat(),
        "sales_ngwee": sales, "sales_change": _change(sales, sales_y),
        "paid_orders": count, "orders_change": _change(count, count_y),
        "average_ngwee": avg, "average_change": _change(avg, avg_y),
        "in_kitchen": in_kitchen, "ready": pipeline["ready"],
        "spark": {"sales": spark_sales, "orders": spark_count, "average": spark_avg},
        "hours": hours,
        "by_hour_today": [by_hour_today[h] for h in hours],
        "by_hour_yesterday": [by_hour_y[h] for h in hours],
        "pipeline": {k: pipeline[k] for k in ("awaiting_payment", "received", "preparing", "ready")},
        "mix": mix, "collected_ngwee": collected,
        "latest": latest, "best_sellers": best, "stock_alerts": alerts, "rating": rating,
        "prep_minutes": base, "wait_minutes": base + 2 * (pipeline["received"] + pipeline["preparing"]),
    }


# ---------------------------------------------------------------------------
# Orders, as the demo's Orders screen lists them
# ---------------------------------------------------------------------------

@router.get("/orders")
def orders_board(
    view: str = Query(default="active", max_length=16),
    q: str = Query(default="", max_length=60),
    db: Session = Depends(get_db),
    _: User = Depends(can_look),
):
    """Active, All today, Collected, Cancelled or Last 14 days."""
    today = _today()
    start, end = _day_bounds(today)
    stmt = select(Order).order_by(Order.created_at.desc())
    if view == "days14":
        stmt = stmt.where(Order.created_at >= _day_bounds(today - timedelta(days=13))[0]).limit(400)
    else:
        stmt = stmt.where(Order.created_at >= start, Order.created_at < end).limit(300)
    term = q.strip()
    if term:
        like = f"%{term}%"
        stmt = select(Order).where(
            (Order.number.ilike(like)) | (Order.customer_name.ilike(like)) | (Order.customer_phone.ilike(like))
        ).order_by(Order.created_at.desc()).limit(100)
    found = list(db.scalars(stmt).all())

    items = db.scalars(select(KitchenItem).where(KitchenItem.order_id.in_([o.id for o in found] or [""]))).all()
    by_order: dict[str, list[KitchenItem]] = defaultdict(list)
    for item in items:
        by_order[item.order_id].append(item)

    rows = []
    for o in found:
        state = kitchen_state(by_order.get(o.id, []), o)
        if not term:
            if view == "active" and state not in ("awaiting_payment", "received", "preparing", "ready"):
                continue
            if view == "collected" and state != "collected":
                continue
            if view == "cancelled" and state != "cancelled":
                continue
        methods = sorted({METHOD_LABELS.get(p.method, p.method) for p in o.payments if not p.is_refund})
        rows.append({
            "id": o.id, "number": o.number,
            "placed": _local(o.created_at).strftime("%H:%M" if view != "days14" and not term else "%d %b %H:%M"),
            "customer": o.customer_name or "Walk-in", "phone": o.customer_phone,
            "items": _items_text(o), "total_ngwee": o.total_ngwee,
            "payment": ", ".join(methods) if methods else ("Not paid" if o.status == "open" else "—"),
            "paid": o.status == "paid",
            "state": state, "state_label": STATE_LABELS[state],
            "order_type": o.order_type,
        })
    return rows


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

@router.get("/payments")
def payments(
    method: str = Query(default="", max_length=16),
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    _: User = Depends(can_report),
):
    """Every payment and refund, to match against the operators' statements."""
    since = _day_bounds(_today() - timedelta(days=days - 1))[0]
    stmt = select(Payment).where(Payment.status != "failed", Payment.created_at >= since).order_by(Payment.created_at.desc())
    rows = list(db.scalars(stmt).all())

    collected = sum(p.amount_ngwee for p in rows if not p.is_refund)
    refunded = sum(p.amount_ngwee for p in rows if p.is_refund)
    count = sum(1 for p in rows if not p.is_refund)
    by_method = Counter()
    for p in rows:
        if not p.is_refund:
            by_method[p.method] += p.amount_ngwee

    if method == "refunds":
        rows = [p for p in rows if p.is_refund]
    elif method == "mobile":
        rows = [p for p in rows if p.method in MOBILE]
    elif method:
        rows = [p for p in rows if p.method == method]

    # Mobile money and card payments need the operator's reference to be
    # matched later. One without it is what "needs attention" means here.
    attention = [p for p in rows if p.method in (*MOBILE, "card") and not p.reference and not p.is_refund]
    if method == "attention":
        rows = attention

    return {
        "collected_ngwee": collected, "refunded_ngwee": refunded, "net_ngwee": collected - refunded,
        "count": count, "needs_attention": len(attention),
        "by_method": {k: by_method[k] for k in ("airtel", "mtn", "zamtel", "card", "cash", "account")},
        "rows": [
            {
                "id": p.id,
                "when": _local(p.created_at).strftime("%d %b, %H:%M"),
                "order": p.order.number if p.order else "",
                "method": METHOD_LABELS.get(p.method, p.method),
                "method_code": p.method,
                "amount_ngwee": p.amount_ngwee,
                "reference": p.reference,
                "by": p.created_by or "",
                "refund": p.is_refund,
                "status": "Refund" if p.is_refund else (
                    "Needs reference" if p in attention else "Received"
                ),
            }
            for p in rows[:400]
        ],
    }


# ---------------------------------------------------------------------------
# End of day
# ---------------------------------------------------------------------------

@router.get("/end-of-day")
def end_of_day(
    day: date | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(can_report),
):
    """The cash-up and sales summary for one trading day."""
    day = day or _today()
    start, end = _day_bounds(day)

    pays = db.scalars(select(Payment).where(Payment.status != "failed", Payment.created_at >= start, Payment.created_at < end)).all()
    taken = Counter()
    refunds = 0
    for p in pays:
        if p.is_refund:
            refunds += p.amount_ngwee
        else:
            taken[p.method] += p.amount_ngwee

    day_orders = db.scalars(select(Order).where(Order.created_at >= start, Order.created_at < end)).all()
    paid = [o for o in day_orders if o.status == "paid"]
    cancelled = [o for o in day_orders if o.status == "cancelled"]
    still_open = [o for o in day_orders if o.status == "open"]
    discounts = sum(o.discount_ngwee for o in paid)
    gross = sum(o.total_ngwee for o in paid)

    sold: dict[str, dict] = {}
    for o in paid:
        for line in o.lines:
            row = sold.setdefault(line.product_name, {"name": line.product_name, "qty": 0, "sales_ngwee": 0})
            row["qty"] += line.quantity
            row["sales_ngwee"] += line.line_ngwee
    items = sorted(sold.values(), key=lambda r: -r["sales_ngwee"])

    waste = []
    for move, ingredient in db.execute(
        select(StockMove, Ingredient).join(Ingredient, Ingredient.id == StockMove.ingredient_id)
        .where(StockMove.kind == "waste", StockMove.created_at >= start, StockMove.created_at < end)
    ).all():
        waste.append({
            "name": ingredient.name, "unit": ingredient.unit,
            "quantity_milli": abs(move.quantity_milli), "cost_ngwee": abs(move.value_ngwee),
            "note": move.note,
        })

    shifts = [
        {
            "opened_by": s.opened_by, "closed_by": s.closed_by or "",
            "opened": _local(s.opened_at).strftime("%H:%M"),
            "closed": _local(s.closed_at).strftime("%H:%M") if s.closed_at else "",
            "float_ngwee": s.float_ngwee, "expected_ngwee": s.expected_ngwee,
            "counted_ngwee": s.counted_ngwee, "variance_ngwee": s.variance_ngwee,
        }
        for s in db.scalars(select(Shift).where(Shift.opened_at >= start, Shift.opened_at < end)).all()
    ]

    return {
        "date": day.isoformat(),
        "title": datetime.combine(day, time.min).strftime("%A, %d %B %Y"),
        "mobile_ngwee": sum(taken[m] for m in MOBILE),
        "airtel_ngwee": taken["airtel"], "mtn_ngwee": taken["mtn"], "zamtel_ngwee": taken["zamtel"],
        "card_ngwee": taken["card"], "cash_ngwee": taken["cash"], "account_ngwee": taken["account"],
        "refunds_ngwee": refunds, "discounts_ngwee": discounts,
        "net_ngwee": gross - refunds,
        "paid_orders": len(paid), "cancelled": len(cancelled), "still_open": len(still_open),
        "items": items, "waste": waste, "shifts": shifts,
    }


# ---------------------------------------------------------------------------
# Sales analytics
# ---------------------------------------------------------------------------

@router.get("/analytics")
def analytics(
    days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    _: User = Depends(can_analyse),
):
    """The demo's Sales analytics, from the real orders."""
    today = _today()
    since = _day_bounds(today - timedelta(days=days - 1))[0]
    until = _day_bounds(today)[1]
    paid = _paid_between(db, since, until)
    lost = db.scalar(
        select(func.count(Order.id)).where(
            Order.status == "cancelled", Order.created_at >= since, Order.created_at < until,
        )
    ) or 0

    sales = sum(o.total_ngwee for o in paid)

    # The period before, of the same length, for the comparison under each
    # figure: 14 days are compared with the 14 days before them.
    prev_since = _day_bounds(today - timedelta(days=2 * days - 1))[0]
    prev_paid = _paid_between(db, prev_since, since)
    prev_sales = sum(o.total_ngwee for o in prev_paid)
    prev_lost = db.scalar(
        select(func.count(Order.id)).where(
            Order.status == "cancelled", Order.created_at >= prev_since, Order.created_at < since,
        )
    ) or 0
    prev_average = round(prev_sales / len(prev_paid)) if prev_paid else 0
    average = round(sales / len(paid)) if paid else 0
    previous = {
        "sales_ngwee": prev_sales, "paid_orders": len(prev_paid),
        "average_ngwee": prev_average, "lost_orders": prev_lost,
        "sales_change": _change(sales, prev_sales),
        "orders_change": _change(len(paid), len(prev_paid)),
        "average_change": _change(average, prev_average),
        "lost_change": _change(lost, prev_lost),
    }

    per_day = Counter()
    for o in paid:
        per_day[_local(o.paid_at).date()] += o.total_ngwee
    daily = []
    for back in range(days - 1, -1, -1):
        d = today - timedelta(days=back)
        daily.append({"date": d.isoformat(), "label": d.strftime("%d %b"), "sales_ngwee": per_day[d]})

    mix = {"mobile": 0, "card": 0, "cash": 0, "account": 0}
    for p in db.scalars(select(Payment).where(Payment.status != "failed", Payment.created_at >= since, Payment.is_refund.is_(False))).all():
        if p.method in MOBILE:
            mix["mobile"] += p.amount_ngwee
        elif p.method in mix:
            mix[p.method] += p.amount_ngwee

    # When customers order: weekday by hour, 08:00 to 19:00.
    hours = list(range(8, 20))
    heat = [[0 for _ in hours] for _ in range(7)]  # Sunday first, as the demo shows
    for o in paid:
        local = _local(o.paid_at)
        if local.hour in hours:
            heat[(local.weekday() + 1) % 7][hours.index(local.hour)] += 1
    busiest = None
    peak = max((max(r) for r in heat), default=0)
    if peak:
        for wd, row in enumerate(heat):
            if peak in row:
                busiest = {"day": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][wd],
                           "hour": f"{hours[row.index(peak)]:02d}:00"}
                break

    sellers: dict[str, dict] = {}
    for o in paid:
        for line in o.lines:
            row = sellers.setdefault(line.product_name, {"name": line.product_name, "sold": 0, "sales_ngwee": 0})
            row["sold"] += line.quantity
            row["sales_ngwee"] += line.line_ngwee
    best = sorted(sellers.values(), key=lambda r: -r["sold"])[:12]

    # Most picked choices, for prep planning. Every option group counts except
    # sizes, which say nothing about what to chop in the morning.
    picks = Counter()
    order_ids = [o.id for o in paid]
    if order_ids:
        for option in db.scalars(
            select(OrderLineOption)
            .join(OrderLine, OrderLine.id == OrderLineOption.line_id)
            .where(OrderLine.order_id.in_(order_ids))
        ).all():
            if option.group_name.lower() in ("size", "sizes"):
                continue
            picks[option.item_name] += 1
    toppings = [{"name": n, "count": c} for n, c in picks.most_common(10)]

    return {
        "days": days,
        "sales_ngwee": sales, "paid_orders": len(paid),
        "per_day": round(len(paid) / days, 1),
        "average_ngwee": round(sales / len(paid)) if paid else 0,
        "lost_orders": lost,
        "previous": previous,
        "daily": daily, "mix": mix,
        "hours": hours, "heat": heat, "busiest": busiest,
        "best_sellers": best, "toppings": toppings,
    }


# ---------------------------------------------------------------------------
# Promotions
# ---------------------------------------------------------------------------

class PromoIn(BaseModel):
    code: str = Field(min_length=3, max_length=24)
    label: str = Field(default="", max_length=120)
    kind: str = Field(default="percent", max_length=10)
    value: int = Field(gt=0, le=100_000_000)
    minimum_ngwee: int = Field(default=0, ge=0, le=100_000_000)


def _promo_out(p: Promotion) -> dict:
    return {
        "id": p.id, "code": p.code, "label": p.label, "kind": p.kind, "value": p.value,
        "minimum_ngwee": p.minimum_ngwee, "is_active": p.is_active, "uses": p.uses,
        "discount_given_ngwee": p.discount_given_ngwee,
        "summary": (f"{p.value}% off" if p.kind == "percent" else f"K{p.value / 100:,.0f} off")
        + (f", orders over K{p.minimum_ngwee / 100:,.0f}" if p.minimum_ngwee else ""),
    }


@router.get("/promotions")
def promotions(db: Session = Depends(get_db), _: User = Depends(requires("promos.manage", "pos.use"))):
    return [_promo_out(p) for p in db.scalars(select(Promotion).order_by(Promotion.is_active.desc(), Promotion.created_at.desc())).all()]


@router.post("/promotions", status_code=status.HTTP_201_CREATED)
def add_promotion(body: PromoIn, db: Session = Depends(get_db), user: User = Depends(can_promote)):
    code = "".join(c for c in body.code.upper() if c.isalnum())
    if len(code) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A code needs at least three letters or numbers.")
    if body.kind not in PROMO_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose percent off or kwacha off.")
    if body.kind == "percent" and body.value > 100:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A percentage cannot be more than 100.")
    if db.scalar(select(Promotion).where(Promotion.code == code)):
        raise HTTPException(status.HTTP_409_CONFLICT, f"{code} already exists.")
    promo = Promotion(
        code=code, label=body.label.strip(), kind=body.kind, value=body.value,
        minimum_ngwee=body.minimum_ngwee, is_active=True, created_by=user.name,
    )
    db.add(promo)
    record(db, user.name, "sales", "Promotion created", f"{code}: {_promo_out(promo)['summary']}", code)
    db.commit()
    db.refresh(promo)
    return _promo_out(promo)


@router.post("/promotions/{promo_id}/toggle")
def toggle_promotion(promo_id: str, db: Session = Depends(get_db), user: User = Depends(can_promote)):
    promo = db.get(Promotion, promo_id)
    if not promo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Promotion not found.")
    promo.is_active = not promo.is_active
    record(db, user.name, "sales", "Promotion started" if promo.is_active else "Promotion stopped", promo.code, promo.code)
    db.commit()
    db.refresh(promo)
    return _promo_out(promo)


@router.get("/promotions/check/{code}")
def check_promotion(code: str, food_ngwee: int = Query(ge=0), db: Session = Depends(get_db),
                    _: User = Depends(requires("pos.use"))):
    """What a code would take off, so the till can show it before the sale."""
    from app.services.promotions import promo_discount
    try:
        off = promo_discount(db, code, food_ngwee)
    except ValueError as wrong:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(wrong))
    return {"code": code.strip().upper(), "discount_ngwee": off}


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackIn(BaseModel):
    order_number: str = Field(default="", max_length=24)
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=500)
    source: str = Field(default="counter", max_length=12)


@router.get("/feedback")
def feedback(db: Session = Depends(get_db), _: User = Depends(can_feedback)):
    rows = db.scalars(select(Feedback).order_by(Feedback.created_at.desc()).limit(200)).all()
    spread = Counter(f.rating for f in rows)
    return {
        "average": round(sum(f.rating for f in rows) / len(rows), 1) if rows else None,
        "count": len(rows),
        "spread": {str(n): spread[n] for n in (5, 4, 3, 2, 1)},
        "rows": [
            {
                "id": f.id, "rating": f.rating, "comment": f.comment, "source": f.source,
                "order_number": f.order_number, "customer": f.customer_name, "by": f.created_by or "",
                "at": _local(f.created_at).strftime("%d %b, %H:%M"),
            }
            for f in rows
        ],
    }


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def add_feedback(body: FeedbackIn, db: Session = Depends(get_db), user: User = Depends(can_feedback)):
    if body.source not in FEEDBACK_SOURCES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown source.")
    order = None
    if body.order_number.strip():
        order = db.scalar(select(Order).where(Order.number == body.order_number.strip().upper()))
        if not order:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "There is no order with that number.")
    row = Feedback(
        order_id=order.id if order else None, order_number=order.number if order else "",
        rating=body.rating, comment=body.comment.strip(), source=body.source,
        customer_name=order.customer_name if order else "", created_by=user.name,
    )
    db.add(row)
    record(db, user.name, "sales", "Feedback recorded", f"{body.rating} stars {row.order_number}".strip(), row.order_number)
    db.commit()
    return {"ok": True}
