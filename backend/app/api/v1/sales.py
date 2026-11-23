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
from app.models.demo import DemoCheckout
from app.models.menu import OptionItem, Product, ProductOptionGroup
from app.models.sales import (
    METHOD_LABELS, ORDER_TYPES, PAYMENT_METHODS, IdempotencyKey, Order, OrderLine,
    OrderLineOption, Payment, Shift,
)
from app.schemas.sales import (
    CancelIn, DayTotals, MethodTotal, OrderIn, OrderLineOut, OrderOut, PaymentIn, PaymentOut,
    LineOptionOut, RefundIn, ShiftCloseIn, ShiftOpenIn, ShiftOut,
)
from app.api.v1.kitchen import announce, send_to_kitchen
from app.api.v1.stock import take_stock_for_order
from app.services.audit import record
from app.services.numbering import numbered
from app.services.posting import Unbalanced, post_cost_of_sales, post_refund, post_sale, post_shift_variance

router = APIRouter(prefix="/sales", tags=["sales"])

can_sell = requires("pos.use")
can_view = requires("pos.use", "orders.view", "reports.view", "books.view")
can_cancel = requires("orders.cancel")

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
            LineOptionOut(group_name=o.group_name, item_name=o.item_name, price_ngwee=o.price_ngwee)
            for o in line.options
        ],
    )


def _payment_out(p: Payment) -> PaymentOut:
    return PaymentOut(
        id=p.id, method=p.method, label=METHOD_LABELS.get(p.method, p.method),
        amount_ngwee=p.amount_ngwee, tendered_ngwee=p.tendered_ngwee,
        change_ngwee=p.change_ngwee, reference=p.reference, is_refund=p.is_refund,
        at=p.created_at.isoformat(), taken_by=p.created_by,
    )


def _order_out(o: Order) -> OrderOut:
    return OrderOut(
        id=o.id, number=o.number, status=o.status, order_type=o.order_type,
        customer_name=o.customer_name, customer_phone=o.customer_phone, note=o.note,
        subtotal_ngwee=o.subtotal_ngwee, discount_ngwee=o.discount_ngwee,
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


def _shift_out(db: Session, shift: Shift) -> ShiftOut:
    payments = db.scalars(select(Payment).where(Payment.shift_id == shift.id)).all()
    orders = db.scalar(
        select(func.count(Order.id)).where(Order.shift_id == shift.id, Order.status == "paid")
    ) or 0
    sales = sum((-p.amount_ngwee if p.is_refund else p.amount_ngwee) for p in payments)
    cash = sum((-p.amount_ngwee if p.is_refund else p.amount_ngwee) for p in payments if p.method == "cash")
    return ShiftOut(
        id=shift.id, opened_by=shift.opened_by, opened_at=shift.opened_at.isoformat(),
        float_ngwee=shift.float_ngwee,
        closed_at=shift.closed_at.isoformat() if shift.closed_at else None,
        closed_by=shift.closed_by, expected_ngwee=shift.expected_ngwee,
        counted_ngwee=shift.counted_ngwee, variance_ngwee=shift.variance_ngwee,
        note=shift.note, is_open=shift.is_open, orders=orders, sales_ngwee=sales,
        cash_ngwee=cash, by_method=_method_totals(list(payments)),
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
    return _shift_out(db, shift) if shift else None


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
    return _shift_out(db, shift)


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
    if shift.opened_by_id != user.id and "staff.manage" not in user.role.permission_codes:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the cashier who opened this till, or a manager, can close it.")

    unpaid = db.scalar(
        select(func.count(Order.id)).where(Order.shift_id == shift.id, Order.status == "open")
    ) or 0
    if unpaid:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{unpaid} order(s) on this till are still unpaid. Take payment or cancel them first.",
        )

    summary = _shift_out(db, shift)
    expected = shift.float_ngwee + summary.cash_ngwee
    shift.closed_at = datetime.now(timezone.utc)
    shift.closed_by = user.name
    shift.expected_ngwee = expected
    shift.counted_ngwee = body.counted_ngwee
    shift.variance_ngwee = body.counted_ngwee - expected
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
    db: Session = Depends(get_db),
    _: User = Depends(can_view),
):
    rows = db.scalars(select(Shift).order_by(Shift.opened_at.desc()).limit(limit)).all()
    return [_shift_out(db, s) for s in rows]


# --------------------------------------------------------------------------
# orders
# --------------------------------------------------------------------------

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

    order = build_order(db, body, user.name, shift.id)
    _remember(db, idempotency_key, "order", order.id)
    record(db, user.name, "sales", "Order taken", f"{order.number}, {order.total_ngwee} ngwee", order.number)
    db.commit()
    db.refresh(order)
    return _order_out(order)


def build_order(db: Session, body: OrderIn, actor: str, shift_id: str | None = None) -> Order:
    """Build and price an order in the caller's transaction."""
    order = Order(
        number=_next_number(db), shift_id=shift_id, order_type=body.order_type,
        customer_name=body.customer_name.strip(), customer_phone=body.customer_phone.strip(),
        note=body.note.strip(), created_by=actor,
    )
    db.add(order)
    db.flush()

    subtotal = 0
    vat_total = 0
    for position, wanted in enumerate(body.lines, start=1):
        product = db.get(Product, wanted.product_id)
        if not product or not product.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That item is not on the menu.")
        if not product.is_available:
            raise HTTPException(status.HTTP_409_CONFLICT, f"{product.name} is sold out.")

        allowed_groups = {link.group_id: link.group for link in product.option_links}
        chosen: dict[str, list[OptionItem]] = {}
        options_total = 0
        for choice in wanted.options:
            item = db.get(OptionItem, choice.option_item_id)
            if not item or not item.is_active:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown choice.")
            if item.group_id not in allowed_groups:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"{item.name} is not offered with {product.name}.",
                )
            if not item.is_available:
                raise HTTPException(status.HTTP_409_CONFLICT, f"{item.name} is sold out.")
            chosen.setdefault(item.group_id, []).append(item)
            options_total += item.price_ngwee

        # The group's own rule, checked here because the browser cannot be trusted.
        for group_id, group in allowed_groups.items():
            if not group.is_active:
                continue
            picked = len(chosen.get(group_id, []))
            if picked < group.min_select:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"{product.name}: choose {group.min_select} from {group.name}.",
                )
            if picked > group.max_select:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    f"{product.name}: at most {group.max_select} from {group.name}.",
                )

        unit = product.price_ngwee
        line_total = (unit + options_total) * wanted.quantity
        rate = int(float(product.vat_rate))
        # VAT is inside the price: K116 at 16% holds K16 of tax.
        vat_total += round(line_total * rate / (100 + rate)) if rate else 0
        subtotal += line_total

        line = OrderLine(
            order_id=order.id, position=position, product_id=product.id,
            product_name=product.name, product_code=product.code, station=product.station,
            unit_ngwee=unit, options_ngwee=options_total, quantity=wanted.quantity,
            line_ngwee=line_total, vat_rate=rate, note=wanted.note.strip(),
        )
        db.add(line)
        db.flush()
        for group_id, items in chosen.items():
            for item in items:
                db.add(OrderLineOption(
                    line_id=line.id, option_item_id=item.id,
                    group_name=allowed_groups[group_id].name, item_name=item.name,
                    price_ngwee=item.price_ngwee,
                ))

    discount = min(body.discount_ngwee, subtotal)
    order.subtotal_ngwee = subtotal
    order.discount_ngwee = discount
    order.total_ngwee = subtotal - discount
    order.vat_ngwee = round(vat_total * (order.total_ngwee / subtotal)) if subtotal else 0

    db.flush()
    return order


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
    if settings.DEMO_ENABLED and db.scalar(select(DemoCheckout.token).where(DemoCheckout.order_id == found.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Use the customer demo to simulate payment for this order.")
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
    if body.method in ("airtel", "mtn", "zamtel", "card") and not body.reference.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Enter the transaction number from the payment, so it can be matched later.",
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
    )
    db.add(payment)
    db.flush()
    # The order's loaded payments do not include the row just added, so the
    # totals have to be read again before deciding whether it is settled.
    db.refresh(found)

    if found.outstanding_ngwee <= 0:
        found.status = "paid"
        found.paid_at = datetime.now(timezone.utc)
        # Paid means the kitchen can start: the board is written here rather
        # than being polled for new orders.
        if send_to_kitchen(db, found):
            announce("new", {"order_number": found.number})
        # What the order used leaves stock here, from the recipes behind it.
        take_stock_for_order(db, found)
        # And the books follow the money and the food in the same breath.
        _post_books(db, found)

    _remember(db, idempotency_key, "payment", payment.id)
    record(db, user.name, "money", "Payment taken",
           f"{found.number}, {METHOD_LABELS[body.method]} {body.amount_ngwee} ngwee", found.number)
    db.commit()
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
    user: User = Depends(can_cancel),
):
    """Gives money back without touching the original payment row."""
    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    if settings.DEMO_ENABLED and db.scalar(select(DemoCheckout.token).where(DemoCheckout.order_id == found.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Use the customer demo to simulate payment for this order.")
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
           f"{found.number}, {body.amount_ngwee} ngwee: {body.reason.strip()}", found.number)
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
    if settings.DEMO_ENABLED and db.scalar(select(DemoCheckout.token).where(DemoCheckout.order_id == found.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Use the customer demo to simulate payment for this order.")
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
        select(Payment).where(Payment.created_at >= start, Payment.created_at < end)
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
def receipt(order_id: str, request: Request, db: Session = Depends(get_db), _: User = Depends(can_view)):
    """Everything a printed receipt needs, already worded and in order."""
    found = db.get(Order, order_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found.")
    when = (found.paid_at or found.created_at).astimezone(LUSAKA)
    from app.api.v1.settings_api import business_settings

    business = business_settings(db)
    return {
        "business": business["business_name"] or settings.BUSINESS_NAME,
        "address": business["business_address"],
        "phone": business["business_phone"],
        "tpin": business["business_tpin"],
        "vat_number": business["business_vat_number"],
        "number": found.number,
        "at": when.strftime("%d %b %Y, %H:%M"),
        "served_by": found.created_by,
        "order_type": {"takeaway": "Takeaway", "eat_in": "Eat in", "delivery": "Delivery"}[found.order_type],
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
        "footer": business["receipt_footer"],
    }
