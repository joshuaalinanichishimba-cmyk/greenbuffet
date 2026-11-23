"""The menu: categories, products, options, ingredients and recipes.

Reading the menu is open to anyone who serves customers — the till, the kitchen
screen and the stock room all need it. Changing it needs menu.edit.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import current_user, requires
from app.models.access import User
from app.models.menu import (
    UNITS, Category, Ingredient, OptionGroup, OptionItem, PriceChange, Product,
    ProductOptionGroup, RecipeLine,
)
from app.schemas.menu import (
    CategoryIn, CategoryOut, CategoryPatch, IngredientIn, IngredientOut, IngredientPatch,
    OptionGroupIn, OptionGroupOut, OptionGroupPatch, OptionItemIn, OptionItemOut,
    PriceChangeOut, ProductGroupsIn, ProductIn, ProductOptionOut, ProductOut, ProductPatch,
    RecipeLineIn, RecipeLineOut,
)
from app.services.audit import record

router = APIRouter(prefix="/menu", tags=["menu"])

# Everyone who serves a customer needs to read the menu.
can_read = requires("menu.edit", "pos.use", "orders.view", "kitchen.view", "inventory.view")
can_edit = requires("menu.edit")


# --------------------------------------------------------------------------
# shaping helpers
# --------------------------------------------------------------------------

def _quantity_label(quantity_milli: int, unit: str) -> str:
    """Turns thousandths of a unit back into something a cook would say."""
    whole = quantity_milli / 1000
    if unit in ("kg", "l"):
        small = "g" if unit == "kg" else "ml"
        if quantity_milli < 1000:
            return f"{quantity_milli:g} {small}"
        return f"{whole:g} {unit}"
    if unit in ("g", "ml"):
        return f"{whole:g} {unit}"
    # each: 1000 is one of them, 500 is half
    if quantity_milli == 500:
        return "half"
    return f"{whole:g}"


def _item_out(item: OptionItem) -> OptionItemOut:
    return OptionItemOut(
        id=item.id, group_id=item.group_id, name=item.name, price_ngwee=item.price_ngwee,
        sort=item.sort, is_active=item.is_active, is_available=item.is_available,
    )


def _line_out(line: RecipeLine) -> RecipeLineOut:
    ing = line.ingredient
    # quantity is in thousandths of a unit, so the cost divides back down by 1000
    line_cost = round(ing.cost_ngwee * line.quantity_milli / 1000)
    return RecipeLineOut(
        id=line.id, ingredient_id=line.ingredient_id, quantity_milli=line.quantity_milli,
        note=line.note, ingredient_name=ing.name, unit=ing.unit,
        cost_ngwee=ing.cost_ngwee, line_cost_ngwee=line_cost,
        quantity_label=_quantity_label(line.quantity_milli, ing.unit),
    )


def _product_out(p: Product) -> ProductOut:
    recipe = [_line_out(line) for line in p.recipe]
    return ProductOut(
        id=p.id, code=p.code, name=p.name, description=p.description,
        category_id=p.category_id, category_name=p.category.name,
        price_ngwee=p.price_ngwee, vat_rate=float(p.vat_rate), station=p.station,
        is_active=p.is_active, is_available=p.is_available, sort=p.sort,
        option_groups=[
            ProductOptionOut(
                group_id=link.group.id, name=link.group.name, helper=link.group.helper,
                min_select=link.group.min_select, max_select=link.group.max_select,
                sort=link.sort,
                items=[_item_out(i) for i in link.group.items if i.is_active],
            )
            for link in sorted(p.option_links, key=lambda l: l.sort)
            if link.group.is_active
        ],
        recipe=recipe,
        recipe_cost_ngwee=sum(line.line_cost_ngwee for line in recipe),
    )


def _group_out(g: OptionGroup, used_by: int = 0) -> OptionGroupOut:
    return OptionGroupOut(
        id=g.id, name=g.name, helper=g.helper, min_select=g.min_select,
        max_select=g.max_select, is_active=g.is_active,
        items=[_item_out(i) for i in g.items], used_by=used_by,
    )


# --------------------------------------------------------------------------
# categories
# --------------------------------------------------------------------------

@router.get("/categories", response_model=list[CategoryOut])
def categories(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(can_read),
):
    counts = dict(
        db.execute(select(Product.category_id, func.count(Product.id)).group_by(Product.category_id)).all()
    )
    stmt = select(Category).order_by(Category.sort, Category.name)
    if not include_hidden:
        stmt = stmt.where(Category.is_active.is_(True))
    return [
        CategoryOut(
            id=c.id, name=c.name, description=c.description, sort=c.sort,
            is_active=c.is_active, product_count=counts.get(c.id, 0),
        )
        for c in db.scalars(stmt).all()
    ]


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryIn, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    name = body.name.strip()
    if db.scalar(select(Category).where(func.lower(Category.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is already a section with that name.")
    category = Category(
        name=name, description=body.description.strip(), sort=body.sort,
        is_active=body.is_active, created_by=user.name,
    )
    db.add(category)
    record(db, user.name, "menu", "Menu section added", name)
    db.commit()
    db.refresh(category)
    return CategoryOut(
        id=category.id, name=category.name, description=category.description,
        sort=category.sort, is_active=category.is_active, product_count=0,
    )


@router.patch("/categories/{category_id}", response_model=CategoryOut)
def patch_category(
    category_id: str, body: CategoryPatch,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    category = db.get(Category, category_id)
    if not category:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Menu section not found.")
    before = {"name": category.name, "active": category.is_active}
    if body.name:
        name = body.name.strip()
        clash = db.scalar(
            select(Category).where(func.lower(Category.name) == name.lower(), Category.id != category_id)
        )
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "There is already a section with that name.")
        category.name = name
    if body.description is not None:
        category.description = body.description.strip()
    if body.sort is not None:
        category.sort = body.sort
    if body.is_active is not None:
        if not body.is_active:
            live = db.scalar(
                select(func.count(Product.id)).where(
                    Product.category_id == category_id, Product.is_active.is_(True)
                )
            )
            if live:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    f"Retire or move the {live} item(s) in this section first.",
                )
        category.is_active = body.is_active
    record(db, user.name, "menu", "Menu section changed", category.name, category.id,
           before=before, after={"name": category.name, "active": category.is_active})
    db.commit()
    db.refresh(category)
    count = db.scalar(select(func.count(Product.id)).where(Product.category_id == category.id)) or 0
    return CategoryOut(
        id=category.id, name=category.name, description=category.description,
        sort=category.sort, is_active=category.is_active, product_count=count,
    )


# --------------------------------------------------------------------------
# products
# --------------------------------------------------------------------------

@router.get("/products", response_model=list[ProductOut])
def products(
    category_id: str | None = None,
    include_hidden: bool = False,
    search: str | None = Query(default=None, max_length=60),
    db: Session = Depends(get_db),
    _: User = Depends(can_read),
):
    stmt = select(Product).order_by(Product.sort, Product.name)
    if category_id:
        stmt = stmt.where(Product.category_id == category_id)
    if not include_hidden:
        stmt = stmt.where(Product.is_active.is_(True))
    if search:
        like = f"%{search.strip().lower()}%"
        stmt = stmt.where(func.lower(Product.name).like(like) | func.lower(Product.code).like(like))
    return [_product_out(p) for p in db.scalars(stmt).all()]


@router.get("/products/{product_id}", response_model=ProductOut)
def product(product_id: str, db: Session = Depends(get_db), _: User = Depends(can_read)):
    found = db.get(Product, product_id)
    if not found:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    return _product_out(found)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductIn, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    code = body.code.strip().upper()
    if db.scalar(select(Product).where(func.upper(Product.code) == code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That item code is already used.")
    if not db.get(Category, body.category_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a menu section.")
    created = Product(
        code=code, name=body.name.strip(), description=body.description.strip(),
        category_id=body.category_id, price_ngwee=body.price_ngwee, vat_rate=body.vat_rate,
        station=body.station.strip() or "kitchen", is_active=body.is_active,
        is_available=body.is_available, sort=body.sort, created_by=user.name,
    )
    db.add(created)
    db.flush()
    db.add(PriceChange(
        product_id=created.id, old_ngwee=0, new_ngwee=body.price_ngwee,
        reason="Added to the menu", created_by=user.name,
    ))
    record(db, user.name, "menu", "Menu item added", f"{created.name} at {created.price_ngwee} ngwee", code)
    db.commit()
    db.refresh(created)
    return _product_out(created)


@router.patch("/products/{product_id}", response_model=ProductOut)
def patch_product(
    product_id: str, body: ProductPatch,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    target = db.get(Product, product_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")

    if body.code:
        code = body.code.strip().upper()
        clash = db.scalar(select(Product).where(func.upper(Product.code) == code, Product.id != product_id))
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "That item code is already used.")
        target.code = code
    if body.category_id:
        if not db.get(Category, body.category_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown menu section.")
        target.category_id = body.category_id

    # A price change is kept in its own table as well as the audit log, because
    # reports need to know what a dish cost on a given day.
    if body.price_ngwee is not None and body.price_ngwee != target.price_ngwee:
        old = target.price_ngwee
        target.price_ngwee = body.price_ngwee
        db.add(PriceChange(
            product_id=target.id, old_ngwee=old, new_ngwee=body.price_ngwee,
            reason=body.price_reason.strip(), created_by=user.name,
        ))
        record(db, user.name, "menu", "Price changed", target.name, target.code,
               before=old, after=body.price_ngwee)

    for field in ("name", "description", "station"):
        value = getattr(body, field)
        if value is not None:
            setattr(target, field, value.strip())
    for field in ("vat_rate", "is_active", "is_available", "sort"):
        value = getattr(body, field)
        if value is not None:
            setattr(target, field, value)

    if body.is_available is not None:
        record(db, user.name, "menu",
               "Marked available" if body.is_available else "Marked sold out",
               target.name, target.code)

    db.commit()
    db.refresh(target)
    return _product_out(target)


@router.put("/products/{product_id}/option-groups", response_model=ProductOut)
def set_product_groups(
    product_id: str, body: ProductGroupsIn,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    target = db.get(Product, product_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    wanted = list(dict.fromkeys(body.group_ids))
    for gid in wanted:
        if not db.get(OptionGroup, gid):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown option group.")
    before = [link.group.name for link in sorted(target.option_links, key=lambda l: l.sort)]
    target.option_links.clear()
    db.flush()
    for position, gid in enumerate(wanted, start=1):
        db.add(ProductOptionGroup(product_id=target.id, group_id=gid, sort=position * 10))
    db.flush()
    db.refresh(target)
    after = [link.group.name for link in sorted(target.option_links, key=lambda l: l.sort)]
    record(db, user.name, "menu", "Item choices changed", target.name, target.code,
           before=before, after=after)
    db.commit()
    db.refresh(target)
    return _product_out(target)


# --------------------------------------------------------------------------
# option groups and their items
# --------------------------------------------------------------------------

@router.get("/option-groups", response_model=list[OptionGroupOut])
def option_groups(db: Session = Depends(get_db), _: User = Depends(can_read)):
    used = dict(
        db.execute(
            select(ProductOptionGroup.group_id, func.count(ProductOptionGroup.id))
            .group_by(ProductOptionGroup.group_id)
        ).all()
    )
    groups = db.scalars(select(OptionGroup).order_by(OptionGroup.name)).all()
    return [_group_out(g, used.get(g.id, 0)) for g in groups]


@router.post("/option-groups", response_model=OptionGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(body: OptionGroupIn, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    name = body.name.strip()
    if db.scalar(select(OptionGroup).where(func.lower(OptionGroup.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "There is already a choice with that name.")
    if body.min_select > body.max_select:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "The smallest number of choices cannot be more than the largest.",
        )
    group = OptionGroup(
        name=name, helper=body.helper.strip(), min_select=body.min_select,
        max_select=body.max_select, is_active=body.is_active, created_by=user.name,
    )
    db.add(group)
    record(db, user.name, "menu", "Choice group added", name)
    db.commit()
    db.refresh(group)
    return _group_out(group)


@router.patch("/option-groups/{group_id}", response_model=OptionGroupOut)
def patch_group(
    group_id: str, body: OptionGroupPatch,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    group = db.get(OptionGroup, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Choice group not found.")
    if body.name:
        name = body.name.strip()
        clash = db.scalar(
            select(OptionGroup).where(func.lower(OptionGroup.name) == name.lower(), OptionGroup.id != group_id)
        )
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "There is already a choice with that name.")
        group.name = name
    if body.helper is not None:
        group.helper = body.helper.strip()
    if body.min_select is not None:
        group.min_select = body.min_select
    if body.max_select is not None:
        group.max_select = body.max_select
    if group.min_select > group.max_select:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "The smallest number of choices cannot be more than the largest.",
        )
    if body.is_active is not None:
        group.is_active = body.is_active
    record(db, user.name, "menu", "Choice group changed", group.name, group.id)
    db.commit()
    db.refresh(group)
    return _group_out(group)


@router.post("/option-groups/{group_id}/items", response_model=OptionItemOut, status_code=status.HTTP_201_CREATED)
def add_item(
    group_id: str, body: OptionItemIn,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    group = db.get(OptionGroup, group_id)
    if not group:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Choice group not found.")
    name = body.name.strip()
    if any(i.name.lower() == name.lower() for i in group.items):
        raise HTTPException(status.HTTP_409_CONFLICT, "That choice is already in this group.")
    item = OptionItem(
        group_id=group_id, name=name, price_ngwee=body.price_ngwee, sort=body.sort,
        is_active=body.is_active, is_available=body.is_available, created_by=user.name,
    )
    db.add(item)
    record(db, user.name, "menu", "Choice added", f"{name} in {group.name}", group.name)
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.patch("/option-items/{item_id}", response_model=OptionItemOut)
def patch_item(
    item_id: str, body: OptionItemIn,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    item = db.get(OptionItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Choice not found.")
    name = body.name.strip()
    if any(i.id != item_id and i.name.lower() == name.lower() for i in item.group.items):
        raise HTTPException(status.HTTP_409_CONFLICT, "That choice is already in this group.")
    before = {"name": item.name, "price": item.price_ngwee, "available": item.is_available}
    item.name = name
    item.price_ngwee = body.price_ngwee
    item.sort = body.sort
    item.is_active = body.is_active
    item.is_available = body.is_available
    record(db, user.name, "menu", "Choice changed", f"{item.name} in {item.group.name}", item.group.name,
           before=before, after={"name": item.name, "price": item.price_ngwee, "available": item.is_available})
    db.commit()
    db.refresh(item)
    return _item_out(item)


# --------------------------------------------------------------------------
# ingredients and recipes
# --------------------------------------------------------------------------

@router.get("/ingredients", response_model=list[IngredientOut])
def ingredients(
    include_hidden: bool = False,
    db: Session = Depends(get_db),
    _: User = Depends(can_read),
):
    used = dict(
        db.execute(
            select(RecipeLine.ingredient_id, func.count(RecipeLine.id)).group_by(RecipeLine.ingredient_id)
        ).all()
    )
    stmt = select(Ingredient).order_by(Ingredient.name)
    if not include_hidden:
        stmt = stmt.where(Ingredient.is_active.is_(True))
    return [
        IngredientOut(
            id=i.id, name=i.name, unit=i.unit, cost_ngwee=i.cost_ngwee,
            note=i.note, is_active=i.is_active, used_in=used.get(i.id, 0),
        )
        for i in db.scalars(stmt).all()
    ]


@router.post("/ingredients", response_model=IngredientOut, status_code=status.HTTP_201_CREATED)
def create_ingredient(body: IngredientIn, db: Session = Depends(get_db), user: User = Depends(can_edit)):
    if body.unit not in UNITS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unit must be one of: {', '.join(UNITS)}")
    name = body.name.strip()
    if db.scalar(select(Ingredient).where(func.lower(Ingredient.name) == name.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "That ingredient is already on the list.")
    ingredient = Ingredient(
        name=name, unit=body.unit, cost_ngwee=body.cost_ngwee,
        note=body.note.strip(), is_active=body.is_active, created_by=user.name,
    )
    db.add(ingredient)
    record(db, user.name, "menu", "Ingredient added", f"{name} per {body.unit}")
    db.commit()
    db.refresh(ingredient)
    return IngredientOut(
        id=ingredient.id, name=ingredient.name, unit=ingredient.unit,
        cost_ngwee=ingredient.cost_ngwee, note=ingredient.note,
        is_active=ingredient.is_active, used_in=0,
    )


@router.patch("/ingredients/{ingredient_id}", response_model=IngredientOut)
def patch_ingredient(
    ingredient_id: str, body: IngredientPatch,
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    ingredient = db.get(Ingredient, ingredient_id)
    if not ingredient:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ingredient not found.")
    if body.unit is not None:
        if body.unit not in UNITS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unit must be one of: {', '.join(UNITS)}")
        ingredient.unit = body.unit
    if body.name:
        name = body.name.strip()
        clash = db.scalar(
            select(Ingredient).where(func.lower(Ingredient.name) == name.lower(), Ingredient.id != ingredient_id)
        )
        if clash:
            raise HTTPException(status.HTTP_409_CONFLICT, "That ingredient is already on the list.")
        ingredient.name = name
    if body.cost_ngwee is not None:
        ingredient.cost_ngwee = body.cost_ngwee
    if body.note is not None:
        ingredient.note = body.note.strip()
    if body.is_active is not None:
        ingredient.is_active = body.is_active
    record(db, user.name, "menu", "Ingredient changed", ingredient.name, ingredient.id)
    db.commit()
    db.refresh(ingredient)
    used = db.scalar(select(func.count(RecipeLine.id)).where(RecipeLine.ingredient_id == ingredient.id)) or 0
    return IngredientOut(
        id=ingredient.id, name=ingredient.name, unit=ingredient.unit,
        cost_ngwee=ingredient.cost_ngwee, note=ingredient.note,
        is_active=ingredient.is_active, used_in=used,
    )


@router.put("/products/{product_id}/recipe", response_model=ProductOut)
def set_recipe(
    product_id: str, lines: list[RecipeLineIn],
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    target = db.get(Product, product_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found.")
    seen: set[str] = set()
    for line in lines:
        if not db.get(Ingredient, line.ingredient_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown ingredient.")
        if line.ingredient_id in seen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "An ingredient can only appear once in a recipe; add the amounts together.",
            )
        seen.add(line.ingredient_id)

    before = [(line.ingredient.name, line.quantity_milli) for line in target.recipe]
    target.recipe.clear()
    db.flush()
    for line in lines:
        db.add(RecipeLine(
            product_id=target.id, ingredient_id=line.ingredient_id,
            quantity_milli=line.quantity_milli, note=line.note.strip(), created_by=user.name,
        ))
    db.flush()
    db.refresh(target)
    record(db, user.name, "menu", "Recipe changed", target.name, target.code,
           before=before, after=[(line.ingredient.name, line.quantity_milli) for line in target.recipe])
    db.commit()
    db.refresh(target)
    return _product_out(target)


@router.put("/option-items/{item_id}/recipe", response_model=OptionItemOut)
def set_item_recipe(
    item_id: str, lines: list[RecipeLineIn],
    db: Session = Depends(get_db), user: User = Depends(can_edit),
):
    """What an option adds to the kitchen's usage: grilled chicken, extra avocado."""
    item = db.get(OptionItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Choice not found.")
    seen: set[str] = set()
    for line in lines:
        if not db.get(Ingredient, line.ingredient_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown ingredient.")
        if line.ingredient_id in seen:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "An ingredient can only appear once in a recipe; add the amounts together.",
            )
        seen.add(line.ingredient_id)
    item.recipe.clear()
    db.flush()
    for line in lines:
        db.add(RecipeLine(
            option_item_id=item.id, ingredient_id=line.ingredient_id,
            quantity_milli=line.quantity_milli, note=line.note.strip(), created_by=user.name,
        ))
    record(db, user.name, "menu", "Choice recipe changed", f"{item.name} in {item.group.name}", item.group.name)
    db.commit()
    db.refresh(item)
    return _item_out(item)


@router.get("/option-items/{item_id}/recipe", response_model=list[RecipeLineOut])
def item_recipe(item_id: str, db: Session = Depends(get_db), _: User = Depends(can_read)):
    item = db.get(OptionItem, item_id)
    if not item:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Choice not found.")
    return [_line_out(line) for line in item.recipe]


@router.get("/price-changes", response_model=list[PriceChangeOut])
def price_changes(
    limit: int = Query(default=100, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(requires("menu.edit", "reports.view", "books.view")),
):
    rows = db.scalars(select(PriceChange).order_by(PriceChange.created_at.desc()).limit(limit)).all()
    names = dict(db.execute(select(Product.id, Product.name)).all())
    return [
        PriceChangeOut(
            id=r.id, at=r.created_at.isoformat(), product_id=r.product_id,
            product_name=names.get(r.product_id, "(removed)"),
            old_ngwee=r.old_ngwee, new_ngwee=r.new_ngwee, reason=r.reason,
            changed_by=r.created_by,
        )
        for r in rows
    ]
