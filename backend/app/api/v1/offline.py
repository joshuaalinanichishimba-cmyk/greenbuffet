"""Cash sales the till took while it could not reach the server.

When the network or the server drops, the till keeps selling for cash. Each
sale is kept on that device with an id made before anything is sent, then
sent here once the server can be reached again. This file turns each one into
an ordinary paid order: kitchen, stock, books and the till's cash all follow,
exactly as if it had been sent at the time.

The rules that make this safe:

- One id is one sale. Sending it again, from a retry or a second tab, gives
  back the same order. The database holds a unique index on the id as well.
- Cash only, no discounts, promotion codes or stamp cards. Those need the
  server to decide, so the till does not offer them while offline.
- The server prices the order again from its own menu. If today's price is
  different from what the till charged, the money the customer paid stands:
  a higher price is written off as an "offline price" difference, a lower one
  is recorded as cash taken over the price. Either way the owners are told,
  and nothing is changed quietly.
- The sale belongs to the person who took it, on the till they had open. A
  sale arriving after that till was closed still goes on it (that is where
  the cash went) and the owners are told, because the count did not know.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.kitchen import announce, send_to_kitchen
from app.api.v1.sales import _next_number, _order_out, _post_books, can_sell
from app.api.v1.stock import take_stock_for_order
from app.core.database import get_db
from app.models.access import User
from app.models.kitchen import KitchenItem
from app.models.sales import ORDER_TYPES, Order, Payment, Shift
from app.schemas.sales import OrderLineIn, OrderOut
from app.services.accounts import LUSAKA, local_time, notify_owners
from app.services.audit import record
from app.services.ordering import OrderProblem, apply_totals, build_lines

router = APIRouter(prefix="/sales/offline", tags=["sales"])

# Food that was cooked from the printed receipt long ago should not appear
# on the board as new. A sale this recent still goes to the kitchen as normal.
KITCHEN_WINDOW = timedelta(minutes=20)
# How far back a sale may be. A device left in a drawer for a month is a
# question for a manager, not something to post into a closed month quietly.
OLDEST = timedelta(days=7)
# The till's clock may run a little ahead of the server's.
CLOCK_SLACK = timedelta(minutes=10)


class OfflineSaleIn(BaseModel):
    id: str = Field(min_length=16, max_length=36, pattern=r"^[0-9a-fA-F-]+$")
    taken_at: datetime
    shift_id: str = Field(min_length=1, max_length=32)
    # The short number printed on the customer's receipt, such as "T-4".
    receipt_number: str = Field(default="", max_length=16)
    lines: list[OrderLineIn] = Field(min_length=1)
    order_type: str = "takeaway"
    customer_name: str = Field(default="", max_length=80)
    note: str = Field(default="", max_length=300)
    # What the till charged and what the customer handed over.
    charged_ngwee: int = Field(gt=0, le=1_000_000_000)
    tendered_ngwee: int | None = Field(default=None, ge=0, le=1_000_000_000)


class OfflineSaleOut(BaseModel):
    order: OrderOut
    # True when this id had already been recorded: nothing new was done.
    already: bool = False
    # Plain sentences for anything that did not line up, shown on the till.
    notes: list[str] = []


def _ngwee(value: int) -> str:
    return f"K{value / 100:,.2f}"


@router.post("/sales", response_model=OfflineSaleOut)
def record_offline_sale(body: OfflineSaleIn, db: Session = Depends(get_db), user: User = Depends(can_sell)):
    existing = db.scalar(select(Order).where(Order.offline_id == body.id.lower()))
    if existing:
        return OfflineSaleOut(order=_order_out(existing), already=True)

    taken_at = body.taken_at if body.taken_at.tzinfo else body.taken_at.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    if taken_at > now + CLOCK_SLACK:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "This sale is dated in the future. Check the date and time on this device.")
    if taken_at < now - OLDEST:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "This sale is more than a week old. A manager needs to enter it by hand.")
    if body.order_type not in ORDER_TYPES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown order type.")
    if body.tendered_ngwee is not None and body.tendered_ngwee < body.charged_ngwee:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "The cash given is less than the amount charged.")

    shift = db.get(Shift, body.shift_id)
    if not shift or shift.opened_by_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "This sale was taken on someone else's till. They send it when they next sign in.")

    notes: list[str] = []
    late = shift.closed_at is not None

    order = Order(
        number=_next_number(db), shift_id=shift.id, order_type=body.order_type,
        customer_name=body.customer_name.strip(), customer_phone="",
        note=body.note.strip(), created_by=user.name, status="open",
        offline_id=body.id.lower(), offline_taken_at=taken_at, offline_synced_at=now,
    )
    db.add(order)
    db.flush()
    try:
        priced = build_lines(db, order, body.lines, already_sold=True)
    except OrderProblem as problem:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"{problem.message} A manager needs to enter this sale by hand.")

    # The customer paid what the till asked. If the menu says more now, the
    # difference is written off and labelled; if it says less, the order is
    # priced as the menu says and the extra cash is named, so the drawer and
    # the books still agree.
    server_total = priced.subtotal_ngwee
    gap = server_total - body.charged_ngwee
    if gap > 0:
        apply_totals(order, priced, discount_ngwee=gap)
        order.discount_reason = "Offline sale: charged at the price this till had"
        notes.append(f"Today's menu prices this at {_ngwee(server_total)}; the till charged "
                     f"{_ngwee(body.charged_ngwee)}. The {_ngwee(gap)} difference is recorded as an offline price difference.")
    else:
        apply_totals(order, priced)
        if gap < 0:
            notes.append(f"Today's menu prices this at {_ngwee(server_total)}; the till charged "
                         f"{_ngwee(body.charged_ngwee)}. The drawer holds {_ngwee(-gap)} more than the sale.")
    amount = order.total_ngwee
    change = (body.tendered_ngwee - body.charged_ngwee) if body.tendered_ngwee is not None else None
    if body.receipt_number:
        order.note = (f"Offline receipt {body.receipt_number.strip()}. " + order.note).strip()[:300]

    order.created_at = taken_at
    payment = Payment(
        order_id=order.id, shift_id=shift.id, method="cash", amount_ngwee=amount,
        tendered_ngwee=body.tendered_ngwee, change_ngwee=change, reference="",
        note=(f"Offline sale; {_ngwee(-gap)} over today's price" if gap < 0 else "Offline sale")[:200],
        created_by=user.name, status="confirmed", confirmed_by=user.name, confirmed_at=taken_at,
    )
    if amount > 0:
        db.add(payment)
    db.flush()
    db.refresh(order)
    order.status = "paid"
    order.paid_at = taken_at

    # The kitchen: a sale from the last few minutes is cooked from the board
    # as usual. An older one was cooked from the printed receipt, so its
    # tickets are written as already served; the board stays clear and the
    # record still shows what was made.
    recent = now - taken_at <= KITCHEN_WINDOW
    tell_kitchen = send_to_kitchen(db, order) > 0
    if not recent:
        tell_kitchen = False
        db.flush()
        for item in db.scalars(select(KitchenItem).where(KitchenItem.order_id == order.id)).all():
            item.status, item.served_at, item.handled_by = "served", taken_at, "offline sale"
    take_stock_for_order(db, order)
    # The books take the day the customer paid, not the day the network came back.
    _post_books(db, order, taken_at.astimezone(LUSAKA).date())

    if late:
        notes.append(f"Your till was closed at {local_time(shift.closed_at)} before this sale arrived. "
                     "It is added to that till, and the owners are told.")

    record(db, user.name, "money", "Offline sale recorded",
           f"{order.number}: {_ngwee(amount)} cash, taken {local_time(taken_at)}"
           + (f", receipt {body.receipt_number}" if body.receipt_number else "")
           + (f"; {' '.join(notes)}" if notes else ""), order.number,
           after={"offline_id": order.offline_id, "charged": body.charged_ngwee, "priced": server_total,
                  "late": late})
    if gap or late:
        notify_owners(db, "offline_sales", f"Offline sale {order.number} needs a look",
                      " ".join(notes), link="/orders", level="warning")
    try:
        db.commit()
    except IntegrityError:
        # The same id sent twice at once: the other request saved it first.
        db.rollback()
        existing = db.scalar(select(Order).where(Order.offline_id == body.id.lower()))
        if existing:
            return OfflineSaleOut(order=_order_out(existing), already=True)
        raise
    if tell_kitchen:
        announce("new", {"order_number": order.number})
    db.refresh(order)
    return OfflineSaleOut(order=_order_out(order), notes=notes)


class OfflineStatusOut(BaseModel):
    # What the till needs to keep selling without the server.
    shift_id: str | None
    user_id: str
    user_name: str
    server_time: str


@router.get("/ready", response_model=OfflineStatusOut)
def offline_ready(db: Session = Depends(get_db), user: User = Depends(can_sell)):
    """Read by the till each time it loads, so it knows whose till is open
    should the network drop a minute later."""
    shift = db.scalar(select(Shift).where(Shift.opened_by_id == user.id, Shift.closed_at.is_(None))
                      .order_by(Shift.opened_at.desc()))
    return OfflineStatusOut(shift_id=shift.id if shift else None, user_id=user.id, user_name=user.name,
                            server_time=datetime.now(timezone.utc).isoformat())
