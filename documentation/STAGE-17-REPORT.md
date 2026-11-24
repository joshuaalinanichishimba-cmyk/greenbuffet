# Stage 17: matching the demo

**Delivered.** The production system now has the demo's staff side: the same
screens in the same sidebar, the same look, fonts and logo, and the demo's
stamp card in place of points. The Till and the back office, which the demo
does not have, sit alongside it without changing how the demo's part reads.

## Why the two had drifted apart

The first sixteen stages were built from the roadmap written at stage 0, not
from the demo's screens. The roadmap covered the same ground, so the system
did most of what the demo did, but it was organised differently, looked
different, and lacked several of the demo's screens. The demo file itself
had been uploaded with the project the whole time. It builds every screen
with JavaScript, which is why fetching the live page only ever showed its
title; running it in a browser showed everything.

## The screens, demo against system

| The demo's screen | In the system |
| --- | --- |
| Overview | Rebuilt to match: sales, orders and average against the same time yesterday, sales by hour, live orders, how people paid, latest orders, best sellers, stock alerts, rating, base prep time |
| Orders | Rebuilt: Active, All today, Collected, Cancelled, Last 14 days, with the next step on each row |
| Kitchen display | Rebuilt as the demo's full-screen board: "To make now" prep list, timers that turn red at 15 minutes, choices labelled base, protein, toppings |
| Messages | Kept; restyled |
| Payments | **New**: every payment and refund, by method, and the mobile money and card payments with no reference |
| End of day | **New**: money in by method, refunds, discounts, net sales, items sold, wastage, each drawer's count, signature lines |
| Sales analytics | **New**: the demo's figures, daily sales, payment mix, a weekday-by-hour grid, best sellers, most picked toppings. The old downloads are on its second tab |
| Menu | **New** default view: price and availability per section, build options with in-stock ticks, which sections earn stamps. The full editor is on the next tab |
| Promotions | **New**: codes checked on the server, counted when the order is paid |
| Inventory | Rebuilt: level bars against the reorder point, a shopping list worked out from those levels, movements, and Buying in alongside |
| Feedback | **New**: what customers say at the counter, on the phone or on WhatsApp |
| Staff & roles | Staff and Roles joined under one sidebar entry |
| Settings | Rebuilt: business details, service and loyalty, opening hours, integrations, and the activity log on the second tab |
| What comes next | Not built. It is the demo's sales page, not a screen a restaurant uses |

Not in the demo, kept in a **Back office** group: Customers & stamps,
Deliveries, Delivery areas, Functions, The books, Journal, Staff clocking,
Payroll. The **Till** sits under Today, because a point of sale needs one.

## The look

The colours, buttons, pills, inputs, tables and segmented tabs are the demo's
own rules, copied from the demo file into `frontend/src/styles.css`, so
changing a colour there changes it everywhere, including the dark theme the
demo also had. The sidebar, top bar, cards and headings were measured from
the demo as it renders in a browser.

The fonts are the demo's, Montserrat and Karla, but bundled with the app
rather than fetched from Google. The till has to look right with the
internet down.

The logos are the demo's: the bowl mark in the sidebar and the full
"THE GREEN BUFFET, A Bowl That Describes you" wordmark on the sign-in page.

## Stamps instead of points

As the demo proposes: every paid bowl or burrito earns a stamp, and a full
card (eight by default, set in Settings) makes the next one free.

- Only sections marked "Earns a stamp" on the Menu screen count. The update
  marked Bowls and Burritos; after that it is the manager's choice.
- The free item is the cheapest bowl or burrito on the order, taken off by
  the server when the order is made. Nobody has to press anything.
- The full card is taken when the order is made and given back if that order
  is cancelled, so the free bowl can't be claimed twice.
- The free item earns no stamp of its own.
- Every change is in a ledger with its reason.

Points earned before this stage are kept on each customer's record and in
the database, but no longer used.

## Found by testing, and fixed

- **A typed promo code could be silently dropped.** A cashier who typed a
  code and went straight to payment paid full price: the till sent the code
  only if its preview had already come back. It now always sends what is in
  the box, and the server applies it or refuses it with a reason.
- **The first click on "Go to payment" could be lost.** Leaving the promo or
  phone box re-checked it, which redrew the panel under the mouse between
  press and release. The boxes now re-check only when their text changes.
- **The wait time could read over 1,000 minutes.** The top bar counted every
  kitchen ticket ever left unfinished. It now counts today's.
- **Yesterday's tickets stayed on the kitchen wall.** The board now shows the
  trading day; older tickets remain on the Orders screen.
- **Stock value went negative.** An item counted below zero added negative
  money. The value now counts what is physically on the shelves.
- **Settings saved keys nothing reads.** A misspelt setting was stored and
  ignored. Unknown keys are now refused, and numbers are range-checked.
- **A table pushed the Build options screen wider than a phone.**

## What these stages refuse to do

| Someone tries | What happens |
| --- | --- |
| Cashier creates or stops a promotion | Refused |
| Cashier changes the kitchen's base time | Refused |
| Cashier reads sales analytics | Refused |
| Cashier fills their own stamp card | Refused |
| A stopped or unknown promo code | Refused, with the reason |
| A promo code under its minimum order | Refused, with the minimum named |
| A setting nothing reads, or a stamp card of nought | Refused |
| A stranger reads the overview, payments, end of day or promotions | Refused |

## Checked before this was called finished

- 32 backend tests and 32 permission checks pass.
- Stamps and promo codes driven through real sales: earned only on bowls and
  burritos, cheapest free, card returned on cancel, codes refused correctly.
- A full sale driven through the till in a browser: promo code, stamp card,
  payment, receipt. The code applied, its use was counted, the stamp earned.
- All 29 screens opened in a browser at phone and desktop width: no overflow,
  no errors.
- Each screen compared with the demo's screenshot.
- Trial balance after all of it: balanced.

## Left out on purpose

- The demo's customer site, which this system deliberately does not have.
- "What comes next", the demo's sales page.
- Gateway fees and settlement on Payments: there is no gateway. The
  operator's reference is what the system can honestly track.
- Ratings collected from customers automatically: there is no customer site,
  so staff write feedback down.
