# Stages 14 to 16: customers, deliveries and functions

> **Removed in stage 20.** Deliveries, delivery areas, functions and the message outbox described here were taken out: The Green Buffet is a counter point of sale. Customers and stamp cards remain. See STAGE-20-REPORT.md.

> **Changed in stage 17.** Loyalty is now the demo's stamp card, not points:
> every paid bowl or burrito earns a stamp, and a full card makes the next one
> free. This report describes the points scheme as it was built at the time;
> see STAGE-17-REPORT.md for how loyalty works now.

**Delivered.** The system now knows who its customers are, tracks the orders
that have to leave the building, and handles functions with deposits that the
books treat correctly.

This is a point of sale and management system. Every order is taken by a
member of staff at the till; there is no customer-facing side and nothing a
stranger can reach. An earlier draft of these stages included a public
ordering site; it was removed, and this report describes what is actually in
the system.

---

## What was built

### Stage 14: customers

A customer record is created the first time somebody gives a phone number at
the till. The number is the identity, because in Zambia everybody has one and
almost nobody gives an email, and it is how the kitchen reaches them and how
their points are found at the counter.

The record is thin on purpose: a number, a name, an area, an address, what
they have spent and what they are owed in points. A restaurant does not need
more than that, and every extra field is one more thing to keep accurate.

Customers screen: search by name or number, correct their details, see their
points and the reason behind every change, and block somebody who is abusing
the service without deleting the history the books still need.

### Stage 15: deliveries and catering

An order marked **Delivery** at the till appears on the Deliveries board the
moment it is paid for. The board answers the three questions nobody else
tracks: is it cooked, who took it, and did it arrive. Mark the food ready,
name the rider and their number, and tick it off when they are back.

Delivery areas carry a fee, a usual time and a smallest order worth sending.
Seven Kitwe areas were seeded and all are editable on the Delivery areas
screen. The fees that came with the system are marked, on that screen, as
guesses to be checked.

A delivery charge is not food, so it has its own account (4200) in the books.
That is what lets the owner ask the only question that matters about delivery:
whether the fees cover the riders.

A catering deposit is **not income**. The food has not been cooked, and if the
function were called off the money would go back, so a deposit sits in its own
liability account (2150, "Customer deposits held") until the day. On the day,
the whole quote becomes a catering sale, the deposit is released against it,
and whatever is left becomes a customer debt in the same account any other
credit customer sits in. The screen will not let anybody take those steps out
of order.

### Stage 16: loyalty and messages

One point per kwacha spent on food. Delivery charges earn nothing, because the
restaurant does not keep that money. A hundred points are worth five kwacha
off, redeemed in whole hundreds so there is never a fraction to argue about at
the counter. Points are earned when an order is **paid**, never when it is
placed.

At the till, typing a customer's phone number finds them and offers their
points; the server checks the balance again before taking anything off.

Every balance has a ledger behind it, so when a customer says their points are
wrong there is a list to read back to them, with the reason and who changed it.

Messages are written down but not sent. There is no WhatsApp Business account
and no SMS shortcode, and getting either is an application to a company rather
than a line of code. Rather than pretend, the system queues the exact words,
and the Messages screen gives each one a WhatsApp button that opens the chat
with the message already typed. When an account does exist, one function
changes.

---

## Three things found by testing

**A cashier could give themselves points.** The permission guard on changing a
customer used `orders.update`, which a cashier holds. Points are money, so a
cashier could have put five thousand points on a friend's number. A new
`customers.manage` permission now guards points and blocking, and cashiers do
not have it.

That fix exposed a second problem: a new permission is worthless if the roles
in a database that already exists never receive it. Running the update now
grants genuinely new permission codes to the system roles that should hold
them — and only genuinely new ones, so a permission an administrator removed
on purpose stays removed.

**Adding columns to a live table did nothing.** `create_all` makes tables that
are missing and never touches a table that already exists, so these stages,
which add twenty columns to `orders`, would have been invisible on a
restaurant that had been trading for a month. `app/core/schema_update.py` now
compares every model against the live database and adds what is missing. It
only ever adds: nothing there drops a column, changes a type or deletes a row.

**A missing photo filled the screen with its own alt text.** One product photo
would not load during testing and the dish card became a wall of giant text
where the picture should have been. A photo that fails now falls back to the
dish's initials.

---

## What these stages refuse to do

| Someone tries | What happens |
| --- | --- |
| Spend points they do not have | Refused, with the real balance named |
| Spend part of a block of points | Refused |
| Settle a function before it has happened | Refused |
| Take a deposit larger than the quote | Refused |
| Cancel a function that has a deposit on it | Refused; refund it through the books first |
| Cashier awards points | Refused |
| Cashier blocks a customer | Refused |
| Cashier invents a delivery area | Refused |
| Stranger reads the customer list | Refused |

---

## Checked before this was called finished

- A delivery driven end to end against a real server and a real PostgreSQL:
  taken at the till, paid, cooked, given to a rider, delivered, off the board,
  with the points earned and the books still balanced.
- 20 permission checks covering the cashier, the owner and a stranger with no
  token at all, including that no public endpoint exists any more.
- The 32 tests from stage 11, still passing.
- All 23 screens opened in a real browser at phone width: no horizontal
  overflow anywhere, no console errors.
- The trial balance after all of it: 95,762.93 on each side, balanced.

## What was left out on purpose

- **Anything customer-facing.** This is a staff system. Orders are taken at
  the till, not by customers.
- **Actually sending messages.** Needs a WhatsApp Business or SMS gateway
  account, which is an application to a company. The words are written and
  WhatsApp opens with them typed.
- **A map.** Deliveries work by area. A map bills per load and, inside one
  town, the area list does the same work.
- **Scheduling an order for later.** The column is there; the screen is not.
