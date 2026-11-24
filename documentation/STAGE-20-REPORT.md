# Stage 20 report: a counter point of sale, with the real menu

The Green Buffet is run like a fast-food counter. Customers order and pay at
the till, the kitchen cooks from the screen, and the food is handed over at
the pass. This stage removes everything built for customers ordering by
themselves, puts the printed menu into the system, and makes signing in one
tap, as in the demo.

## 1. Customer ordering removed

These were built for customers ordering on their own, so they are gone:

| Removed | What it was |
|---|---|
| Deliveries | A board for orders going out with a rider |
| Delivery areas | Delivery zones and their fees |
| Functions | Event and catering bookings with deposits |
| Messages | WhatsApp and SMS texts telling customers their order was ready |
| "Delivery" at the till | The till now takes **Takeaway** or **Eat in** only |
| "Block from online ordering" | On the Customers screen |
| WhatsApp and SMS settings | On the Settings screen |

Their screens, sidebar links and server routes are removed. The server
refuses a delivery order. Their database tables are left in place with
whatever they hold, so no history is lost and the books don't change.

**Kept:** customers and stamp cards. A regular gives their phone number at
the counter and collects a stamp, as in the demo. Feedback stays too, since
staff write down what customers say at the counter.

**The cashier's sidebar is trimmed, as in the demo.** A cashier sees My till,
Till, Orders, Kitchen display, Customers & stamps and clocking. Payments, End
of day, Menu, Promotions and Feedback are for managers.

## 2. The real menu

Everything on *The_Green_Buffet_Menu_final.pdf* is in the system at the
printed prices.

| Section | Items |
|---|---|
| Bowls | Build your own bowl K75 · Garlic barbecue chicken bowl K75 · Birria beef bowl K75 · Garden salad K60 |
| Burritos | Garlic barbecue chicken burrito K100 · Birria beef burrito K100 · Build your own burrito K100 |
| Breakfast | Breakfast burritos (2 per order) K80, 08:30 to 11:30 |
| Dips | Garlic · Sweet onion teriyaki · Chili, K20 each |
| Drinks | Strawberry lemonade refresher K50 · Lychee refresher K50 |

The choices at the till:
- **Base**: white, yellow or brown rice.
- **Protein**: garlic barbecue chicken or birria beef.
- **Bowl toppings**: up to eight. **Five are included, then K10 for each one
  over five**, which the till adds automatically and shows as it happens
  ("+K20.00 for 2 extra").
- **Burrito toppings**: up to five.
- **Extras**: protein K20, cheese K15, sauce K10, veggies K15.
- **Add a dip**: K20 each.

Bowls and burritos fill the stamp card.

**Three things the printed menu doesn't say. Check them on the Menu screen:**
1. The price of a build-your-own bowl. It is set to K75, like the signature
   bowls.
2. Which toppings are "the veggies displayed". The demo's eight are used:
   sweetcorn, black beans, tomato, avocado, peppers, lettuce, red onion and
   baked beans.
3. Ingredient costs. These are estimates, so the margin figures have
   something to work with. Put the real costs in on the Ingredients screen.

**How it gets in.** The first `update.ps1` after this stage loads the printed
menu once. Later updates leave the menu alone, so changes made on the Menu
screen are kept. `.\scripts\load-menu.ps1` loads it again at any time.
Nothing is deleted: old items such as the smoothies and juices are switched
off, so old receipts and reports keep their names.

**The "N included" rule** is new and works for any choice group. On
**Menu → Choices**, open a group and set *Included in the price* and *Charge
for each one over that*. The Settings figure "charge per topping over five"
stays in step with it.

## 3. One-tap sign-in, like the demo

Each card on the sign-in screen now lists that kind of account's people.
- Where there is one person, a tap fills in their email and puts the cursor
  on the password.
- Where there are several (three cashiers, say), tap the card, then tap the
  person's name.
- Kinds with no account yet say so.

Only the password is typed. The server still checks that the account is the
kind chosen.

This screen shows staff names and emails before anyone signs in, which suits
a counter system on the restaurant's own network. The owner can switch it off
under **Settings → Sign-in screen**, so everyone types their email instead.
Passwords are never shown.

## Checks

- A build-your-own bowl with seven toppings and a dip comes to K115: K75 +
  2 × K10 + K20. The till showed K95 before the dip, and the server charged
  the same.
- A delivery order is refused (422).
- Loading the menu twice changes nothing the second time.
- Each of the seven roles signs in with one tap and lands on its own home,
  on desktop and phone.
- 25 of 25 screens are clean at phone and desktop width.
- 36 automated tests pass. All 29 permission checks pass, including four new
  ones confirming the removed screens are gone.

## Installing

    Expand-Archive green-buffet-stage20.zip -DestinationPath "D:\The Green Buffet" -Force
    cd "D:\The Green Buffet"
    .\scripts\update.ps1

The update adds two columns for the "N included" rule and loads the printed
menu. Then press Ctrl+F5 in the browser.
