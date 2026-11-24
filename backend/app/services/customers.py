"""Finding and remembering customers.

A customer record is created the first time someone gives a phone number,
whether that happens at the counter or on the website. Nothing is asked for
beyond the number and a name: a restaurant does not need a date of birth to
sell somebody nshima, and every extra field is one more thing to get wrong.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customers import Customer, normalise_phone


def find_customer(db: Session, phone: str) -> Customer | None:
    cleaned = normalise_phone(phone)
    if not cleaned:
        return None
    return db.scalar(select(Customer).where(Customer.phone == cleaned))


def find_or_make_customer(db: Session, phone: str, name: str = "", area: str = "") -> Customer | None:
    """Returns the customer for this number, creating them if they are new."""
    cleaned = normalise_phone(phone)
    if not cleaned:
        return None
    customer = db.scalar(select(Customer).where(Customer.phone == cleaned))
    if customer:
        # A name given later fills in a blank, but never overwrites one the
        # customer or a manager has already corrected.
        if name and not customer.name:
            customer.name = name.strip()[:80]
        if area and not customer.area:
            customer.area = area.strip()[:80]
        return customer
    customer = Customer(phone=cleaned, name=name.strip()[:80], area=area.strip()[:80])
    db.add(customer)
    db.flush()
    return customer
