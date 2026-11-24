"""Promotion codes, worked out on the server.

The till sends a code; it never sends what the code is worth. That is decided
here, from the code's own row, so a cashier cannot type a bigger discount and
a code that has been stopped stops working at every till at once.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.business import Promotion


def find_code(db: Session, code: str) -> Promotion | None:
    return db.scalar(select(Promotion).where(Promotion.code == code.strip().upper()))


def promo_discount(db: Session, code: str, food_ngwee: int) -> int:
    """What this code takes off an order of this size. Raises if it cannot apply."""
    promo = find_code(db, code)
    if not promo:
        raise ValueError(f"There is no promotion called {code.strip().upper()}.")
    if not promo.is_active:
        raise ValueError(f"{promo.code} has been stopped.")
    if food_ngwee < promo.minimum_ngwee:
        raise ValueError(f"{promo.code} needs an order of at least K{promo.minimum_ngwee / 100:,.2f}.")
    if promo.kind == "percent":
        off = round(food_ngwee * promo.value / 100)
    else:
        off = promo.value
    return max(0, min(off, food_ngwee))


def count_promo_use(db: Session, code: str, discount_ngwee: int) -> None:
    promo = find_code(db, code)
    if promo:
        promo.uses += 1
        promo.discount_given_ngwee += discount_ngwee
