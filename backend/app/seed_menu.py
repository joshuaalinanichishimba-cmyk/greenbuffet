"""Loads a starting menu for The Green Buffet.

Run once, after setup:

    cd backend
    .\\.venv\\Scripts\\python.exe -m app.seed_menu

It only writes when the menu is empty, so running it twice changes nothing. The
prices and recipe amounts are a starting point taken from the demo — change
them in the Menu screen rather than in this file, so the price history records
who changed what.
"""
import sys

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.menu import (
    Category, Ingredient, OptionGroup, OptionItem, PriceChange, Product,
    ProductOptionGroup, RecipeLine,
)

BY = "Setup"

# name, unit, cost per unit in ngwee
INGREDIENTS = [
    ("Brown rice", "kg", 3200),
    ("White rice", "kg", 2800),
    ("Quinoa", "kg", 9500),
    ("Mixed leaves", "kg", 4500),
    ("Chicken breast", "kg", 8500),
    ("Beef strips", "kg", 11000),
    ("Tofu", "kg", 7000),
    ("Chickpeas", "kg", 3500),
    ("Avocado", "each", 1200),
    ("Tomato", "kg", 2200),
    ("Cucumber", "kg", 1800),
    ("Red onion", "kg", 1600),
    ("Sweetcorn", "kg", 3000),
    ("Feta", "kg", 12000),
    ("Tortilla wrap", "each", 500),
    ("Mango", "each", 900),
    ("Banana", "each", 400),
    ("Spinach", "kg", 3800),
    ("Natural yoghurt", "l", 3500),
    ("Orange", "each", 500),
    ("Carrot", "kg", 1500),
    ("Ginger", "kg", 6000),
    ("Sweet potato", "kg", 1900),
    ("Cooking oil", "l", 4800),
]

# name, helper, min, max, [(item, price in ngwee)]
GROUPS = [
    ("Base", "Choose one base", 1, 1, [
        ("Brown rice", 0), ("White rice", 0), ("Quinoa", 1500), ("Mixed leaves", 0),
    ]),
    ("Protein", "Choose one", 1, 1, [
        ("Grilled chicken", 0), ("Beef strips", 2000), ("Tofu", 0), ("Chickpeas", 0),
    ]),
    ("Toppings", "Up to four, free", 0, 4, [
        ("Tomato", 0), ("Cucumber", 0), ("Red onion", 0), ("Sweetcorn", 0),
        ("Avocado", 1500), ("Feta", 1200),
    ]),
    ("Sauce", "Choose one", 1, 1, [
        ("Garlic yoghurt", 0), ("Chilli", 0), ("Peri peri", 0), ("Lemon dressing", 0),
    ]),
    ("Size", "Choose one", 1, 1, [
        ("Regular", 0), ("Large", 2500),
    ]),
]

# code, name, description, category, price in ngwee, station, groups, recipe
PRODUCTS = [
    ("BOWL-01", "Build your own bowl", "Pick a base, a protein, toppings and a sauce.",
     "Bowls", 9500, "kitchen", ["Base", "Protein", "Toppings", "Sauce", "Size"],
     [("Mixed leaves", 60)]),
    ("BOWL-02", "Green Buffet signature bowl", "Quinoa, grilled chicken, avocado, feta and lemon dressing.",
     "Bowls", 12500, "kitchen", ["Size"],
     [("Quinoa", 160), ("Chicken breast", 120), ("Avocado", 500), ("Feta", 30)]),
    ("BUR-01", "Build your own burrito", "The same choices, wrapped and warm.",
     "Burritos", 9500, "kitchen", ["Base", "Protein", "Toppings", "Sauce"],
     [("Tortilla wrap", 1000)]),
    ("BUR-02", "Chicken burrito", "Grilled chicken, rice, beans, salsa and garlic yoghurt.",
     "Burritos", 10500, "kitchen", [],
     [("Tortilla wrap", 1000), ("White rice", 150), ("Chicken breast", 120), ("Chickpeas", 60)]),
    ("SAL-01", "Garden salad", "Leaves, tomato, cucumber and lemon dressing.",
     "Salads", 5500, "cold", ["Protein"],
     [("Mixed leaves", 120), ("Tomato", 60), ("Cucumber", 50)]),
    ("SMO-01", "Mango smoothie", "Mango, banana and yoghurt.",
     "Smoothies and juices", 4500, "bar", [],
     [("Mango", 1000), ("Banana", 1000), ("Natural yoghurt", 150)]),
    ("SMO-02", "Green smoothie", "Spinach, banana, mango and ginger.",
     "Smoothies and juices", 4800, "bar", [],
     [("Spinach", 60), ("Banana", 1000), ("Mango", 500), ("Ginger", 5)]),
    ("JUI-01", "Orange juice", "Pressed to order.",
     "Smoothies and juices", 3500, "bar", [],
     [("Orange", 3000)]),
    ("JUI-02", "Carrot and ginger juice", "Pressed to order.",
     "Smoothies and juices", 3800, "bar", [],
     [("Carrot", 300), ("Ginger", 8)]),
    ("SID-01", "Sweet potato wedges", "Baked, with a sprinkle of salt.",
     "Sides", 3000, "kitchen", [],
     [("Sweet potato", 250), ("Cooking oil", 20)]),
    ("SID-02", "Side salad", "A small garden salad.",
     "Sides", 2500, "cold", [],
     [("Mixed leaves", 60), ("Tomato", 30)]),
]

CATEGORIES = [
    ("Bowls", "Build your own, or take the signature", 10),
    ("Burritos", "Wrapped and warm", 20),
    ("Salads", "Light and fresh", 30),
    ("Smoothies and juices", "Blended and pressed to order", 40),
    ("Sides", "To go alongside", 50),
]

# Which ingredient an option uses, so the kitchen's usage follows the choice.
OPTION_RECIPES = {
    ("Base", "Brown rice"): [("Brown rice", 180)],
    ("Base", "White rice"): [("White rice", 180)],
    ("Base", "Quinoa"): [("Quinoa", 160)],
    ("Base", "Mixed leaves"): [("Mixed leaves", 120)],
    ("Protein", "Grilled chicken"): [("Chicken breast", 120)],
    ("Protein", "Beef strips"): [("Beef strips", 120)],
    ("Protein", "Tofu"): [("Tofu", 120)],
    ("Protein", "Chickpeas"): [("Chickpeas", 100)],
    ("Toppings", "Avocado"): [("Avocado", 500)],
    ("Toppings", "Feta"): [("Feta", 30)],
    ("Toppings", "Tomato"): [("Tomato", 40)],
    ("Toppings", "Cucumber"): [("Cucumber", 40)],
    ("Toppings", "Red onion"): [("Red onion", 20)],
    ("Toppings", "Sweetcorn"): [("Sweetcorn", 40)],
}


def seed_menu() -> bool:
    db = SessionLocal()
    try:
        if db.scalar(select(func.count(Product.id))):
            print("The menu already has items, so nothing was changed.")
            return False

        ingredients: dict[str, Ingredient] = {}
        for name, unit, cost in INGREDIENTS:
            found = db.scalar(select(Ingredient).where(Ingredient.name == name))
            if not found:
                found = Ingredient(name=name, unit=unit, cost_ngwee=cost, created_by=BY)
                db.add(found)
            ingredients[name] = found

        categories: dict[str, Category] = {}
        for name, description, sort in CATEGORIES:
            found = db.scalar(select(Category).where(Category.name == name))
            if not found:
                found = Category(name=name, description=description, sort=sort, created_by=BY)
                db.add(found)
            categories[name] = found

        groups: dict[str, OptionGroup] = {}
        items: dict[tuple[str, str], OptionItem] = {}
        for name, helper, low, high, options in GROUPS:
            found = db.scalar(select(OptionGroup).where(OptionGroup.name == name))
            if not found:
                found = OptionGroup(
                    name=name, helper=helper, min_select=low, max_select=high, created_by=BY,
                )
                db.add(found)
            groups[name] = found
            db.flush()
            for position, (item_name, price) in enumerate(options, start=1):
                item = db.scalar(
                    select(OptionItem).where(
                        OptionItem.group_id == found.id, OptionItem.name == item_name
                    )
                )
                if not item:
                    item = OptionItem(
                        group_id=found.id, name=item_name, price_ngwee=price,
                        sort=position * 10, created_by=BY,
                    )
                    db.add(item)
                items[(name, item_name)] = item
        db.flush()

        for (group_name, item_name), lines in OPTION_RECIPES.items():
            item = items[(group_name, item_name)]
            for ingredient_name, quantity in lines:
                db.add(RecipeLine(
                    option_item_id=item.id, ingredient_id=ingredients[ingredient_name].id,
                    quantity_milli=quantity, created_by=BY,
                ))

        for code, name, description, category, price, station, group_names, recipe in PRODUCTS:
            product = Product(
                code=code, name=name, description=description,
                category_id=categories[category].id, price_ngwee=price,
                station=station, sort=10, created_by=BY,
            )
            db.add(product)
            db.flush()
            db.add(PriceChange(
                product_id=product.id, old_ngwee=0, new_ngwee=price,
                reason="Starting menu", created_by=BY,
            ))
            for position, group_name in enumerate(group_names, start=1):
                db.add(ProductOptionGroup(
                    product_id=product.id, group_id=groups[group_name].id, sort=position * 10,
                ))
            for ingredient_name, quantity in recipe:
                db.add(RecipeLine(
                    product_id=product.id, ingredient_id=ingredients[ingredient_name].id,
                    quantity_milli=quantity, created_by=BY,
                ))

        db.commit()
        return True
    finally:
        db.close()


if __name__ == "__main__":
    wrote = seed_menu()
    if wrote:
        print("Starting menu loaded.")
        print(f"  Sections    : {len(CATEGORIES)}")
        print(f"  Items       : {len(PRODUCTS)}")
        print(f"  Choices     : {len(GROUPS)} groups")
        print(f"  Ingredients : {len(INGREDIENTS)}")
        print("  Open the Menu screen to check the prices before you trade with them.")
    sys.exit(0)
