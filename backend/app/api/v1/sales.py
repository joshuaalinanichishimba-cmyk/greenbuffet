"""The till: shifts, orders, payments and receipts.

Every amount here is worked out from the menu on the server. The browser says
what was ordered; the server decides what it costs, whether the choices were
allowed, and whether the money adds up.
"""
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import User
from app.models.menu import OptionItem, Product, ProductOptionGroup
from app.models.sales import (
    CASH_KINDS, METHOD_LABELS, ORDER_TYPES, PAYMENT_METHODS, CashMovement, IdempotencyKey, Order,
    OrderLine, OrderLineOption, Payment, Shift,
)
from app.schemas.sales import (
    CancelIn, DayTotals, MethodTotal, OrderIn, OrderLineOut, OrderOut, PaymentIn, PaymentOut,
    CashMoveIn, CashMoveOut, DecideIn, LineOptionOut, RefundIn, ShiftCloseIn, ShiftOpenIn, ShiftOut,
    ShiftReviewIn,
)
from app.services.approvals import approve, setting_int
from app.api.v1.kitchen import announce, send_to_kitchen
from app.api.v1.stock import take_stock_for_order
from app.services.audit import record
from app.services.numbering import numbered
from app.models.customers import Customer
from app.services.customers import find_or_make_customer
from app.services.loyalty import earn_on_order, free_item_for, give_back_on_cancel
from app.services.promotions import count_promo_use, promo_discount
from app.services.ordering import OrderProblem, apply_totals, build_lines
from app.services.posting import (
    Unbalanced, post_cash_movement, post_cost_of_sales, post_failed_payment, post_refund, post_sale,
    post_shift_variance,
)

router = APIRouter(prefix="/sales", tags=["sales"])

can_sell = requires("pos.use")
can_view = requires("pos.use", "orders.view", "reports.view", "books.view")
can_cancel = requires("orders.cancel")
can_refund = requires("orders.cancel", "refunds.request")
ELECTRONIC = ("airtel", "mtn", "zamtel", "card")

# Lusaka is UTC+2 with no daylight saving, so a trading day is a fixed window.
LUSAKA = timezone(timedelta(hours=2))


def _today_bounds() -> tuple[datetime, datetime]:
    today = datetime.now(LUSAKA).date()
    start = datetime.combine(today, time.min, tzinfo=LUSAKA)
    return start, start + timedelta(days=1)


def _next_number(db: Session) -> str:
    """GB-20261123-014: readable on a receipt, and sorts by itself."""
    today = datetime.now(LUSAKA).date()
    return numbered(db, f"GB-{today:%Y%m%d}-")


def _seen_before(db: Session, key: str | None, scope: str) -> str | None:
    if not key:
        return None
    found = db.scalar(select(IdempotencyKey).where(IdempotencyKey.key == key, IdempotencyKey.scope == scope))
    return found.result_id if found else None


def _remember(db: Session, key: str | None, scope: str, result_id: str) -> None:
    if not key:
        return
    db.add(IdempotencyKey(key=key, scope=scope, result_id=result_id))
    # A retry arrives within seconds, so keys older than a day are only
    # taking up room. Cleared here rather than on a timer, so there is one
    # fewer moving part to go wrong.
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    db.query(IdempotencyKey).filter(IdempotencyKey.created_at < cutoff).delete()


def _line_out(line: OrderLine) -> OrderLineOut:
    return OrderLineOut(
        id=line.id, product_id=line.product_id, product_name=line.product_name,
        product_code=line.product_code, station=line.station, unit_ngwee=line.unit_ngwee,
        options_ngwee=line.options_ngwee, quantity=line.quantity, line_ngwee=line.line_ngwee,
        note=line.note,
        options=[
            LineOptionOut(group_name=o.group_name, item_name=o.item_name, price_ngwee=o.price_ngwee,
                          option_item_id=o.option_item_id)
            for o in line.options
        ],
    )


def _payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id, method=p.method, label=METHOD_LABELS.get(p.method, p.method),
        amount_ngwee=p.amount_ngwee, tendered_ngwee=p.tendered_ngwee,
        change_ngwee=p.change_ngwee, reference=p.reference, is_refund=p.is_refund,
        at=p.created_at.isoformat(), taken_by=p.created_by,
        status=p.status or "confirmed", confirmed_by=p.confirmed_by,
    )


def _order_out(o: Order) -> OrderOut:
    return OrderOut(
        id=o.id, number=o.number, status=o.status, order_type=o.order_type,
        customer_name=o.customer_name, customer_phone=o.customer_phone, note=o.note,
        subtotal_ngwee=o.subtotal_ngwee, discount_ngwee=o.discount_ngwee,
        discount_reason=o.discount_reason or "", discount_approved_by=o.discount_approved_by,
        total_ngwee=o.total_ngwee, vat_ngwee=o.vat_ngwee, paid_ngwee=o.paid_ngwee,
        outstanding_ngwee=o.outstanding_ngwee,
        change_ngwee=sum(p.change_ngwee or 0 for p in o.payments),
        created_by=o.created_by, created_at=o.created_at.isoformat(),
        paid_at=o.paid_at.isoformat() if o.paid_at else None,
        cancelled_at=o.cancelled_at.isoformat() if o.cancelled_at else None,
        cancel_reason=o.cancel_reason,
        lines=[_line_out(line) for line in o.lines],
        payments=[_payment_out(p) for p in o.payments],
    )


def _method_totals(payments: list[Payment]) -> list[MethodTotal]:
    totals: dict[str, list[int]] = {}
    for p in payments:
        amount = -p.amount_ngwee if p.is_refund else p.amount_ngwee
        row = totals.setdefault(p.method, [0, 0])
        row[0] += amount
        row[1] += 1
    return [
        MethodTotal(method=m, label=METHOD_LABELS.get(m, m), amount_ngwee=v[0], count=v[1])
        for m, v in sorted(totals.items())
    ]


def _cash_moves_ngwee(db: Session, shift: Shift) -> int:
    """What cash movements did to the drawer: drops and petty cash take out,
    cash added puts in. Rejected ones never happened."""
    total = 0
    for m in db.scalars(select(CashMovement).where(
            CashMovement.shift_id == shift.id, CashMovement.status != "rejected")).all():
        total += m.amount_ngwee if m.kind == "added" else -m.amount_ngwee
    return total


def _expected_cash(db: Session, shift: Shift, cash_ngwee: int) -> int:
    """Float + cash taken − cash refunds (already netted in cash_ngwee)
    + cash added − drops − petty cash."""
    return shift.float_ngwee + cash_ngwee + _cash_moves_ngwee(db, shift)


def _shift_out(db: Session, shift: Shift, viewer: User | None = None) -> ShiftOut:
    payments = db.scalars(select(Payment).where(Payment.shift_id == shift.id, Payment.status != "failed")).all()
    orders = db.scalar(
        select(func.count(Order.id)).where(Order.shift_id == shift.id, Order.status == "paid")
    ) or 0
    sales = sum((-p.amount_ngwee if p.is_refund else p.amount_ngwee) for p in payments)
    cash = sum((-p.amount_ngwee if p.is_refund else p.amount_ngwee) for p in payments if p.method == "cash")
    # The count at closing is blind: a cashier does not see the cash figure
    # of their own open till. Managers (cash.approve) always see it.
    blind = (
        viewer is not None and shift.is_open
        and "cash.approve" not in viewer.role.permission_codes
    )
    limit = setting_int(db, "till.variance_limit_ngwee", 2000)
    methods = _method_totals(list(payments))
    if blind:
        methods = [m for m in methods if m.method != "cash"]
    return ShiftOut(
        id=shift.id, opened_by=shift.opened_by, opened_at=shift.opened_at.isoformat(),
        float_ngwee=shift.float_ngwee,
        closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
        closed_by=shift.closed_by, expected_ngwee=shift.expected_ngwee,
        counted_ngwee=shift.counted_ngwee, variance_ngwee=shift.variance_ngwee,
        note=shift.note, is_open=shift.is_open, orders=orders, sales_ngwee=sales,
        cash_ngwee=None if blind else cash, by_method=methods,
        cash_moves_ngwee=0 if blind else _cash_moves_ngwee(db, shift),
        first_count_ngwee=shift.first_count_ngwee, reviewed_by=shift.reviewed_by,
        review_note=shift.review_note or "",
        needs_review=bool(
            shift.closed_at and not shift.reviewed_by and abs(shift.variance_ngwee or 0) > limit
        ),
    )


def _open_shift(db: Session, user: User) -> Shift | None:
    return db.scalar(
        select(Shift).where(Shift.opened_by_id == user.id, Shift.closed_at.is_(None))
        .order_by(Shift.opened_at.desc())
    )


# --------------------------------------------------------------------------
# shifts
# --------------------------------------------------------------------------

@router.get("/shifts/current", response_model=ShiftOut | None)
def current_shift(db: Session = Depends(get_db), user: User = Depends(can_sell)):
    shift = _open_shift(db, user)
    return _shift_out(db, shift, user) if shift else None


@router.post("/shifts", response_model=ShiftOut, status_code=status.HTTP_201_CREATED)
def open_shift(body: ShiftOpenIn, db: Session = Depends(get_db), user: User = Depends(can_sell)):
    if _open_shift(db, user):
        raise HTTPException(status.HTTP_409_CONFLICT, "You already have a till open. Close it first.")
    shift = Shift(
        opened_by=user.name, opened_by_id=user.id, opened_at=datetime.now(timezone.utc),
        float_ngwee=body.float_ngwee, note=body.note.strip(), created_by=user.name,
    )
    db.add(shift)
    record(db, user.name, "sales", "Till opened", f"float {body.float_ngwee} ngwee")
    db.commit()
    db.refresh(shift)
    return _shift_out(db, shift, user)


@router.post("/shifts/{shift_id}/close", response_model=ShiftOut)
def close_shift(
    shift_id: str, body: ShiftCloseIn,
    db: Session = Depends(get_db), user: User = Depends(can_sell),
):
    shift = db.get(Shift, shift_id)
    if not shift:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Till session not found.")
    if not shift.is_open:
        raise HTTPException(status.HTTP_409_CONFLICT, "That till has already been closed.")
    if shift.opened_by_id != user.id and "cash.approve" not in user.role.permission_codes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the cashier who opened this till, or a manager, can close it.")

    unpaid = db.scalar(
        select(func.count(Order.id)).where(Order.shift_id == shift.id, Order.status == "open")
    ) or 0
    if unpaid:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{unpaid} order(s) on this till are still unpaid. Take payment or cancel them first.",
        )

    summary = _shift_out(db, shift)  # no viewer: the full, unblinded figures
    expected = _expected_cash(db, shift, summary.cash_ngwee or 0)
    variance = body.counted_ngwee - expected

    # The first figure typed is kept whatever happens next, so a recount
    # that lands exactly on the expected amount can be seen for what it is.
    if shift.first_count_ngwee is None:
        shift.first_count_ngwee = body.counted_ngwee
        record(db, user.name, "sales", "Till counted", shift.opened_by, shift.id,
               after={"counted": body.counted_ngwee})

    # Out by more than the limit: the till stays open until someone says why.
    limit = setting_int(db, "till.variance_limit_ngwee", 2000)
    if abs(variance) > limit and len(body.note.strip()) < 3:
        db.commit()
        word = "over" if variance > 0 else "short"
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"The drawer is K{abs(variance) / 100:,.2f} {word}. Write what happened in the note "
            f"and close again. A manager will review it.",
        )

    shift.closed_at = datetime.now(timezone.utc)
    shift.closed_by = user.name
    shift.expected_ngwee = expected
    shift.counted_ngwee = body.counted_ngwee
    shift.variance_ngwee = variance
    if body.note.strip():
        shift.note = body.note.strip()
    try:
        post_shift_variance(db, shift)
    except Unbalanced:
        pass
    record(db, user.name, "sales", "Till closed", shift.opened_by, shift.id,
           before={"expected": expected}, after={"counted": body.counted_ngwee,
                                                 "variance": shift.variance_ngwee})
    db.commit()
    db.refresh(shift)
    return _shift_out(db, shift)


@router.get("/shifts", response_model=list[ShiftOut])
def shifts(
    limit: int = Query(default=20, le=100),
    needs_review: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(can_view),
):
    rows = db.scalars(select(Shift).order_by(Shift.opened_at.desc()).limit(200 if needs_review else limit)).all()
    out = [_shift_out(db, s, user) for s in rows]
    return [o for o in out if o.needs_review][:limit] if needs_review else out


@router.post("/shifts/{shift_id}/review", response_model=ShiftOut)
def review_shift(
    shift_id: str, body: ShiftReviewIn,
    db: Session = Depends(get_db), user: User = Depends(requires("cash.approve")),
):
    """A manager's look at a till that counted out of line. It records what
    was found; it never changes the figures or accuses anyone."""
    shift = db.get(Shift, shift_id)
    if not shift or shift.is_open:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No closed till with that number.")
    if shift.opened_by_id == user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Someone other than the cashier has to review their till.")
    shift.reviewed_by = user.name
    shift.reviewed_at = datetime.now(timezone.utc)
    shift.review_note = body.note.strip()
    record(db, user.name, "sales", "Till count reviewed", f"{shift.opened_by}: {body.note.strip()}", shift.id,
           after={"variance": shift.variance_ngwee})
    db.commit()
    return _shift_out(db, shift, user)


# --------------------------------------------------------------------------
# cash moved in or out of a drawer
# --------------------------------------------------------------------------

def _cash_out(m: CashMovement, shift: Shift) -> CashMoveOut:
    return CashMoveOut(
        id=m.id, shift_id=m.shift_id, cashier=shift.opened_by, kind=m.kind,
        label=CASH_KINDS.get(m.kind, m.kind), amount_ngwee=m.amount_ngwee, reason=m.reason,
        status=m.status, recorded_by=m.created_by, at=m.created_at.isoformat(), decided_by=m.decided_by,
    )


@router.post("/cash", response_model=CashMoveOut, status_code=status.HTTP_201_CREATED)
def move_cash(
    body: CashMoveIn, db: Session = Depends(get_db), user: User = Depends(requires("cash.move")),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """A drop to the safe, cash added from the safe, or petty cash spent, on
    your own open till. It counts in the expected cash straight away and
    waits for a manager to confirm it."""
    repeated = _seen_before(db, idempotency_key, "cash")
    if repeated:
        m = db.get(CashMovement, repeated)
        if m:
            return _cash_out(m, db.get(Shift, m.shift_id))
    if body.kind not in CASH_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a drop, cash added, or petty cash.")
    shift = _open_shift(db, user)
    if not shift:
        raise HTTPException(status.HTTP_409_CONFLICT, "Open your till first.")
    m = CashMovement(shift_id=shift.id, kind=body.kind, amount_ngwee=body.amount_ngwee,
                     reason=body.reason.strip(), created_by=user.name)
    db.add(m)
    db.flush()
    try:
        post_cash_movement(db, m, who=user.name)
    except Unbalanced:
        pass
    _remember(db, idempotency_key, "cash", m.id)
    record(db, user.name, "money", CASH_KINDS[body.kind],
           f"K{body.amount_ngwee / 100:,.2f}: {body.reason.strip()}", m.id,
           after={"amount": body.amount_ngwee, "till": shift.opened_by})
    db.commit()
    return _cash_out(m, shift)


@router.get("/cash", response_model=list[CashMoveOut])
def cash_moves(
    pending: bool = False, days: int = Query(default=7, ge=1, le=62),
    db: Session = Depends(get_db), user: User = Depends(requires("cash.move", "cash.approve")),
):
    since = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(CashMovement).where(CashMovement.created_at >= since).order_by(CashMovement.created_at.desc())
    if pending:
        stmt = stmt.where(CashMovement.status == "pending")
    rows = db.scalars(stmt).all()
    # A cashier sees their own; a manager sees everyone's.
    if "cash.approve" not in user.role.permission_codes:
        rows = [m for m in rows if m.created_by == user.name]
    return [_cash_out(m, db.get(Shift, m.shift_id)) for m in rows]


@router.post("/cash/{move_id}/decide", response_model=CashMoveOut)
def decide_cash(
    move_id: str, body: DecideIn,
    db: Session = Depends(get_db), user: User = Depends(requires("cash.approve")),
):
    m = db.get(CashMovement, move_id)
    if not m:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    if m.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {m.status}.")
    if m.created_by == user.name:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Someone else has to confirm cash you moved yourself.")
    m.status = "confirmed" if body.ok else "rejected"
    m.decided_by = user.name
    m.decided_at = datetime.now(timezone.utc)
    if not body.ok:
        try:
            post_cash_movement(db, m, who=user.name, reverse=True)
        except Unbalanced:
            pass
    record(db, user.name, "money", "Cash movement " + m.status,
           f"{CASH_KINDS.get(m.kind, m.kind)} K{m.amount_ngwee / 100:,.2f}: {body.note.strip() or m.reason}", m.id)
    db.commit()
    return _cash_out(m, db.get(Shift, m.shift_id))


# --------------------------------------------------------------------------
# orders
# --------------------------------------------------------------------------

def _price_order(db: Session, order: Order, body: OrderIn, user: User) -> None:
    """Prices an order from what the till sent: lines, the discount and its
    approval, a promotion code and the stamp card. Used when an order is
    taken and again when an unpaid order is changed."""
    try:
        priced = build_lines(db, order, body.lines)
    except OrderProblem as problem:
        raise HTTPException(problem.code, problem.message)

    discount = min(body.discount_ngwee, priced.subtotal_ngwee)

    # A discount typed at the till: allowed up to the cashier's limit with a
    # reason; above it, a manager approves on the spot. Promotion codes and
    # free stamp-card items below are rules of their own, not discounts.
    if discount:
        codes = user.role.permission_codes
        if not body.discount_reason.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Say why the discount is given.")
        limit_pct = setting_int(db, "till.discount_limit_percent", 10)
        over_limit = discount * 100 > priced.subtotal_ngwee * limit_pct
        if "discounts.approve" in codes:
            pass
        elif "discounts.give" in codes and not over_limit:
            pass
        else:
            what = (f"A discount over {limit_pct}%" if "discounts.give" in codes
                    else "A discount")
            approver = approve(db, body.approval, "discounts.approve", user, what)
            order.discount_approved_by = approver.name
        order.discount_reason = body.discount_reason.strip()

    # A customer who gives a phone number is remembered, so points are earned
    # at the counter exactly as they are online.
    # A promotion code takes its share off the food, checked here rather
    # than trusted from the screen: the code must exist, be running, and the
    # order must reach its minimum.
    if body.promo_code.strip():
        try:
            promo_off = promo_discount(db, body.promo_code, priced.subtotal_ngwee - discount)
        except ValueError as wrong:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(wrong))
        order.promo_code = body.promo_code.strip().upper()
        order.promo_ngwee = promo_off
        discount += promo_off

    # A customer who gives a phone number is remembered, and a full stamp
    # card makes their next bowl or burrito free without anyone asking.
    customer = None
    if order.customer_phone:
        customer = find_or_make_customer(db, order.customer_phone, order.customer_name)
        order.customer_id = customer.id
        discount += free_item_for(db, customer, order)

    apply_totals(order, priced, discount_ngwee=discount)


@router.post("/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    body: OrderIn, db: Session = Depends(get_db), user: User = Depends(can_sell),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    repeated = _seen_before(db, idempotency_key, "order")
    if repeated:
        existing = db.get(Order, repeated)
        if existing:
            return _order_out(existing)

    if body.order_type not in ORDER_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown order type.")
    shift = _open_shift(db, user)
    if not shift:
        raise HTTPException(status.HTTP_409_CONFLICT, "Open the till before taking an order.")

    order = Order(
        number=_next_number(db), shift_id=shift.id, order_type=body.order_type,
        customer_name=body.customer_name.strip(), customer_phone=body.customer_phone.strip(),
        note=body.note.strip(), created_by=user.name,
    )
    db.add(order)
    db.flush()

    _price_order(db, order, body, user)

    _remember(db, idempotency_key, "order", order.id)
    record(db, user.name, "sales", "Order taken", f"{order.number}, {order.total_ngwee} ngwee", order.number)
    if order.discount_reason:
        record(db, user.name, "sales", "Discount given",
               f"{order.number}: K{body.discount_ngwee / 100:,.2f} ({order.discount_reason})"
               + (f", approved by {order.discount_approved_by}" if order.discount_approved_by else ""),
               order.number, after={"discount": body.discount_ngwee, "approved_by": order.discount_approved_by})
    db.commit()
    db.refresh(order)
    return _order_out(order)


@router.put("/orders/{order_id}", response_model=OrderOut)
def change_order(
    order_id: str, body: OrderIn, db: Session = Depends(get_db), user: User = Depends(can_sell),
):
    """Changes an order that has not been paid for: add, remove or change
    items without cancelling and starting again. Once money is taken it can
    only be refunded."""
    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if found.status != "open" or found.payments:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an unpaid order can be changed. Refund it instead.")
    if body.order_type not in ORDER_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown order type.")
    before = {"total": found.total_ngwee, "lines": [f"{l.quantity} x {l.product_name}" for l in found.lines]}
    # A stamp card spent on the old version goes back before it is re-priced.
    if found.customer_id:
        give_back_on_cancel(db, db.get(Customer, found.customer_id), found, who=user.name)
    for line in list(found.lines):
        db.delete(line)
    db.flush()
    found.order_type = body.order_type
    found.customer_name, found.customer_phone = body.customer_name.strip(), body.customer_phone.strip()
    found.note = body.note.strip()
    found.discount_reason, found.discount_approved_by = "", None
    found.promo_code, found.promo_ngwee, found.customer_id = "", 0, None
    db.refresh(found)
    _price_order(db, found, body, user)
    record(db, user.name, "sales", "Order changed", found.number, found.number,
           before=before, after={"total": found.total_ngwee,
                                 "lines": [f"{l.quantity} x {l.product_name}" for l in found.lines]})
    db.commit()
    db.refresh(found)
    return _order_out(found)


@router.get("/orders", response_model=list[OrderOut])
def orders(
    status_filter: str | None = Query(default=None, alias="status"),
    today: bool = True,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(can_view),
):
    stmt = select(Order).order_by(Order.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Order.status == status_filter)
    if today:
        start, end = _today_bounds()
        stmt = stmt.where(Order.created_at >= start, Order.created_at < end)
    return [_order_out(o) for o in db.scalars(stmt).all()]


@router.get("/orders/{order_id}", response_model=OrderOut)
def order(order_id: str, db: Session = Depends(get_db), _: User = Depends(can_view)):
    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    return _order_out(found)


@router.post("/orders/{order_id}/payments", response_model=OrderOut)
def take_payment(
    order_id: str, body: PaymentIn, db: Session = Depends(get_db), user: User = Depends(can_sell),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    repeated = _seen_before(db, idempotency_key, "payment")
    if repeated:
        taken = db.get(Payment, repeated)
        if taken:
            return _order_out(db.get(Order, taken.order_id))

    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if found.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "That order was cancelled.")
    if body.method not in PAYMENT_METHODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown payment method.")
    if found.outstanding_ngwee <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "That order is already paid.")
    if body.amount_ngwee > found.outstanding_ngwee:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "That is more than the order owes. Take the amount owing and give change from the drawer.",
        )
    if body.method in ELECTRONIC and not body.reference.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Enter the transaction number from the payment, so it can be matched later.",
        )
    if body.method in ELECTRONIC:
        # One transaction pays once. A reference already used (and not marked
        # failed) is refused, whichever order it was on.
        used = db.scalar(select(Payment).where(Payment.status != "failed", 
            Payment.method == body.method, Payment.reference == body.reference.strip(),
            Payment.is_refund.is_(False), Payment.status != "failed",
        ))
        if used:
            other = db.get(Order, used.order_id)
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Transaction {body.reference.strip()} has already been used on order "
                f"{other.number if other else '?'}. Check the number on the customer's message.",
            )
    if body.method == "account" and not found.customer_name.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "An order on account needs the customer's name.",
        )

    change = None
    if body.method == "cash" and body.tendered_ngwee is not None:
        if body.tendered_ngwee < body.amount_ngwee:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The cash given is less than the amount.")
        change = body.tendered_ngwee - body.amount_ngwee

    shift = _open_shift(db, user)
    payment = Payment(
        order_id=found.id, shift_id=shift.id if shift else found.shift_id, method=body.method,
        amount_ngwee=body.amount_ngwee, tendered_ngwee=body.tendered_ngwee,
        change_ngwee=change, reference=body.reference.strip(), note=body.note.strip(),
        created_by=user.name,
        status="confirmed" if body.method not in ELECTRONIC or body.confirmed else "pending",
        confirmed_by=user.name if body.method not in ELECTRONIC or body.confirmed else None,
        confirmed_at=datetime.now(timezone.utc) if body.method not in ELECTRONIC or body.confirmed else None,
    )
    db.add(payment)
    db.flush()
    # The order's loaded payments do not include the row just added, so the
    # totals have to be read again before deciding whether it is settled.
    db.refresh(found)

    tell_kitchen = False
    if found.outstanding_ngwee <= 0:
        found.status = "paid"
        found.paid_at = datetime.now(timezone.utc)
        # Paid means the kitchen can start: the board is written here rather
        # than being polled for new orders.
        # The board is told only after the commit below. Told now, it would
        # fetch its tickets before this transaction is saved and miss the
        # very order it was told about.
        tell_kitchen = send_to_kitchen(db, found) > 0
        # What the order used leaves stock here, from the recipes behind it.
        take_stock_for_order(db, found)
        # And the books follow the money and the food in the same breath.
        _post_books(db, found)
        # Stamps are earned on payment, never on placing an order: an order
        # that is never paid for has earned nothing.
        if found.customer_id:
            customer = db.get(Customer, found.customer_id)
            if customer:
                earn_on_order(db, customer, found, who=user.name)
        # A promotion counts as used once the order it was used on is paid.
        if found.promo_code:
            count_promo_use(db, found.promo_code, found.promo_ngwee)

    _remember(db, idempotency_key, "payment", payment.id)
    record(db, user.name, "money", "Payment taken",
           f"{found.number}, {METHOD_LABELS[body.method]} {body.amount_ngwee} ngwee"
           + (f", ref {payment.reference}" if payment.reference else "")
           + (" (waiting for confirmation)" if payment.status == "pending" else ""), found.number)
    db.commit()
    if tell_kitchen:
        announce("new", {"order_number": found.number})
    db.refresh(found)
    return _order_out(found)


def _post_books(db: Session, order: Order) -> None:
    """Writes the journal entries for a paid order.

    The books must never stop the till. If an entry cannot be written the sale
    still stands, and the gap shows up in the trial balance rather than losing
    the sale itself.
    """
    from app.models.stock import StockMove

    try:
        db.flush()
        post_sale(db, order)
        used = db.scalar(
            select(func.coalesce(func.sum(StockMove.value_ngwee), 0)).where(
                StockMove.kind == "sale", StockMove.reference == order.number
            )
        ) or 0
        post_cost_of_sales(db, order, abs(int(used)))
    except Unbalanced:
        pass


@router.post("/orders/{order_id}/refund", response_model=OrderOut)
def refund(
    order_id: str, body: RefundIn, db: Session = Depends(get_db),
    user: User = Depends(can_refund),
):
    """Gives money back without touching the original payment row. A cashier
    can ask; a manager (orders.cancel) gives it, or approves it on the spot."""
    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    approved_by = None
    if "orders.cancel" not in user.role.permission_codes:
        approved_by = approve(db, body.approval, "orders.cancel", user, "A refund").name
    if body.method not in PAYMENT_METHODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown payment method.")
    if body.amount_ngwee > found.paid_ngwee - found.refunded_ngwee:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That is more than was paid on this order.")

    shift = _open_shift(db, user)
    db.add(Payment(
        order_id=found.id, shift_id=shift.id if shift else found.shift_id, method=body.method,
        amount_ngwee=body.amount_ngwee, is_refund=True, note=body.reason.strip(),
        created_by=user.name,
    ))
    db.flush()
    try:
        post_refund(db, found, found.payments[-1])
    except Unbalanced:
        pass
    record(db, user.name, "money", "Refund given",
           f"{found.number}, {body.amount_ngwee} ngwee: {body.reason.strip()}"
           + (f", approved by {approved_by}" if approved_by else ""), found.number,
           after={"amount": body.amount_ngwee, "approved_by": approved_by})
    db.commit()
    db.refresh(found)
    return _order_out(found)


@router.post("/orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: str, body: CancelIn, db: Session = Depends(get_db),
    user: User = Depends(can_cancel),
):
    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if found.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "That order is already cancelled.")
    if found.paid_ngwee > found.refunded_ngwee:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Money has been taken on this order. Refund it first, then cancel.",
        )
    found.status = "cancelled"
    found.cancelled_at = datetime.now(timezone.utc)
    found.cancelled_by = user.name
    found.cancel_reason = body.reason.strip()
    # A full stamp card spent on this order goes back on the customer's card.
    if found.customer_id:
        give_back_on_cancel(db, db.get(Customer, found.customer_id), found, who=user.name)
    record(db, user.name, "sales", "Order cancelled", f"{found.number}: {body.reason.strip()}", found.number)
    db.commit()
    db.refresh(found)
    return _order_out(found)


@router.get("/today", response_model=DayTotals)
def today(db: Session = Depends(get_db), _: User = Depends(can_view)):
    start, end = _today_bounds()
    paid = db.scalars(
        select(Order).where(Order.created_at >= start, Order.created_at < end, Order.status == "paid")
    ).all()
    payments = db.scalars(
        select(Payment).where(Payment.status != "failed", Payment.created_at >= start, Payment.created_at < end)
    ).all()
    return DayTotals(
        date=datetime.now(LUSAKA).date().isoformat(),
        orders=len(paid),
        sales_ngwee=sum(o.total_ngwee for o in paid),
        vat_ngwee=sum(o.vat_ngwee for o in paid),
        refunds_ngwee=sum(p.amount_ngwee for p in payments if p.is_refund),
        by_method=_method_totals(list(payments)),
    )


@router.get("/orders/{order_id}/receipt")
def receipt(
    order_id: str, request: Request, reprint: bool = False,
    db: Session = Depends(get_db), user: User = Depends(can_view),
):
    """Everything a printed receipt needs, already worded and in order. A
    reprint is recorded, since a second copy of a receipt can be used to
    claim a refund twice."""
    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if reprint:
        record(db, user.name, "sales", "Receipt reprinted", found.number, found.number)
        db.commit()
    when = (found.paid_at or found.created_at).astimezone(LUSAKA)
    from app.api.v1.settings_api import business_settings

    business = business_settings(db)
    return {
        "business": business["business_name"] or settings.BUSINESS_NAME,
        "address": business["business_address"],
        "phone": business["business_phone"],
        "tpin": business["business_tpin"],
        "vat_number": business["business_vat_number"],
        # The VAT line prints only for a sale that carried VAT, so a receipt
        # from a period when the business was not registered never claims it.
        "vat_registered": found.vat_ngwee > 0,
        "number": found.number,
        "at": when.strftime("%d %b %Y, %H:%M"),
        "served_by": found.created_by,
        "order_type": {"takeaway": "Takeaway", "eat_in": "Eat in", "delivery": "Delivery"}.get(found.order_type, found.order_type),
        "customer": found.customer_name,
        "status": found.status,
        "lines": [
            {
                "name": line.product_name,
                "quantity": line.quantity,
                "each_ngwee": line.unit_ngwee + line.options_ngwee,
                "total_ngwee": line.line_ngwee,
                "options": [
                    f"{o.item_name}" + (f" +{o.price_ngwee / 100:.2f}" if o.price_ngwee else "")
                    for o in line.options
                ],
                "note": line.note,
            }
            for line in found.lines
        ],
        "subtotal_ngwee": found.subtotal_ngwee,
        "discount_ngwee": found.discount_ngwee,
        "total_ngwee": found.total_ngwee,
        "vat_ngwee": found.vat_ngwee,
        "payments": [
            {
                "label": METHOD_LABELS.get(p.method, p.method),
                "amount_ngwee": p.amount_ngwee,
                "reference": p.reference,
                "is_refund": p.is_refund,
            }
            for p in found.payments
        ],
        "change_ngwee": sum(p.change_ngwee or 0 for p in found.payments),
        "footer": business["receipt_footer"] if found.vat_ngwee
                  else business["receipt_footer"].replace("Prices include VAT.", "").strip(),
    }


# --------------------------------------------------------------------------
# mobile money and card: matching what was typed against what arrived
# --------------------------------------------------------------------------

@router.get("/payments/unconfirmed")
def unconfirmed_payments(
    days: int = Query(default=14, ge=1, le=62),
    db: Session = Depends(get_db), _: User = Depends(requires("payments.confirm")),
):
    """Mobile money and card payments nobody has yet seen arrive. Match each
    against the operator's statement or the merchant phone's messages."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.scalars(select(Payment).where(Payment.status != "failed", 
        Payment.status == "pending", Payment.is_refund.is_(False), Payment.created_at >= since,
    ).order_by(Payment.created_at)).all()
    out = []
    for p in rows:
        o = db.get(Order, p.order_id)
        out.append({
            "id": p.id, "order_id": p.order_id, "order_number": o.number if o else "",
            "method": p.method, "label": METHOD_LABELS.get(p.method, p.method),
            "amount_ngwee": p.amount_ngwee, "reference": p.reference,
            "taken_by": p.created_by, "at": p.created_at.isoformat(),
        })
    return out


@router.post("/payments/{payment_id}/confirm")
def confirm_payment(
    payment_id: str, body: DecideIn,
    db: Session = Depends(get_db), user: User = Depends(requires("payments.confirm")),
):
    """ok=true: the money is on the statement. ok=false: it never arrived;
    it stops counting as paid, and the books move it to money owed to us."""
    p = db.get(Payment, payment_id)
    if not p or p.is_refund:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found.")
    if p.status != "pending":
        raise HTTPException(status.HTTP_409_CONFLICT, f"That payment is already {p.status}.")
    order = db.get(Order, p.order_id)
    p.status = "confirmed" if body.ok else "failed"
    p.confirmed_by = user.name
    p.confirmed_at = datetime.now(timezone.utc)
    if not body.ok and order and order.status == "paid":
        try:
            post_failed_payment(db, order, p, who=user.name)
        except Unbalanced:
            pass
    record(db, user.name, "money", "Payment confirmed" if body.ok else "Payment failed",
           f"{order.number if order else ''}: {METHOD_LABELS.get(p.method, p.method)} {p.reference}, "
           f"K{p.amount_ngwee / 100:,.2f}" + (f" ({body.note.strip()})" if body.note.strip() else ""),
           order.number if order else p.id)
    db.commit()
    return {"id": p.id, "status": p.status, "outstanding_ngwee": order.outstanding_ngwee if order else 0}
