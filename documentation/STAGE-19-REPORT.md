# Stage 19 report: a home screen for every account

The demo has four sign-in accounts (administrator, manager, kitchen, cashier),
and each one sees only the parts it is allowed to. The Green Buffet has seven
starting roles. Until now they all opened on the same Overview, with only the
sidebar trimmed. From this stage each role opens on a home screen built for
its job.

| Role | Opens on | What it answers |
|---|---|---|
| Owner | **Overview** + *month so far* + *team today* | How is the business doing, today and this month? |
| Manager | **Overview** + *month so far* + *team today* | How is service going, and who is on? |
| Administrator | **System** | Are accounts, sign-ins, backups and the server in order? |
| Accountant | **Money** | What came in, what is owed, what needs approving? |
| Cashier | **My till** | Is my till open, what have I taken, who is waiting? |
| Kitchen staff | **Kitchen display** (as in the demo) | What do I cook next? |
| Inventory staff | **Store room** | What is running out, on order, or moved? |

The first sidebar link is renamed to match: *Overview*, *System*, *Money*,
*My till* or *Store room*. Accounts whose home is not the Overview get a
**Business overview** link if they are allowed to see sales. A role the owner
creates later is placed by its permissions. For example, a role with only stock
permissions opens on the Store room.

## The screens

**Overview, owner and manager.** This is the demo's Overview, unchanged. Below
it are two new panels:
- *Month so far*: sales against the same days last month, paid orders, the
  average day, the best day, and the profit from the books.
- *The team today*: who is clocked in and since when, who has finished, who
  is on leave and who hasn't come in, plus any leave requests waiting for a
  decision.

**System, administrator.**
- Server and database status.
- Active and switched-off accounts.
- Sign-ins and wrong passwords in the last 24 hours, and anyone locked out.
- The last backup and its age. A warning appears when there is none, or it is
  more than a day old.
- Accounts by role, and accounts still on a temporary password.
- Recent changes from the activity log. Sign-ins are counted, not listed, so
  they don't bury real changes.

**Money, accountant.**
- Today's takings by payment method.
- This month so far against last month, and the profit and margin from the
  books.
- What is owed to each supplier.
- Every till closed this week, with what it was out by and the total short.
- Warnings when journal entries are waiting for approval, when this month's
  payroll isn't finished, or when the trial balance doesn't balance.

**My till, cashier.**
- Clock in and out (if the account is linked to a staff member).
- Whether their till is open and what the drawer should hold, or how the last
  till counted out.
- What they have taken today.
- Orders ready at the pass to call out, orders still unpaid on their till,
  their latest orders, and this till's takings by method.

**Store room, inventory staff.**
- Stock value, items below reorder level, deliveries on order, and what is
  owed to suppliers.
- A warning when items show less than nothing.
- What is running low, with a bar against the reorder level.
- Deliveries waiting to arrive, and the latest stock movements.

## Signing in as a kind of account

The sign-in screen is laid out like the demo's, with the logo, email and
password, and below them a card for each kind of account and what it sees.
The cards are Owner, Administrator, Manager, Accountant, Cashier, Kitchen
staff and Inventory staff. The seven standard kinds always appear, as the demo's
account cards do. A role the owner makes up appears once someone has an
account with it.

**`starter-accounts.ps1`** (new) makes one account for each standard kind
that doesn't have one yet: `admin@`, `manager@`, `accountant@`, `cashier@`,
`kitchen@` and `inventory@greenbuffet.zm`. It prints each temporary password
once, and each person must choose their own password at their first sign-in.
Running it twice changes nothing. Rename the accounts to real people under
Staff & roles.

- Pick a card and the screen says **Signing in as Manager**. The button reads
  **Sign in as Manager**.
- The server checks that the account really is that kind. A cashier who picks
  *Manager* is told "This is a Cashier account, not a Manager one. Choose
  Cashier and sign in again." No session is opened.
- That check runs only after the password is right, so it tells a guesser
  nothing. It doesn't count towards the 15-minute lock.
- Each computer remembers its last choice. The till PC stays on *Cashier*,
  and the office PC on *Accountant*.
- The list is public, because it shows before anyone signs in. It holds role
  names and descriptions only, never people or emails
  (`GET /api/v1/auth/roles`).

## How it is built

- `backend/app/api/v1/home.py` has six read-only endpoints under
  `/api/v1/home`: `cashier`, `stock`, `money`, `team`, `month`, `system`.
  Each has its own permission guard, so a custom role sees exactly the panels
  its permissions allow. The figures come from the same functions as the
  Inventory, Books and supplier screens, so the numbers always agree.
- `frontend/src/services/home.ts` decides which home an account gets.
  `views/HomeView.vue` shows it. The router sends the kitchen straight to
  `/kitchen`. `/overview` is the demo's Overview for anyone allowed to see it.

## Checks

- Signed in as each of the seven roles, on desktop and phone: each lands on
  its own home, with no errors and no sideways scrolling.
- Each role was refused every home endpoint it isn't entitled to (403).
- Signing in with the wrong kind of account is refused. The right kind works,
  and a wrong password gives the same answer as always (four new automated
  tests, 36 in total).
- All 29 screens were re-checked at phone and desktop width; tests and
  permission probes pass.

## Installing

Same as stage 18: extract the zip over `D:\The Green Buffet` and run
`.\scripts\update.ps1`. There are no new database columns.
