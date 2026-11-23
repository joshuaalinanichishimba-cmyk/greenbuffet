# Stage 3 report — menu, choices, ingredients and recipes

New tables, so an installed copy updates with `.\scripts\update.ps1`, which
creates them and loads a starting menu if the menu is still empty.

## What you can now do in the app

**Menu** (`/menu`)

- Sections (Bowls, Burritos, Salads, Smoothies and juices, Sides) with their own
  order on the board.
- Items with a code, price, description, section, and which station makes them —
  kitchen, cold station or juice bar. Stage 5's kitchen screen routes by that.
- Mark something sold out in one click. It leaves the till at once and stays on
  the menu, so it comes back with one more click.
- Retire an item instead of deleting it, so old receipts still make sense.
- Every price change is recorded with a reason, in its own table as well as the
  activity log. Reports in later stages read it to know what a dish cost on a
  given day.

**Choices** (`/menu/choices`)

This is the bowl and burrito builder from the demo, as real data. A group —
Base, Protein, Toppings, Sauce, Size — carries its own rule: pick exactly one
base, up to four toppings. Each choice can add to the price (quinoa +K15,
avocado +K15, large +K25) and can be marked sold out on its own, so "no avocado
today" does not take the whole bowl off the menu. A group is written once and
attached to as many items as you like, in the order the till will ask.

**Ingredients** (`/menu/ingredients`)

What the kitchen buys and what it costs, by the kilogram, litre or item. Recipes
are written against this list, so a new supplier price changes the cost of every
dish that uses it. Stock levels and purchase orders arrive at stage 6.

**Recipes** (inside the item editor)

What one serving uses. The editor shows ingredient cost and margin as you type,
so a price can be set against what the dish actually costs. Choices carry their
own ingredients — grilled chicken adds 120 g of chicken — which is why a
build-your-own bowl lists only what every one of them uses.

## Money and quantities

Prices are whole ngwee everywhere: K95.00 is stored as 9500. Kwacha as a decimal
drifts once discounts, VAT and change are involved, and this system has to
balance to the ngwee at stage 7. One function converts for display, one reads
what is typed into a price box, and nothing else touches it.

Recipe quantities are thousandths of the ingredient's own unit: 180 against an
ingredient bought by the kilogram is 180 g, 150 against one bought by the litre
is 150 ml, and 500 of something counted singly is half. The screens take grams,
millilitres or a count and do that conversion in one place.

VAT is recorded per item as the share of the price that is tax, at 16% by
default, because Zambian shelf prices include it. Nothing is added at the till.

## Rules the server enforces

| Rule | Result |
| --- | --- |
| A cashier reading the menu | Allowed — the till, kitchen and stock room all need it |
| A cashier changing a price | 403 |
| Reusing an item code | 409 |
| A choice group with "least" above "most" | 422 |
| Hiding a section that still has live items | 409, with the count |
| An ingredient unit outside g, kg, ml, l, each | 422 |
| The same ingredient twice in one recipe | 422 |
| An unknown section, group or ingredient | 422 |

## Tested

- API suite against PostgreSQL: every row above, plus price history, sold-out
  switching, recipe costing and choice ordering.
- Browser run: owner edits a price with a reason, adds an item with a recipe and
  a size choice, adds a topping, adds an ingredient; a cashier sees the menu
  read-only with no edit buttons and is turned away from the choices screen.
- A fresh database builds 15 tables and loads 11 items, 20 choices and 24
  ingredients. Running the menu seed twice changes nothing.
- `vue-tsc` clean, production build clean, no horizontal scrolling at 390 px.

## Two bugs this stage found

**Recipe quantities were out by a factor of a thousand**, which made the
signature bowl cost K30,000 in ingredients. Caught by reading the margins rather
than the code: a 72% margin is plausible, −24,000% is not. Fixed, and every
seeded recipe is now checked against its selling price.

**One quantity in the starting menu survived the fix**, so Side salad showed
K662.70 of tomato. Caught the same way. The lesson for later stages: numbers on
a screen get read, not just tested for the right type.

## Not in this stage

Photographs of the dishes. The demo's images came from stock photography; real
ones for the menu board are worth taking properly, and uploads belong with the
document storage work at stage 10.
