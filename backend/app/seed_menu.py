"""The Green Buffet's real menu, from The_Green_Buffet_Menu_final.pdf.

    python -m app.seed_menu             load it into an empty menu
    python -m app.seed_menu --replace   make an existing menu match it

Everything on the printed menu is here: the three bases, the two proteins,
five included toppings with K10 for each one over five, the signature bowls
and burritos, the breakfast burritos (08:30 to 11:30), the dips, the extras
and the two refreshers, all at the printed prices.

Two things the printed menu does not say, taken from the demo and marked so
the owner can check them on the Menu screen:
  - the price of a build-your-own bowl (K75, the same as the signature bowls);
  - which toppings are "the veggies displayed" (the demo's eight).
Ingredient costs are estimates for working out margins, not prices from a
supplier: put the real costs in on the Ingredients screen.

--replace never deletes. Items, choices and sections that are not on this
menu are switched off, so past orders, receipts and reports keep their names
and nothing in the books changes. Items already on the menu with the same
code keep any recipe someone has written for them.
"""
import sys

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.menu import (
    Category, Ingredient, OptionGroup, OptionItem, PriceChange, Product,
    ProductOptionGroup, RecipeLine,
)

BY = "Menu (PDF)"
K = 100  # ngwee in a kwacha, so prices below read like the printed menu

# name, unit, estimated cost per unit in ngwee (check these)
INGREDIENTS = [
    ("White rice", "kg", 28 * K),
    ("Yellow rice", "kg", 30 * K),
    ("Brown rice", "kg", 32 * K),
    ("Garlic barbecue chicken", "kg", 95 * K),
    ("Birria beef", "kg", 120 * K),
    ("Ground beef", "kg", 100 * K),
    ("Eggs", "each", 3 * K),
    ("Potato wedges", "kg", 25 * K),
    ("Cheddar cheese", "kg", 160 * K),
    ("Sweetcorn", "kg", 30 * K),
    ("Black beans", "kg", 35 * K),
    ("Tomato", "kg", 22 * K),
    ("Avocado", "each", 12 * K),
    ("Peppers", "kg", 40 * K),
    ("Lettuce", "kg", 30 * K),
    ("Red onion", "kg", 16 * K),
    ("Baked beans", "kg", 30 * K),
    ("Signature sauce", "l", 80 * K),
    ("Garlic dip", "l", 90 * K),
    ("Sweet onion teriyaki dip", "l", 90 * K),
    ("Chili dip", "l", 90 * K),
    ("Tortilla wrap", "each", 5 * K),
    ("Bowl with lid", "each", 4 * K),
    ("Foil", "each", 1 * K),
    ("Cup with lid", "each", 3 * K),
    ("Strawberry lemonade base", "l", 40 * K),
    ("Lychee refresher base", "l", 45 * K),
]

# The printed menu's sections, in its order. earns_stamp: bowls and burritos
# fill the stamp card ("eight bowls or burritos and the next is free").
CATEGORIES = [
    ("Bowls", "Build your own, or try a signature bowl", 10, True),
    ("Burritos", "Want something a little heavier?", 20, True),
    ("Breakfast", "Early fuel, served 08:30 to 11:30", 30, False),
    ("Dips", "K20 each, on the side", 40, False),
    ("Drinks", "House refreshers", 50, False),
]

TOPPINGS = ["Sweetcorn", "Black beans", "Tomato", "Avocado", "Peppers", "Lettuce", "Red onion", "Baked beans"]

# name, helper, min, max, free_count, extra charge, [(item, price)]
GROUPS = [
    ("Base", "Choose your base", 1, 1, 0, 0, [
        ("White rice", 0), ("Yellow rice", 0), ("Brown rice", 0),
    ]),
    ("Protein", "Choose your protein", 1, 1, 0, 0, [
        ("Garlic barbecue chicken", 0), ("Birria beef", 0),
    ]),
    ("Bowl toppings", "Five included. K10 for each one over five.", 0, 8, 5, 10 * K,
     [(t, 0) for t in TOPPINGS]),
    ("Burrito toppings", "Up to five. Add more with Extra veggies.", 0, 5, 0, 0,
     [(t, 0) for t in TOPPINGS]),
    ("Extras", "Charged per portion", 0, 4, 0, 0, [
        ("Extra protein", 20 * K), ("Extra cheese", 15 * K), ("Extra sauce", 10 * K), ("Extra veggies", 15 * K),
    ]),
    ("Add a dip", "K20 each", 0, 3, 0, 0, [
        ("Garlic dip", 20 * K), ("Sweet onion teriyaki dip", 20 * K), ("Chili dip", 20 * K),
    ]),
]

BOWL = [("Bowl with lid", 1000), ("Signature sauce", 30)]
WRAP = [("Tortilla wrap", 1000), ("Foil", 1000), ("Signature sauce", 30)]

# code, name, description, section, price, station, choices, recipe (thousandths)
PRODUCTS = [
    ("BWL-BYO", "Build your own bowl",
     "Your base, your protein, five toppings. Price to confirm: the printed menu gives none.",
     "Bowls", 75 * K, "kitchen", ["Base", "Protein", "Bowl toppings", "Extras", "Add a dip"], BOWL),
    ("BWL-BBQ", "Garlic barbecue chicken bowl",
     "Garlic barbecue chicken, rice, toppings, signature sauces.",
     "Bowls", 75 * K, "kitchen", ["Base", "Bowl toppings", "Extras", "Add a dip"],
     BOWL + [("Garlic barbecue chicken", 150)]),
    ("BWL-BIR", "Birria beef bowl",
     "Slow-cooked birria beef, rice, toppings, signature sauces.",
     "Bowls", 75 * K, "kitchen", ["Base", "Bowl toppings", "Extras", "Add a dip"],
     BOWL + [("Birria beef", 150)]),
    ("BWL-SAL", "Garden salad", "Veggies only.",
     "Bowls", 60 * K, "kitchen", ["Bowl toppings", "Extras", "Add a dip"],
     [("Bowl with lid", 1000), ("Lettuce", 80)]),
    ("BUR-BBQ", "Garlic barbecue chicken burrito",
     "Garlic barbecue chicken, rice and your toppings, wrapped.",
     "Burritos", 100 * K, "kitchen", ["Base", "Burrito toppings", "Extras", "Add a dip"],
     WRAP + [("Garlic barbecue chicken", 150)]),
    ("BUR-BIR", "Birria beef burrito",
     "Slow-cooked birria beef, rice and your toppings, wrapped.",
     "Burritos", 100 * K, "kitchen", ["Base", "Burrito toppings", "Extras", "Add a dip"],
     WRAP + [("Birria beef", 150)]),
    ("BUR-BYO", "Build your own burrito",
     "Choice of five toppings. Extras charged separately.",
     "Burritos", 100 * K, "kitchen", ["Base", "Protein", "Burrito toppings", "Extras", "Add a dip"], WRAP),
    ("BRK-BUR", "Breakfast burritos (2 per order)",
     "Ground beef in our secret spice blend, eggs, potato wedges and cheddar. 08:30 to 11:30.",
     "Breakfast", 80 * K, "kitchen", ["Extras", "Add a dip"],
     [("Tortilla wrap", 2000), ("Foil", 2000), ("Ground beef", 150), ("Eggs", 2000),
      ("Potato wedges", 100), ("Cheddar cheese", 30)]),
    ("DIP-GAR", "Garlic dip", "On the side.", "Dips", 20 * K, "kitchen", [], [("Garlic dip", 50)]),
    ("DIP-TER", "Sweet onion teriyaki dip", "On the side.", "Dips", 20 * K, "kitchen", [],
     [("Sweet onion teriyaki dip", 50)]),
    ("DIP-CHI", "Chili dip", "On the side.", "Dips", 20 * K, "kitchen", [], [("Chili dip", 50)]),
    ("DRK-STR", "Strawberry lemonade refresher", "House refresher.", "Drinks", 50 * K, "bar", [],
     [("Cup with lid", 1000), ("Strawberry lemonade base", 350)]),
    ("DRK-LYC", "Lychee refresher", "House refresher.", "Drinks", 50 * K, "bar", [],
     [("Cup with lid", 1000), ("Lychee refresher base", 350)]),
]

# What a choice takes from the store room, so stock follows what was picked.
OPTION_RECIPES = {
    ("Base", "White rice"): [("White rice", 200)],
    ("Base", "Yellow rice"): [("Yellow rice", 200)],
    ("Base", "Brown rice"): [("Brown rice", 200)],
    ("Protein", "Garlic barbecue chicken"): [("Garlic barbecue chicken", 150)],
    ("Protein", "Birria beef"): [("Birria beef", 150)],
    **{("Bowl toppings", t): [(t, 1000 if t == "Avocado" else 40)] for t in TOPPINGS},
    **{("Burrito toppings", t): [(t, 1000 if t == "Avocado" else 40)] for t in TOPPINGS},
    ("Extras", "Extra protein"): [("Garlic barbecue chicken", 100)],
    ("Extras", "Extra cheese"): [("Cheddar cheese", 30)],
    ("Extras", "Extra sauce"): [("Signature sauce", 30)],
    ("Add a dip", "Garlic dip"): [("Garlic dip", 50)],
    ("Add a dip", "Sweet onion teriyaki dip"): [("Sweet onion teriyaki dip", 50)],
    ("Add a dip", "Chili dip"): [("Chili dip", 50)],
}
# Avocado is counted whole; a portion is a quarter of one.
for key in list(OPTION_RECIPES):
    if key[1] == "Avocado":
        OPTION_RECIPES[key] = [("Avocado", 250)]


def load_menu(replace: bool = False) -> dict | None:
    """Loads the printed menu. Returns what it did, or None if it left an
    existing menu alone."""
    db = SessionLocal()
    done = {"added": [], "updated": [], "retired": []}
    try:
        if not replace and db.scalar(select(func.count(Product.id))):
            return None

        ingredients: dict[str, Ingredient] = {}
        for name, unit, cost in INGREDIENTS:
            found = db.scalar(select(Ingredient).where(func.lower(Ingredient.name) == name.lower()))
            if not found:
                found = Ingredient(name=name, unit=unit, cost_ngwee=cost,
                                   note="Estimated cost from the menu load: check it", created_by=BY)
                db.add(found)
            else:
                found.is_active = True
            ingredients[name] = found

        categories: dict[str, Category] = {}
        for name, description, sort, stamps in CATEGORIES:
            found = db.scalar(select(Category).where(func.lower(Category.name) == name.lower()))
            if not found:
                found = Category(name=name, description=description, sort=sort, created_by=BY)
                db.add(found)
            found.description, found.sort, found.is_active, found.earns_stamp = description, sort, True, stamps
            categories[name] = found

        groups: dict[str, OptionGroup] = {}
        items: dict[tuple[str, str], OptionItem] = {}
        new_items: set[tuple[str, str]] = set()
        for name, helper, low, high, free, extra, options in GROUPS:
            found = db.scalar(select(OptionGroup).where(func.lower(OptionGroup.name) == name.lower()))
            if not found:
                found = OptionGroup(name=name, created_by=BY)
                db.add(found)
            found.helper, found.min_select, found.max_select = helper, low, high
            found.free_count, found.extra_ngwee, found.is_active = free, extra, True
            groups[name] = found
            db.flush()
            wanted = {item_name for item_name, _ in options}
            for existing in found.items:
                if existing.name not in wanted:
                    existing.is_active = False
            for position, (item_name, price) in enumerate(options, start=1):
                item = db.scalar(select(OptionItem).where(
                    OptionItem.group_id == found.id, OptionItem.name == item_name))
                if not item:
                    item = OptionItem(group_id=found.id, name=item_name, created_by=BY)
                    db.add(item)
                    new_items.add((name, item_name))
                item.price_ngwee, item.sort, item.is_active = price, position * 10, True
                items[(name, item_name)] = item
        db.flush()

        for key, lines in OPTION_RECIPES.items():
            if key not in new_items:
                continue  # an existing choice keeps whatever recipe it has
            for ingredient_name, quantity in lines:
                db.add(RecipeLine(option_item_id=items[key].id, ingredient_id=ingredients[ingredient_name].id,
                                  quantity_milli=quantity, created_by=BY))

        codes = set()
        for position, (code, name, description, category, price, station, group_names, recipe) in enumerate(PRODUCTS, start=1):
            codes.add(code)
            product = db.scalar(select(Product).where(Product.code == code))
            fresh = product is None
            if fresh:
                product = Product(code=code, name=name, category_id=categories[category].id,
                                  price_ngwee=price, created_by=BY)
                db.add(product)
                db.flush()
                db.add(PriceChange(product_id=product.id, old_ngwee=0, new_ngwee=price,
                                   reason="Printed menu", created_by=BY))
                done["added"].append(name)
            else:
                if product.price_ngwee != price:
                    db.add(PriceChange(product_id=product.id, old_ngwee=product.price_ngwee, new_ngwee=price,
                                       reason="Printed menu", created_by=BY))
                done["updated"].append(name)
            product.name, product.description, product.station = name, description, station
            product.category_id, product.price_ngwee, product.sort = categories[category].id, price, position * 10
            product.is_active, product.is_available = True, True

            for link in list(product.option_links):
                db.delete(link)
            db.flush()
            for order, group_name in enumerate(group_names, start=1):
                db.add(ProductOptionGroup(product_id=product.id, group_id=groups[group_name].id, sort=order * 10))
            if fresh:
                for ingredient_name, quantity in recipe:
                    db.add(RecipeLine(product_id=product.id, ingredient_id=ingredients[ingredient_name].id,
                                      quantity_milli=quantity, created_by=BY))

        if replace:
            # Switched off, never deleted: old receipts and reports keep their names.
            for product in db.scalars(select(Product).where(Product.is_active.is_(True))).all():
                if product.code not in codes:
                    product.is_active = False
                    done["retired"].append(product.name)
            keep_groups = {g[0].lower() for g in GROUPS}
            for group in db.scalars(select(OptionGroup)).all():
                if group.name.lower() not in keep_groups:
                    group.is_active = False
            keep_sections = {c[0].lower() for c in CATEGORIES}
            for category in db.scalars(select(Category)).all():
                if category.name.lower() not in keep_sections:
                    category.is_active = False

        db.commit()
        return done
    finally:
        db.close()


MARKER = "menu.loaded_from"
SOURCE = "The_Green_Buffet_Menu_final.pdf"


def _marked() -> bool:
    from app.models.access import Setting
    with SessionLocal() as db:
        row = db.get(Setting, MARKER)
        return bool(row and row.value == SOURCE)


def _mark() -> None:
    from app.models.access import Setting
    with SessionLocal() as db:
        row = db.get(Setting, MARKER)
        if row:
            row.value = SOURCE
        else:
            db.add(Setting(key=MARKER, value=SOURCE, label="Where the menu was loaded from"))
        db.commit()


def seed_menu() -> bool:
    return load_menu(replace=False) is not None


if __name__ == "__main__":
    # update.ps1 runs this without --replace. The first time after stage 20
    # it brings the printed menu in, once; after that the Menu screen is the
    # place for changes, and updates leave the menu alone.
    replace = "--replace" in sys.argv or not _marked()
    result = load_menu(replace=replace)
    if result is not None:
        _mark()
    if result is None:
        print("The menu already has items, so nothing was changed.")
        print("  To make it match the printed menu: .\\scripts\\load-menu.ps1")
        sys.exit(0)
    print("The printed menu is loaded.")
    print(f"  Sections : {', '.join(c[0] for c in CATEGORIES)}")
    print(f"  Items    : {len(PRODUCTS)} ({len(result['added'])} new, {len(result['updated'])} brought up to date)")
    if result["retired"]:
        print(f"  Switched off (not on the printed menu): {', '.join(result['retired'])}")
    print("  Check on the Menu screen: the build-your-own bowl price (K75 assumed),")
    print("  the topping list, and the ingredient costs (estimates).")
    sys.exit(0)
