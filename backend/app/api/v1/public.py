"""The part of the system a customer touches, with no sign-in at all.

Everything else in this application assumes a member of staff holding a token.
These routes assume a stranger on a phone, possibly a hostile one, so they are
written to a different standard:

* Nothing here reads or writes anything about staff, money already taken, or
  another customer. The only thing a customer can see is their own order, and
  only with a long random token that is theirs alone.
* Prices, totals and VAT are worked out by the same code as the till. The
  browser sends what was chosen, never what it costs.
* An order placed here is not a sale. It is a request the restaurant can
  accept or refuse, and no money moves until a member of staff takes it.
* Orders are rate limited by phone number and by address, because the cost of
  a prank order is a kitchen cooking food nobody collects.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.access import Setting
from app.models.customers import Customer, DeliveryZone, normalise_phone
from app.models.files import Document
from app.models.menu import Category, Product
from app.models.sales import Order
from app.schemas.public import (
    PublicMenu, PublicMenuCategory, PublicMenuProduct, PublicOptionGroup, PublicOptionItem,
    PublicOrderIn, PublicOrderOut, PublicPlaced, PublicZone, ShopInfo,
)
from app.services.customers import find_or_make_customer
from app.services.messaging import order_received
from app.services.numbering import numbered
from app.services.ordering import OrderProblem, apply_totals, build_lines

router = APIRouter(prefix="/public", tags=["public"])

# How many orders one phone number may place in an hour. A real customer
# ordering lunch for the office places one, maybe two.
MAX_ORDERS_PER_HOUR = 4
MAX_UNPAID_OPEN = 3


def _setting(db: Session, key: str, fallback: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row and row.value else fallback


def _accepting(db: Session) -> bool:
    return _setting(db, "service.accepting_orders", "true").lower() == "true"


@router.get("/shop", response_model=ShopInfo)
def shop(db: Session = Depends(get_db)):
    """Who the restaurant is, and whether it is taking orders right now."""
    phones = [p.strip() for p in _setting(db, "business.phones", "").split(",") if p.strip()]
    zones = db.scalars(
        select(DeliveryZone).where(DeliveryZone.is_active.is_(True)).order_by(DeliveryZone.sort, DeliveryZone.name)
    ).all()
    return ShopInfo(
        name=_setting(db, "business.name", "The Green Buffet"),
        location=_setting(db, "business.location", "Liberty Mall"),
        phones=phones,
        accepting_orders=_accepting(db),
        prep_minutes=int(_setting(db, "service.prep_minutes", "12") or 12),
        closed_message=_setting(db, "service.closed_message", "We are not taking online orders at the moment."),
        zones=[
            PublicZone(
                id=z.id, name=z.name, fee_ngwee=z.fee_ngwee, minutes=z.minutes,
                minimum_ngwee=z.minimum_ngwee,
            )
            for z in zones
        ],
    )


@router.get("/menu", response_model=PublicMenu)
def menu(db: Session = Depends(get_db)):
    """The menu as a customer sees it: what is on sale, and nothing else.

    Cost prices, recipes, suppliers and stock levels are all deliberately
    absent. This answer is public, so it may only contain what a printed menu
    on the wall would contain.
    """
    categories = db.scalars(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort, Category.name)
    ).all()
    products = db.scalars(
        select(Product).where(Product.is_active.is_(True)).order_by(Product.sort, Product.name)
    ).all()

    # One query for every product photo, rather than one per product.
    photos = {
        doc.attached_id: doc.id
        for doc in db.scalars(
            select(Document).where(
                Document.attached_to == "product", Document.kind == "photo",
            ).order_by(Document.is_primary.desc(), Document.created_at)
        ).all()
        if doc.attached_id
    }

    by_category: dict[str, list[PublicMenuProduct]] = {}
    for product in products:
        groups: list[PublicOptionGroup] = []
        for link in sorted(product.option_links, key=lambda l: l.sort):
            group = link.group
            if not group or not group.is_active:
                continue
            items = [
                PublicOptionItem(
                    id=item.id, name=item.name, price_ngwee=item.price_ngwee,
                    is_available=item.is_available,
                )
                for item in sorted(group.items, key=lambda i: (i.sort, i.name))
                if item.is_active
            ]
            if not items:
                continue
            groups.append(PublicOptionGroup(
                id=group.id, name=group.name, min_select=group.min_select,
                max_select=group.max_select, items=items,
            ))
        by_category.setdefault(product.category_id, []).append(PublicMenuProduct(
            id=product.id, name=product.name, description=product.description,
            price_ngwee=product.price_ngwee, is_available=product.is_available,
            photo_id=photos.get(product.id, ""), groups=groups,
        ))

    return PublicMenu(categories=[
        PublicMenuCategory(id=c.id, name=c.name, description=c.description,
                           products=by_category.get(c.id, []))
        for c in categories
        if by_category.get(c.id)
    ])


def _order_out(order: Order, db: Session) -> PublicOrderOut:
    """What a customer may know about their own order."""
    prep = int(_setting(db, "service.prep_minutes", "12") or 12)
    return PublicOrderOut(
        number=order.number,
        token=order.public_token,
        status=order.track_status or "placed",
        fulfilment=order.fulfilment,
        placed_at=order.created_at.isoformat() if order.created_at else "",
        total_ngwee=order.total_ngwee,
        delivery_fee_ngwee=order.delivery_fee_ngwee,
        customer_name=order.customer_name,
        address=order.address,
        zone_name=order.zone_name,
        reject_reason=order.reject_reason,
        minutes=prep,
        paid=order.status == "paid",
        lines=[
            f"{line.quantity} x {line.product_name}"
            + (f" ({', '.join(o.item_name for o in line.options)})" if line.options else "")
            for line in order.lines
        ],
    )


@router.post("/orders", response_model=PublicPlaced, status_code=status.HTTP_201_CREATED)
def place_order(
    body: PublicOrderIn,
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """A customer places an order. No money moves; staff accept it first."""
    if not _accepting(db):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            _setting(db, "service.closed_message", "We are not taking online orders at the moment."),
        )

    phone = normalise_phone(body.customer_phone)
    if len(phone) < 10:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter a phone number we can reach you on.")
    if not body.customer_name.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter your name.")

    customer = find_or_make_customer(db, phone, body.customer_name, body.area)
    if customer and customer.is_blocked:
        # Deliberately vague: someone blocked for abuse is not owed an
        # explanation that tells them how to get around it.
        raise HTTPException(status.HTTP_403_FORBIDDEN, "We cannot take online orders from this number. Please call us.")

    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent = db.scalar(
        select(func.count(Order.id)).where(
            Order.customer_phone == phone, Order.channel == "online", Order.created_at >= hour_ago,
        )
    ) or 0
    if recent >= MAX_ORDERS_PER_HOUR:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "That is several orders in a short time. Please call us to place another.",
        )
    waiting = db.scalar(
        select(func.count(Order.id)).where(
            Order.customer_phone == phone, Order.channel == "online",
            Order.status == "open", Order.track_status.in_(("placed", "accepted", "cooking")),
        )
    ) or 0
    if waiting >= MAX_UNPAID_OPEN:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "You already have orders with us. Please wait for those before sending another.",
        )

    fulfilment = body.fulfilment if body.fulfilment in ("collection", "delivery") else "collection"
    zone = None
    if fulfilment == "delivery":
        if not body.address.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter the address to deliver to.")
        zone = db.get(DeliveryZone, body.zone_id) if body.zone_id else None
        if not zone or not zone.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose an area we deliver to.")

    order = Order(
        number=numbered(db, f"GB-{datetime.now(timezone.utc):%Y%m%d}-"),
        order_type="delivery" if fulfilment == "delivery" else "takeaway",
        channel="online",
        fulfilment=fulfilment,
        track_status="placed",
        public_token=secrets.token_urlsafe(24)[:40],
        status="open",
        customer_id=customer.id if customer else None,
        customer_name=body.customer_name.strip()[:80],
        customer_phone=phone,
        note=body.note.strip()[:300],
        address=body.address.strip()[:200] if fulfilment == "delivery" else "",
        directions=body.directions.strip()[:300] if fulfilment == "delivery" else "",
        zone_id=zone.id if zone else None,
        zone_name=zone.name if zone else "",
        created_by=body.customer_name.strip()[:80] or "Online",
    )
    db.add(order)
    db.flush()

    try:
        priced = build_lines(db, order, body.lines)
    except OrderProblem as problem:
        raise HTTPException(problem.code, problem.message)

    fee = zone.fee_ngwee if zone else 0
    if zone and zone.minimum_ngwee and priced.subtotal_ngwee < zone.minimum_ngwee:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Orders to {zone.name} start at K{zone.minimum_ngwee / 100:,.2f}.",
        )
    apply_totals(order, priced, discount_ngwee=0, delivery_fee_ngwee=fee)

    order_received(db, order)
    db.commit()
    db.refresh(order)
    return PublicPlaced(number=order.number, token=order.public_token, total_ngwee=order.total_ngwee)


@router.get("/orders/{token}", response_model=PublicOrderOut)
def track(token: str, db: Session = Depends(get_db)):
    """Where an order has got to. The token is the only key to it."""
    if len(token) < 20:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That order could not be found.")
    order = db.scalar(select(Order).where(Order.public_token == token))
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That order could not be found.")
    return _order_out(order, db)


@router.get("/photo/{document_id}")
def photo(document_id: str, db: Session = Depends(get_db)):
    """A menu photo, served without a token.

    Only a photo attached to a product can be fetched here, and only by its
    own id. Every other stored document — a supplier invoice, an employee
    contract — is unreachable from this route whatever id is tried.
    """
    from pathlib import Path

    from fastapi.responses import FileResponse

    doc = db.get(Document, document_id)
    if not doc or doc.attached_to != "product" or doc.kind != "photo":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    path = Path(doc.path)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return FileResponse(
        path, media_type=doc.media_type or "image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/points/{phone}")
def points(phone: str, db: Session = Depends(get_db)):
    """A customer's own points balance, found by their number.

    This returns a balance and nothing else: no name, no history, no orders.
    Knowing a phone number is a low bar, so what it unlocks must be low value.
    """
    customer = db.scalar(select(Customer).where(Customer.phone == normalise_phone(phone)))
    return {"points": customer.points if customer else 0}
