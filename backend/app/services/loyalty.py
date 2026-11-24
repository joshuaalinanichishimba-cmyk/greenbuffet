"""Loyalty stamps, as the demo proposes them.

"Your 9th bowl is on us." Every bowl or burrito that is paid for earns one
stamp. When a card is full (eight stamps by default, set in Settings) the next
bowl or burrito is free, and the till applies it by itself.

The rules are deliberately the ones a cashier can explain without a screen:

* Only items from a menu section marked as earning stamps count: bowls and
  burritos, not dips or drinks.
* A stamp is earned when the order is paid for, never when it is typed. An
  order that is cancelled earns nothing.
* The free item is the cheapest qualifying item on the order, so a customer
  with a full card who orders two bowls gets the smaller one free.
* The full card is taken when the order is made, so it cannot be spent twice
  on two orders at once, and given back if that order is cancelled.

Every change is written to a ledger as well as to the balance, so when a
customer says their card is wrong there is a list to read back to them.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.access import Setting
from app.models.customers import Customer, PointsEntry
from app.models.menu import Product

DEFAULT_STAMPS_NEEDED = 8


def stamps_needed(db: Session) -> int:
    row = db.get(Setting, "loyalty.stamps_needed")
    try:
        value = int(row.value) if row and row.value else DEFAULT_STAMPS_NEEDED
    except ValueError:
        value = DEFAULT_STAMPS_NEEDED
    return max(1, value)


def loyalty_on(db: Session) -> bool:
    row = db.get(Setting, "loyalty.enabled")
    return (row.value if row else "true").lower() == "true"


def record(
    db: Session,
    customer: Customer,
    stamps: int,
    reason: str,
    order_id: str | None = None,
    who: str | None = None,
) -> PointsEntry | None:
    """Moves a customer's card and writes the reason down."""
    if stamps == 0:
        return None
    customer.stamps = max(0, customer.stamps + stamps)
    entry = PointsEntry(
        customer_id=customer.id, order_id=order_id, points=stamps,
        balance_after=customer.stamps, reason=reason[:120], created_by=who,
    )
    db.add(entry)
    return entry


def _qualifying_units(db: Session, order) -> list[int]:
    """The price of every single bowl or burrito on the order, one per unit."""
    units: list[int] = []
    for line in order.lines:
        product = db.get(Product, line.product_id)
        if not product or not product.category or not product.category.earns_stamp:
            continue
        each = line.unit_ngwee + line.options_ngwee
        units.extend([each] * line.quantity)
    return units


def free_item_for(db: Session, customer: Customer | None, order) -> int:
    """If this customer's card is full, takes it and returns the free amount.

    Called when the order is made, after its lines are priced. Returns the
    ngwee to take off, or 0.
    """
    if not customer or not loyalty_on(db):
        return 0
    needed = stamps_needed(db)
    if customer.stamps < needed:
        return 0
    units = _qualifying_units(db, order)
    if not units:
        return 0
    free = min(units)
    record(db, customer, -needed, f"Free item on {order.number}", order_id=order.id, who=order.created_by)
    order.stamps_redeemed = needed
    order.free_item_ngwee = free
    return free


def earn_on_order(db: Session, customer: Customer, order, who: str | None = None) -> int:
    """Stamps for a paid order. Returns how many were given."""
    if not loyalty_on(db) or order.stamps_earned:
        return 0
    units = _qualifying_units(db, order)
    # The free item does not earn a stamp of its own.
    earned = max(0, len(units) - (1 if order.free_item_ngwee else 0))
    customer.orders_count += 1
    customer.spent_ngwee += order.total_ngwee
    customer.last_order_at = datetime.now(timezone.utc)
    if earned <= 0:
        return 0
    order.stamps_earned = earned
    record(db, customer, earned, f"Order {order.number}", order_id=order.id, who=who)
    return earned


def give_back_on_cancel(db: Session, customer: Customer | None, order, who: str | None = None) -> None:
    """A cancelled order returns the full card it used."""
    if customer and order.stamps_redeemed:
        record(db, customer, order.stamps_redeemed, f"Card returned, {order.number} cancelled",
               order_id=order.id, who=who)
        order.stamps_redeemed = 0
