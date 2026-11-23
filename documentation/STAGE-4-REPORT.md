# Stage 4 report — the till

The system now takes money. New tables, so update with `.\scripts\update.ps1`.

## What a cashier does

1. **Opens the till**, counting the float into the drawer and entering it.
2. **Taps items.** Anything with choices opens the builder: base, protein,
   toppings, sauce, size, with the running total at the bottom and "Add to the
   order" disabled until the required choices are made.
3. **Goes to payment.** Cash, Airtel Money, MTN MoMo, Zamtel Kwacha, card or on
   account. Cash takes what the customer handed over and shows the change
   before the payment is recorded. Mobile money and card ask for the operator's
   transaction number, so the money can be matched later.
4. **Prints the receipt** — 72 mm, the business name, the order number, each
   line with its choices, the split across payment methods, the change, and the
   VAT included in the total.
5. **Closes the till**, counting the drawer. The system says what should be
   there and records the difference under the cashier's name.

The Orders screen shows everything taken today with its totals, split by
payment method, with a receipt for any order and refunds for the paid ones.

## What the server decides, not the browser

The browser sends what was ordered. Prices, totals, VAT and change are all
worked out on the server from the menu as it stands at that moment, and the
price is then copied onto the order line, so a price change tomorrow cannot
alter what today's receipt says.

| Rule | Result |
| --- | --- |
| Taking an order with no till open | 409 |
| A sold-out item or choice | 409, naming it |
| Fewer choices than a group requires | 422: "choose 1 from Base" |
| More than a group allows | 422: "at most 1 from Base" |
| A choice not offered with that item | 422, naming both |
| Mobile money or card with no transaction number | 422 |
| On account with no customer name | 422 |
| Paying more than the order owes | 422 |
| Paying an order that is already paid | 409 |
| Cash given less than the amount | 422 |
| Cancelling an order that has been paid | 409: refund first |
| Refunding more than was taken | 422 |
| Closing a till with unpaid orders on it | 409, with the count |
| Closing someone else's till without staff.manage | 403 |
| A cashier cancelling or refunding | 403 |

## Money that cannot be taken twice

Every write carries an idempotency key. If the same order or payment request
arrives again — a double tap, a retry on a bad connection — the stored answer
comes back instead of a second order or a second charge. Tested by sending the
same order twice: one order, one number.

## Partial and split payments

An order can be paid in pieces: K50 on Airtel Money, the rest in cash. It stays
open until the balance reaches zero, then it is marked paid with the time. The
shift summary splits takings by method, and only the cash counts towards what
should be in the drawer.

## Refunds

A refund is a new row, never an edit of the original payment. It shows on the
same order, reduces the day's takings, and reduces the cash expected in the
drawer when it was given in cash.

## Tested

Against PostgreSQL, with a real worked example: a large quinoa bowl with
grilled chicken, avocado, feta and chilli at K162, two orange juices at K70,
K232 total holding K32 of VAT; K50 by Airtel Money, K182 cash from K200 tendered
with K18 change; a K20 refund; the till closing at K362 expected against K357
counted, K5 short. Every row in the table above was checked. In the browser:
the full flow from opening the till to printing the receipt and closing the
drawer, a cashier's own till, and no horizontal scrolling at 390 px.

## One bug this stage found

An order paid in full stayed marked "open", because the payment just written
was not yet visible to the order's own total. The till looked right and the
books would not have balanced. Fixed by re-reading the order after the payment
is written, before deciding whether it is settled.

## Not in this stage

- **Taking mobile money through the system.** Payments are recorded as taken on
  the operator's own device, which is how most Zambian restaurants run it. Live
  Airtel, MTN or Zamtel collection needs a merchant account and is a stage of
  its own once one is chosen.
- **The kitchen screen.** Orders carry their station already; stage 5 shows them.
- **Taking stock out as items sell.** The recipes are there; stage 6 uses them.
