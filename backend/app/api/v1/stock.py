"""Stock levels, suppliers and purchases.

Stock leaves on its own as orders are paid: every paid line takes out what its
recipe says, including the recipe behind each choice the customer made. That
is why the recipes in stage 3 were worth writing properly.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import requires
from app.models.access import User
from app.models.menu import Ingredient, OptionItem, Product, RecipeLine
from app.models.sales import Order
from app.models.stock import (
    MOVE_KINDS, MOVE_LABELS, Purchase, PurchaseLine, StockLevel, StockMove, Supplier,
    SupplierPayment,
)
from app.services.audit import record
from app.services.numbering import numbered
from app.services.posting import (
    SUPPLIER_PAYMENT_ACCOUNTS, Unbalanced, post_purchase, post_supplier_payment, post_waste,
)

router = APIRouter(prefix="/stock", tags=["stock"])

can_see = requires("inventory.view", "purchases.manage", "books.view", "reports.view")
can_adjust = requires("inventory.adjust")
can_buy = requires("purchases.manage")


# ---------------------------------------------------------------------------
# shapes
# ---------------------------------------------------------------------------

class LevelOut(BaseModel):
    ingredient_id: str
    name: str
    unit: str
    quantity_milli: int
    reorder_milli: int
    cost_ngwee: int
    value_ngwee: int
    is_low: bool
    used_in: int


class AdjustIn(BaseModel):
    ingredient_id: str
    # Signed: what is being added or taken away, in thousandths of the unit.
    quantity_milli: int
    kind: str = "adjustment"
    note: str = Field(default="", max_length=200)


class CountIn(BaseModel):
    """A stocktake: what was actually on the shelf."""

    ingredient_id: str
    counted_milli: int = Field(ge=0)
    note: str = Field(default="", max_length=200)


class ReorderIn(BaseModel):
    ingredient_id: str
    reorder_milli: int = Field(ge=0)


class MoveOut(BaseModel):
    id: str
    at: str
    ingredient_id: str
    ingredient_name: str
    unit: str
    kind: str
    kind_label: str
    quantity_milli: int
    balance_milli: int
    value_ngwee: int
    reference: str
    note: str
    by: str | None


class SupplierIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    contact: str = Field(default="", max_length=80)
    phone: str = Field(default="", max_length=24)
    email: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=300)
    is_active: bool = True


class SupplierOut(SupplierIn):
    id: str
    purchases: int
    spent_ngwee: int


class PurchaseLineIn(BaseModel):
    ingredient_id: str
    quantity_milli: int = Field(gt=0)
    unit_cost_ngwee: int = Field(ge=0, le=100_000_000)


class PurchaseIn(BaseModel):
    supplier_id: str
    lines: list[PurchaseLineIn] = Field(min_length=1)
    invoice_number: str = Field(default="", max_length=40)
    note: str = Field(default="", max_length=300)


class PurchaseLineOut(BaseModel):
    id: str
    ingredient_id: str
    ingredient_name: str
    unit: str
    quantity_milli: int
    unit_cost_ngwee: int
    line_ngwee: int


class SupplierPaymentIn(BaseModel):
    method: str = "bank"
    amount_ngwee: int = Field(gt=0, le=1_000_000_000)
    reference: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=200)


class SupplierPaymentOut(BaseModel):
    id: str
    at: str
    method: str
    amount_ngwee: int
    reference: str
    note: str
    by: str | None


class OwedRow(BaseModel):
    supplier_id: str
    supplier_name: str
    phone: str
    purchases: int
    owed_ngwee: int
    oldest_days: int
    overdue_ngwee: int


class PurchaseOut(BaseModel):
    id: str
    number: str
    supplier_id: str
    supplier_name: str
    status: str
    invoice_number: str
    note: str
    total_ngwee: int
    created_at: str
    created_by: str | None
    received_at: str | None
    received_by: str | None
    lines: list[PurchaseLineOut]
    paid_ngwee: int
    owed_ngwee: int
    payments: list[SupplierPaymentOut]


# ---------------------------------------------------------------------------
# the movement ledger
# ---------------------------------------------------------------------------

def _level_row(db: Session, ingredient_id: str) -> StockLevel:
    level = db.get(StockLevel, ingredient_id)
    if not level:
        level = StockLevel(ingredient_id=ingredient_id, quantity_milli=0, reorder_milli=0)
        db.add(level)
        db.flush()
    return level


def move_stock(
    db: Session, ingredient: Ingredient, quantity_milli: int, kind: str,
    reference: str = "", note: str = "", who: str | None = None,
    unit_cost_ngwee: int | None = None,
) -> StockMove:
    """Writes one movement and keeps the cached level in step.

    Stock is allowed to go negative. A kitchen that has run out still sells the
    last bowl, and a negative figure is the honest record of that; it shows on
    the screen as something to count and correct.
    """
    level = _level_row(db, ingredient.id)
    level.quantity_milli += quantity_milli
    level.updated_at = datetime.now(timezone.utc)
    cost = ingredient.cost_ngwee if unit_cost_ngwee is None else unit_cost_ngwee
    entry = StockMove(
        ingredient_id=ingredient.id, kind=kind, quantity_milli=quantity_milli,
        value_ngwee=round(cost * quantity_milli / 1000), reference=reference,
        note=note, balance_milli=level.quantity_milli, created_by=who,
    )
    db.add(entry)
    return entry


def take_stock_for_order(db: Session, order: Order) -> int:
    """Takes out what a paid order used, from the recipes behind it.

    The product's own recipe covers what every one of them uses; each choice
    the customer made brings its own. One movement per ingredient per line, so
    the ledger reads back as "this order used this much of that".
    """
    already = db.scalar(
        select(StockMove).where(StockMove.kind == "sale", StockMove.reference == order.number)
    )
    if already:
        return 0

    used: dict[str, int] = {}
    for line in order.lines:
        product = db.get(Product, line.product_id)
        if product:
            for recipe in product.recipe:
                used[recipe.ingredient_id] = (
                    used.get(recipe.ingredient_id, 0) + recipe.quantity_milli * line.quantity
                )
        for chosen in line.options:
            item = db.get(OptionItem, chosen.option_item_id)
            if not item:
                continue
            for recipe in item.recipe:
                used[recipe.ingredient_id] = (
                    used.get(recipe.ingredient_id, 0) + recipe.quantity_milli * line.quantity
                )

    written = 0
    for ingredient_id, quantity in used.items():
        ingredient = db.get(Ingredient, ingredient_id)
        if not ingredient or quantity <= 0:
            continue
        move_stock(
            db, ingredient, -quantity, "sale", reference=order.number,
            note=f"Order {order.number}", who=order.created_by,
        )
        written += 1
    return written


# ---------------------------------------------------------------------------
# levels
# ---------------------------------------------------------------------------

@router.get("/levels", response_model=list[LevelOut])
def levels(
    low_only: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(can_see),
):
    ingredients = db.scalars(
        select(Ingredient).where(Ingredient.is_active.is_(True)).order_by(Ingredient.name)
    ).all()
    cached = {l.ingredient_id: l for l in db.scalars(select(StockLevel)).all()}
    used = dict(
        db.execute(
            select(RecipeLine.ingredient_id, func.count(RecipeLine.id)).group_by(RecipeLine.ingredient_id)
        ).all()
    )
    rows = []
    for item in ingredients:
        level = cached.get(item.id)
        quantity = level.quantity_milli if level else 0
        reorder = level.reorder_milli if level else 0
        rows.append(LevelOut(
            ingredient_id=item.id, name=item.name, unit=item.unit,
            quantity_milli=quantity, reorder_milli=reorder,
            cost_ngwee=item.cost_ngwee,
            value_ngwee=round(item.cost_ngwee * quantity / 1000),
            is_low=quantity <= reorder,
            used_in=used.get(item.id, 0),
        ))
    if low_only:
        rows = [r for r in rows if r.is_low]
    return rows


@router.post("/adjust", response_model=LevelOut)
def adjust(body: AdjustIn, db: Session = Depends(get_db), user: User = Depends(can_adjust)):
    ingredient = db.get(Ingredient, body.ingredient_id)
    if not ingredient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingredient not found.")
    if body.kind not in MOVE_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown kind of movement.")
    if body.quantity_milli == 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Enter an amount to add or take out.")
    if body.kind == "waste" and body.quantity_milli > 0:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Waste takes stock out, so it should be negative.")
    entry = move_stock(db, ingredient, body.quantity_milli, body.kind, note=body.note.strip(), who=user.name)
    if body.kind == "waste":
        try:
            post_waste(db, ingredient.name, entry.value_ngwee, f"WASTE-{entry.id[:8]}", user.name)
        except Unbalanced:
            pass
    record(db, user.name, "stock", MOVE_LABELS[body.kind], f"{ingredient.name} {body.quantity_milli:+}", ingredient.name)
    db.commit()
    return [r for r in levels(low_only=False, db=db, _=user) if r.ingredient_id == ingredient.id][0]


@router.post("/count", response_model=LevelOut)
def count(body: CountIn, db: Session = Depends(get_db), user: User = Depends(can_adjust)):
    """A stocktake: say what is on the shelf and the difference is recorded."""
    ingredient = db.get(Ingredient, body.ingredient_id)
    if not ingredient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingredient not found.")
    level = _level_row(db, ingredient.id)
    difference = body.counted_milli - level.quantity_milli
    if difference == 0:
        db.commit()
        return [r for r in levels(low_only=False, db=db, _=user) if r.ingredient_id == ingredient.id][0]
    move_stock(
        db, ingredient, difference, "adjustment",
        note=body.note.strip() or "Counted on the shelf", who=user.name,
    )
    record(db, user.name, "stock", "Stock counted",
           f"{ingredient.name}: {difference:+} against the system", ingredient.name)
    db.commit()
    return [r for r in levels(low_only=False, db=db, _=user) if r.ingredient_id == ingredient.id][0]


@router.post("/reorder-level", response_model=LevelOut)
def set_reorder(body: ReorderIn, db: Session = Depends(get_db), user: User = Depends(can_adjust)):
    ingredient = db.get(Ingredient, body.ingredient_id)
    if not ingredient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingredient not found.")
    level = _level_row(db, ingredient.id)
    level.reorder_milli = body.reorder_milli
    db.commit()
    return [r for r in levels(low_only=False, db=db, _=user) if r.ingredient_id == ingredient.id][0]


@router.get("/moves", response_model=list[MoveOut])
def moves(
    ingredient_id: str | None = None,
    kind: str | None = None,
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(can_see),
):
    stmt = select(StockMove).order_by(StockMove.created_at.desc()).limit(limit)
    if ingredient_id:
        stmt = stmt.where(StockMove.ingredient_id == ingredient_id)
    if kind:
        stmt = stmt.where(StockMove.kind == kind)
    rows = db.scalars(stmt).all()
    names = {i.id: i for i in db.scalars(select(Ingredient)).all()}
    return [
        MoveOut(
            id=m.id, at=m.created_at.isoformat(), ingredient_id=m.ingredient_id,
            ingredient_name=names[m.ingredient_id].name if m.ingredient_id in names else "(removed)",
            unit=names[m.ingredient_id].unit if m.ingredient_id in names else "",
            kind=m.kind, kind_label=MOVE_LABELS.get(m.kind, m.kind),
            quantity_milli=m.quantity_milli, balance_milli=m.balance_milli,
            value_ngwee=m.value_ngwee, reference=m.reference, note=m.note, by=m.created_by,
        )
        for m in rows
    ]


# ---------------------------------------------------------------------------
# suppliers
# ---------------------------------------------------------------------------

def _supplier_out(db: Session, s: Supplier) -> SupplierOut:
    rows = db.execute(
        select(func.count(Purchase.id), func.coalesce(func.sum(Purchase.total_ngwee), 0))
        .where(Purchase.supplier_id == s.id, Purchase.status == "received")
    ).first()
    return SupplierOut(
        id=s.id, name=s.name, contact=s.contact, phone=s.phone, email=s.email,
        note=s.note, is_active=s.is_active, purchases=rows[0] or 0, spent_ngwee=rows[1] or 0,
    )


@router.get("/suppliers", response_model=list[SupplierOut])
def suppliers(
    include_hidden: bool = False, db: Session = Depends(get_db), _: User = Depends(can_see),
):
    stmt = select(Supplier).order_by(Supplier.name)
    if not include_hidden:
        stmt = stmt.where(Supplier.is_active.is_(True))
    return [_supplier_out(db, s) for s in db.scalars(stmt).all()]


@router.post("/suppliers", response_model=SupplierOut, status_code=status.HTTP_201_CREATED)
def create_supplier(body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(can_buy)):
    name = body.name.strip()
    if db.scalar(select(Supplier).where(func.lower(Supplier.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is already a supplier with that name.")
    supplier = Supplier(
        name=name, contact=body.contact.strip(), phone=body.phone.strip(),
        email=body.email.strip(), note=body.note.strip(), is_active=body.is_active,
        created_by=user.name,
    )
    db.add(supplier)
    record(db, user.name, "stock", "Supplier added", name)
    db.commit()
    db.refresh(supplier)
    return _supplier_out(db, supplier)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierOut)
def patch_supplier(
    supplier_id: str, body: SupplierIn, db: Session = Depends(get_db), user: User = Depends(can_buy),
):
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Supplier not found.")
    name = body.name.strip()
    clash = db.scalar(
        select(Supplier).where(func.lower(Supplier.name) == name.lower(), Supplier.id != supplier_id)
    )
    if clash:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is already a supplier with that name.")
    supplier.name = name
    supplier.contact = body.contact.strip()
    supplier.phone = body.phone.strip()
    supplier.email = body.email.strip()
    supplier.note = body.note.strip()
    supplier.is_active = body.is_active
    record(db, user.name, "stock", "Supplier changed", name, supplier.id)
    db.commit()
    db.refresh(supplier)
    return _supplier_out(db, supplier)


# ---------------------------------------------------------------------------
# purchases
# ---------------------------------------------------------------------------

def _purchase_out(p: Purchase, payments: list[SupplierPayment] | None = None) -> PurchaseOut:
    paid_rows = payments if payments is not None else []
    paid = sum(x.amount_ngwee for x in paid_rows)
    # Only a received delivery is a debt; a draft is not owed yet.
    owed = (p.total_ngwee - paid) if p.status == "received" else 0
    return PurchaseOut(
        id=p.id, number=p.number, supplier_id=p.supplier_id, supplier_name=p.supplier.name,
        status=p.status, invoice_number=p.invoice_number, note=p.note,
        total_ngwee=p.total_ngwee, created_at=p.created_at.isoformat(), created_by=p.created_by,
        received_at=p.received_at.isoformat() if p.received_at else None,
        received_by=p.received_by,
        lines=[
            PurchaseLineOut(
                id=line.id, ingredient_id=line.ingredient_id, ingredient_name=line.ingredient_name,
                unit=line.unit, quantity_milli=line.quantity_milli,
                unit_cost_ngwee=line.unit_cost_ngwee, line_ngwee=line.line_ngwee,
            )
            for line in p.lines
        ],
        paid_ngwee=paid,
        owed_ngwee=max(owed, 0),
        payments=[
            SupplierPaymentOut(
                id=x.id, at=x.created_at.isoformat(), method=x.method,
                amount_ngwee=x.amount_ngwee, reference=x.reference, note=x.note, by=x.created_by,
            )
            for x in sorted(paid_rows, key=lambda r: r.created_at)
        ],
    )


def _payments_by_purchase(db: Session, purchase_ids: list[str]) -> dict[str, list[SupplierPayment]]:
    if not purchase_ids:
        return {}
    rows = db.scalars(
        select(SupplierPayment).where(SupplierPayment.purchase_id.in_(purchase_ids))
    ).all()
    grouped: dict[str, list[SupplierPayment]] = {}
    for row in rows:
        grouped.setdefault(row.purchase_id, []).append(row)
    return grouped


def _purchase_number(db: Session) -> str:
    today = datetime.now(timezone.utc).date()
    return numbered(db, f"PO-{today:%Y%m}-")


@router.get("/purchases", response_model=list[PurchaseOut])
def purchases(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(can_see),
):
    stmt = select(Purchase).order_by(Purchase.created_at.desc()).limit(limit)
    if status_filter:
        stmt = stmt.where(Purchase.status == status_filter)
    found = list(db.scalars(stmt).all())
    paid = _payments_by_purchase(db, [p.id for p in found])
    return [_purchase_out(p, paid.get(p.id, [])) for p in found]


@router.post("/purchases", response_model=PurchaseOut, status_code=status.HTTP_201_CREATED)
def create_purchase(body: PurchaseIn, db: Session = Depends(get_db), user: User = Depends(can_buy)):
    supplier = db.get(Supplier, body.supplier_id)
    if not supplier:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a supplier.")
    purchase = Purchase(
        number=_purchase_number(db), supplier_id=supplier.id, status="draft",
        invoice_number=body.invoice_number.strip(), note=body.note.strip(), created_by=user.name,
    )
    db.add(purchase)
    db.flush()

    total = 0
    seen: set[str] = set()
    for line in body.lines:
        ingredient = db.get(Ingredient, line.ingredient_id)
        if not ingredient:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown ingredient.")
        if ingredient.id in seen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "An ingredient can only appear once; add the quantities together.",
            )
        seen.add(ingredient.id)
        line_total = round(line.unit_cost_ngwee * line.quantity_milli / 1000)
        total += line_total
        db.add(PurchaseLine(
            purchase_id=purchase.id, ingredient_id=ingredient.id,
            ingredient_name=ingredient.name, unit=ingredient.unit,
            quantity_milli=line.quantity_milli, unit_cost_ngwee=line.unit_cost_ngwee,
            line_ngwee=line_total,
        ))
    purchase.total_ngwee = total
    record(db, user.name, "stock", "Purchase drafted", f"{purchase.number} from {supplier.name}", purchase.number)
    db.commit()
    db.refresh(purchase)
    return _purchase_out(purchase, _payments_by_purchase(db, [purchase.id]).get(purchase.id, []))


@router.post("/purchases/{purchase_id}/receive", response_model=PurchaseOut)
def receive_purchase(
    purchase_id: str, db: Session = Depends(get_db), user: User = Depends(can_buy),
):
    """Checks a delivery in: stock goes up and the ingredient's cost is updated."""
    purchase = db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase not found.")
    if purchase.status == "received":
        raise HTTPException(status.HTTP_409_CONFLICT, "That delivery has already been checked in.")
    if purchase.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "That purchase was cancelled.")

    for line in purchase.lines:
        ingredient = db.get(Ingredient, line.ingredient_id)
        if not ingredient:
            continue
        move_stock(
            db, ingredient, line.quantity_milli, "purchase", reference=purchase.number,
            note=f"{purchase.supplier.name} {purchase.invoice_number}".strip(),
            who=user.name, unit_cost_ngwee=line.unit_cost_ngwee,
        )
        # The newest price paid becomes the cost used for margins and stock value.
        if line.unit_cost_ngwee and line.unit_cost_ngwee != ingredient.cost_ngwee:
            ingredient.cost_ngwee = line.unit_cost_ngwee

    purchase.status = "received"
    purchase.received_at = datetime.now(timezone.utc)
    purchase.received_by = user.name
    try:
        db.flush()
        post_purchase(db, purchase)
    except Unbalanced:
        pass
    record(db, user.name, "stock", "Delivery checked in",
           f"{purchase.number}, {purchase.total_ngwee} ngwee", purchase.number)
    db.commit()
    db.refresh(purchase)
    return _purchase_out(purchase, _payments_by_purchase(db, [purchase.id]).get(purchase.id, []))


@router.post("/purchases/{purchase_id}/cancel", response_model=PurchaseOut)
def cancel_purchase(
    purchase_id: str, db: Session = Depends(get_db), user: User = Depends(can_buy),
):
    purchase = db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase not found.")
    if purchase.status == "received":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That delivery is already in stock. Record a return instead.",
        )
    purchase.status = "cancelled"
    purchase.cancelled_at = datetime.now(timezone.utc)
    record(db, user.name, "stock", "Purchase cancelled", purchase.number, purchase.number)
    db.commit()
    db.refresh(purchase)
    return _purchase_out(purchase, _payments_by_purchase(db, [purchase.id]).get(purchase.id, []))


@router.get("/value")
def stock_value(db: Session = Depends(get_db), _: User = Depends(can_see)):
    """What is on the shelves, at what it cost. Stage 7 reads this for the books."""
    rows = levels(low_only=False, db=db, _=_)
    return {
        "ingredients": len(rows),
        "value_ngwee": sum(r.value_ngwee for r in rows),
        "low": [r.name for r in rows if r.is_low],
        "negative": [r.name for r in rows if r.quantity_milli < 0],
    }


@router.post("/purchases/{purchase_id}/pay", response_model=PurchaseOut)
def pay_supplier(
    purchase_id: str, body: SupplierPaymentIn,
    db: Session = Depends(get_db), user: User = Depends(can_buy),
):
    """Records money paid to a supplier against one delivery."""
    purchase = db.get(Purchase, purchase_id)
    if not purchase:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Purchase not found.")
    if purchase.status != "received":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only a delivery that has been checked in can be paid for.",
        )
    if body.method not in SUPPLIER_PAYMENT_ACCOUNTS:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Pay by one of: {', '.join(SUPPLIER_PAYMENT_ACCOUNTS)}.",
        )
    already = sum(
        x.amount_ngwee for x in _payments_by_purchase(db, [purchase.id]).get(purchase.id, [])
    )
    owed = purchase.total_ngwee - already
    if owed <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "That delivery is already paid for.")
    if body.amount_ngwee > owed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "That is more than is owed on this delivery.",
        )

    payment = SupplierPayment(
        purchase_id=purchase.id, supplier_id=purchase.supplier_id, method=body.method,
        amount_ngwee=body.amount_ngwee, reference=body.reference.strip(),
        note=body.note.strip(), created_by=user.name,
    )
    db.add(payment)
    db.flush()
    try:
        post_supplier_payment(db, purchase, payment)
    except Unbalanced:
        pass
    record(db, user.name, "money", "Supplier paid",
           f"{purchase.supplier.name}, {purchase.number}, {body.amount_ngwee} ngwee", purchase.number)
    db.commit()
    db.refresh(purchase)
    return _purchase_out(purchase, _payments_by_purchase(db, [purchase.id]).get(purchase.id, []))


@router.get("/owed", response_model=list[OwedRow])
def owed(
    overdue_days: int = Query(default=30, ge=1, le=180),
    db: Session = Depends(get_db),
    _: User | None = Depends(can_see),
):
    """What is owed to each supplier, and how long it has been owed."""
    received = list(db.scalars(select(Purchase).where(Purchase.status == "received")).all())
    paid = _payments_by_purchase(db, [p.id for p in received])
    now = datetime.now(timezone.utc)
    rows: dict[str, dict] = {}
    for purchase in received:
        settled = sum(x.amount_ngwee for x in paid.get(purchase.id, []))
        outstanding = purchase.total_ngwee - settled
        if outstanding <= 0:
            continue
        since = purchase.received_at or purchase.created_at
        days = (now - since).days
        row = rows.setdefault(purchase.supplier_id, {
            "name": purchase.supplier.name, "phone": purchase.supplier.phone,
            "count": 0, "owed": 0, "oldest": 0, "overdue": 0,
        })
        row["count"] += 1
        row["owed"] += outstanding
        row["oldest"] = max(row["oldest"], days)
        if days >= overdue_days:
            row["overdue"] += outstanding
    return [
        OwedRow(
            supplier_id=supplier_id, supplier_name=r["name"], phone=r["phone"],
            purchases=r["count"], owed_ngwee=r["owed"], oldest_days=r["oldest"],
            overdue_ngwee=r["overdue"],
        )
        for supplier_id, r in sorted(rows.items(), key=lambda kv: -kv[1]["owed"])
    ]
