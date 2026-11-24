# Stage 6 report — stock, suppliers and purchases

Five new tables, nothing existing altered. `.\scripts\update.ps1` creates them.

## The idea

The movements table is the truth. Every change to an ingredient is one row that
is never edited: bought in, used in an order, wasted, counted and corrected.
What is "on hand" is the sum of those rows, cached alongside so the screen does
not add up thousands of rows on every load. If the two ever disagree, the
movements win.

That is the same discipline as the till and, at stage 7, the books: write once,
correct by writing again.

## What you can do

**Stock** (`/stock`)

Every ingredient with what is on hand, what it is worth, and the level at which
to reorder. Three figures across the top: the value of the store room, how many
items are at or below their reorder level, and how many have gone negative.

Four actions per ingredient:

- **Count** — a stocktake. Say what is on the shelf and the difference is
  recorded as its own movement. This is how a negative figure is put right.
- **Waste** — what was thrown away, which the system refuses to take as a
  positive number.
- **Add** — stock arriving outside a delivery.
- **Reorder at** — the level that marks it for ordering.

"Show movements" opens the ledger: what changed, by how much, what was left
afterwards, and against which order or delivery.

**Buying in** (`/purchases`)

Suppliers with their contact and what has been spent with them, and deliveries
written as a purchase first. Stock only moves when the delivery is checked in,
and the price paid on that delivery becomes the ingredient's cost from then on,
so margins follow what you actually pay.

## Stock leaves on its own

When an order is paid, the system reads the recipes behind it — the product's
own recipe, plus the recipe behind every choice the customer made — and writes
one movement per ingredient. Two build-your-own bowls with brown rice, grilled
chicken and avocado took out 360 g of rice, 240 g of chicken, one avocado and
120 g of leaves, each against the order number.

This is what the recipes in stage 3 were for, and it is why the option recipes
mattered: a bowl's chicken comes from the choice, not the bowl.

## Stock is allowed to go negative

A kitchen that has run out still sells the last bowl, and the figure that
follows is the honest record of it. Negative items are counted on the screen
and named in a line of their own, because they mean one of three things: an
opening count was never done, a delivery was not checked in, or a recipe is
wrong. A count puts it right.

In testing, Mixed leaves went to −120 g immediately, because nothing had ever
been counted in. That is the system working, not failing.

## Rules

| Rule | Result |
| --- | --- |
| Two suppliers with the same name | 409 |
| The same ingredient twice on one purchase | 422 |
| Checking the same delivery in twice | 409 |
| Cancelling a delivery already in stock | 409: record a return instead |
| Waste entered as a positive number | 422 |
| An adjustment of zero | 422 |
| An order paid twice (a retry) | One set of movements, not two |
| Inventory staff adjusting stock and buying | Allowed — the role holds both |
| A cashier touching stock | 403 |

## Tested

Against PostgreSQL: a supplier, a three-line delivery at K1,150 checked in,
costs updated from the delivery, two bowls sold and every ingredient movement
checked against the recipe by hand. In the browser: a two-line purchase written
and checked in, a count, a waste, the movement ledger, the low-stock filter, and
no horizontal scrolling at 390 px.

## Worth doing now

Count the store room once and enter it through **Count** on each ingredient.
Until that is done, every figure on the stock screen is only "what has moved
since the system was installed", and most items will read negative as they sell.

## Not in this stage

- **Stock taken when food is made rather than when it is paid for.** Paid is
  the simpler and safer point, and for a buffet the gap is seconds.
- **Supplier invoices as money owed.** The purchase records what was spent; the
  creditors ledger that tracks what is still owed is stage 7.
- **Counting by batch or expiry date.** Worth adding only if you start holding
  stock long enough for it to matter.
