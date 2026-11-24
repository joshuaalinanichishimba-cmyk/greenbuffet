"""Customers and their stamp cards, looked up at the till.

The Green Buffet is a point of sale: customers order at the counter, not
online. So this is all that is left of the customer stages: finding a
regular by phone number, their stamp card, and putting a card right.
Deliveries, delivery areas, functions and the message outbox were removed
in stage 20; their tables stay in the database untouched, so no history is
lost.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import User
from app.models.customers import Customer, PointsEntry, normalise_phone
from app.schemas.customers import CustomerOut, CustomerUpdateIn, PointsAdjustIn, PointsEntryOut
from app.services.audit import record
from app.services.loyalty import record as record_stamps, stamps_needed

router = APIRouter(prefix="/customers", tags=["customers"])

can_serve = requires("customers.view", "pos.use", "orders.view")
# Stamps are money, so putting a card right is a manager's decision.
can_manage_customers = requires("customers.manage")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _customer_out(c: Customer, needed: int = 8) -> CustomerOut:
    return CustomerOut(
        id=c.id, phone=c.phone, name=c.name, email=c.email, area=c.area, address=c.address,
        note=c.note, stamps=c.stamps, stamps_needed=needed, free_ready=c.stamps >= needed,
        orders_count=c.orders_count, spent_ngwee=c.spent_ngwee,
        last_order_at=c.last_order_at.isoformat() if c.last_order_at else "",
    )


@router.get("", response_model=list[CustomerOut])
def customers(
    search: str = Query(default="", max_length=60),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(can_serve),
):
    stmt = select(Customer).order_by(Customer.last_order_at.desc().nullslast()).limit(limit)
    term = search.strip()
    if term:
        digits = normalise_phone(term)
        stmt = select(Customer).where(or_(
            Customer.name.ilike(f"%{term}%"),
            Customer.phone.like(f"%{digits or term}%"),
        )).limit(limit)
    needed = stamps_needed(db)
    return [_customer_out(c, needed) for c in db.scalars(stmt).all()]


@router.get("/by-phone/{phone}", response_model=CustomerOut)
def customer_by_phone(phone: str, db: Session = Depends(get_db), _: User = Depends(can_serve)):
    """The till's lookup: a number typed at the counter finds the stamp card."""
    customer = db.scalar(select(Customer).where(Customer.phone == normalise_phone(phone)))
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No customer with that number yet.")
    return _customer_out(customer, stamps_needed(db))


@router.patch("/{customer_id}", response_model=CustomerOut)
def update_customer(
    customer_id: str, body: CustomerUpdateIn,
    db: Session = Depends(get_db), user: User = Depends(can_manage_customers),
):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found.")
    for field in ("name", "email", "area", "address", "note"):
        value = getattr(body, field)
        if value is not None:
            setattr(customer, field, value.strip())
    db.commit()
    db.refresh(customer)
    return _customer_out(customer, stamps_needed(db))


@router.get("/{customer_id}/stamps", response_model=list[PointsEntryOut])
def stamps_history(customer_id: str, db: Session = Depends(get_db), _: User = Depends(can_serve)):
    entries = db.scalars(
        select(PointsEntry).where(PointsEntry.customer_id == customer_id)
        .order_by(PointsEntry.created_at.desc()).limit(100)
    ).all()
    return [
        PointsEntryOut(
            points=e.points, balance_after=e.balance_after, reason=e.reason,
            at=e.created_at.isoformat() if e.created_at else "", by=e.created_by or "",
        )
        for e in entries
    ]


@router.post("/{customer_id}/stamps", response_model=CustomerOut)
def adjust_stamps(
    customer_id: str, body: PointsAdjustIn,
    db: Session = Depends(get_db), user: User = Depends(can_manage_customers),
):
    """A manager correcting a stamp card, with the reason recorded beside it."""
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found.")
    if not body.reason.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Say why the card is being changed.")
    if body.points == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "That would change nothing.")
    record_stamps(db, customer, body.points, body.reason.strip(), who=user.name)
    record(db, user.name, "sales", "Stamps adjusted",
           f"{customer.phone} {body.points:+d}: {body.reason.strip()}", customer.id)
    db.commit()
    db.refresh(customer)
    return _customer_out(customer, stamps_needed(db))


@router.get("/stamps/rules")
def stamps_rules(db: Session = Depends(get_db), _: User = Depends(can_serve)):
    """What the scheme is, so the screen and the wall sheet never disagree."""
    needed = stamps_needed(db)
    return {
        "stamps_needed": needed,
        "summary": f"Every paid bowl or burrito earns a stamp. Collect {needed} and the next one is free.",
    }
