"""Public, simulated ordering in the separately configured demonstration database."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.v1.kitchen import board, send_to_kitchen
from app.api.v1.sales import _post_books, build_order
from app.api.v1.stock import take_stock_for_order
from app.core.database import get_db
from app.models.demo import DemoCheckout
from app.models.kitchen import KitchenItem, STATUSES
from app.models.menu import Category, Product
from app.models.sales import Order, Payment
from app.schemas.sales import OrderIn, OrderLineIn
from app.services.audit import record

router = APIRouter(prefix="/demo", tags=["demo"])
ACTOR = "Demo checkout"
PaymentState = Literal["initiated", "pending", "successful", "failed"]


class CheckoutIn(BaseModel):
    lines: list[OrderLineIn] = Field(min_length=1, max_length=20)


class SimulationIn(BaseModel):
    outcome: Literal["pending", "successful", "failed"]


class Tracker(BaseModel):
    order_number: str
    total_ngwee: int
    payment: PaymentState
    kitchen: str | None


def get_checkout(db: Session, token: UUID) -> tuple[DemoCheckout, Order]:
    checkout = db.get(DemoCheckout, token.hex)
    if checkout is None:
        raise HTTPException(404, "Demo order not found.")
    return checkout, db.get_one(Order, checkout.order_id)


def tracking(db: Session, checkout: DemoCheckout, order: Order) -> Tracker:
    statuses = db.scalars(select(KitchenItem.status).where(KitchenItem.order_id == order.id)).all()
    kitchen = min(statuses, key=STATUSES.index) if statuses else None
    return Tracker(
        order_number=order.number, total_ngwee=order.total_ngwee, payment=checkout.payment_state,
        kitchen="cancelled" if order.status == "cancelled" else kitchen,
    )


def lock_checkout(db: Session, token: UUID) -> None:
    # Serialize creation and payment retries for the same token.
    db.execute(text("select pg_advisory_xact_lock(:key)"), {"key": int.from_bytes(token.bytes[:8], "big", signed=True)})


@router.get("/menu")
def menu(db: Session = Depends(get_db)):
    products = db.scalars(
        select(Product).join(Category).where(Category.is_active, Product.is_active)
        .order_by(Category.sort, Product.sort, Product.name)
    ).all()
    return [
        dict(
            id=p.id, code=p.code, name=p.name, description=p.description, category=p.category.name,
            price_ngwee=p.price_ngwee, available=p.is_available,
            groups=[
                dict(
                    id=g.id, name=g.name, min=g.min_select, max=g.max_select,
                    items=[
                        dict(id=i.id, name=i.name, price_ngwee=i.price_ngwee, available=i.is_available)
                        for i in g.items if i.is_active
                    ],
                )
                for g in (link.group for link in sorted(p.option_links, key=lambda link: link.sort))
                if g.is_active
            ],
        )
        for p in products
    ]


@router.put("/orders/{token}", response_model=Tracker)
def create(token: UUID, body: CheckoutIn, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    lock_checkout(db, token)
    existing = db.get(DemoCheckout, token.hex)
    if existing:
        return tracking(db, existing, db.get_one(Order, existing.order_id))
    for line in body.lines:
        product = db.get(Product, line.product_id)
        if not product or not product.category.is_active:
            raise HTTPException(422, "That item is not on the demo menu.")
        if line.quantity > 20 or len(line.options) > 30:
            raise HTTPException(422, "This demo order has too many items or choices.")
        if len({option.option_item_id for option in line.options}) != len(line.options):
            raise HTTPException(422, "Select each choice only once.")
        offered = {item.id for link in product.option_links if link.group.is_active for item in link.group.items}
        if any(option.option_item_id not in offered for option in line.options):
            raise HTTPException(422, "That choice is not offered with this item.")
    order = build_order(db, OrderIn(lines=body.lines, customer_name="Demo guest"), ACTOR)
    checkout = DemoCheckout(token=token.hex, order_id=order.id, payment_state="initiated")
    db.add(checkout)
    record(db, ACTOR, "sales", "Demo checkout initiated", order.number, order.number)
    db.commit()
    return tracking(db, checkout, order)


@router.get("/orders/{token}", response_model=Tracker)
def track(token: UUID, response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return tracking(db, *get_checkout(db, token))


@router.put("/orders/{token}/payment", response_model=Tracker)
def simulate(token: UUID, body: SimulationIn, response: Response, background: BackgroundTasks, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    lock_checkout(db, token)
    checkout, order = get_checkout(db, token)
    # The staff workflow can cancel an open order. Read and lock it before paying.
    db.refresh(order, with_for_update=True)
    if checkout.payment_state in ("successful", "failed"):
        if checkout.payment_state != body.outcome:
            raise HTTPException(409, "This simulation is already complete.")
        return tracking(db, checkout, order)
    if order.status != "open" or order.payments:
        raise HTTPException(409, "This demo order was already handled by staff.")
    checkout.payment_state = body.outcome
    if body.outcome == "successful":
        db.add(Payment(order_id=order.id, method="simulated", amount_ngwee=order.total_ngwee, created_by=ACTOR))
        order.status = "paid"
        order.paid_at = datetime.now(timezone.utc)
        db.flush()
        db.refresh(order)
        send_to_kitchen(db, order)
        take_stock_for_order(db, order)
        _post_books(db, order)
    elif body.outcome == "failed":
        order.status = "cancelled"
        order.cancelled_at = datetime.now(timezone.utc)
        order.cancelled_by = ACTOR
        order.cancel_reason = "Simulated payment failed"
    record(db, ACTOR, "money", f"Simulated payment {body.outcome}", order.number, order.number)
    db.commit()
    if body.outcome == "successful":
        background.add_task(board.tell_everyone, {"event": "new", "order_number": order.number})
    return tracking(db, checkout, order)
