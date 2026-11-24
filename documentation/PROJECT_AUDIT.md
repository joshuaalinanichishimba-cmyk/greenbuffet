# The Green Buffet: project audit

Audited 24 November 2026, against two briefs: *Restaurant Business
Management System: Audit, Improvement and Development*, and *Ownership,
User Management, Access Control and Business Oversight*.

**How this was checked.** I read the code. I listed every route, table and
permission from the running system. Then I ran real transactions against a
test copy of the database: sales, split payments, retried payments, stock
deductions, refunds, two owner accounts, disabling accounts and resetting
passwords. Where this document says something **works**, it was run and seen
to work. Where it says **not verified**, it was not run here. Nothing on your
computer or in your data was changed for this audit.

---

## 1. What the system is today

| Part | What it is |
|---|---|
| Server | Python 3.12, FastAPI, SQLAlchemy 2, PostgreSQL. One process (`run_server.py`). It runs on the restaurant PC and is started by a Windows scheduled task. |
| Screens | Vue 3 + TypeScript, built by Vite and served by the same server. It works on the restaurant network with no internet. |
| Size | 133 API operations, 45 database tables, 36 permission codes, 7 starting roles, 32 screens. |
| Money | Whole ngwee everywhere: no floating-point money. |
| Stock | Quantities are held in thousandths of a unit (grams, millilitres, or thousandths of an item). |
| Books | Double entry. `post()` refuses any entry that does not balance. |
| Numbers | Order, purchase and journal numbers come from a locked counter table, so they never repeat. |
| Retries | An idempotency key on order creation and payments means a double tap or retry is never charged twice (verified). |
| Audit log | One table. Each entry holds who, area, action, detail, reference, before and after. No route edits or deletes it. |
| Sign-in | Email and password, argon2 hashes, 8-hour tokens, lockout after 5 wrong passwords in 15 minutes. |
| Git | **There is no Git repository** in the project folder, here or on the PC. Checkpoints so far are the stage zips and the database backups. |

### How the parts connect

A sale goes from the **Till** to an **Order** to **Kitchen tickets**. When it
is paid, the system:
1. records a **Payment** on the cashier's **Shift**;
2. takes **stock** from the recipes, once;
3. posts a **journal entry** (sales, VAT, cost of sales, stock);
4. stamps the customer's **loyalty card** and counts any **promo** used.

The reports, dashboards and books all read from these same records. Purchases
add stock and post to the books. Supplier payments post to the books. Payroll
runs post to the books. Shift variances post to the books.

---

## 2. Every feature, classified

Key:
1. Working and useful.
2. Working, needs improvement.
3. Partly built.
4. Demonstration only.
5. Broken.
6. Duplicate.
7. Unnecessary.
8. Missing and needed.

### Selling

| Feature | Class | Evidence and notes |
|---|---|---|
| Till: menu grid, choices, notes, quantity | 1 | Used daily. Choice rules ("5 toppings included, K10 after") were verified at K115. |
| Takeaway / eat in | 1 | Delivery removed in stage 20. |
| Phone or WhatsApp orders keyed in by staff | 2 | Possible as takeaway with a customer name and phone. There is no "phone order" label for reports. |
| Held orders | 3 | An unpaid order stays open and can be paid later. There is no "hold / recall" button. |
| Changing an order before payment | 8 | Not possible: the order must be cancelled and re-entered. |
| Cancellation | 2 | Needs `orders.cancel` and a reason, and is audited. It is blocked once money has been taken. |
| Cash payment, change worked out | 1 | Verified: K100 tendered on K50 gave K50 change. |
| Split payments (cash + mobile money) | 1 | Verified. |
| Mobile money (Airtel, MTN, Zamtel) | 2 | The reference is recorded, but **the same reference can be used twice** (verified: accepted). There is no pending / confirmed / failed status: a payment counts as received when the cashier enters it. |
| Card, on account | 2 | Recorded like mobile money, with no settlement matching. |
| Bank transfer | 8 | Not a payment method. |
| Retried payment charged once | 1 | Verified with an idempotency key. |
| Discounts | 2 | **Any cashier can type any discount**: a 98% discount was accepted with no approval (verified). The amount is recorded on the order, but there is no limit, reason or approval. |
| Promotion codes | 1 | Checked on the server, counted, and turned on or off by managers. |
| Refunds | 2 | Partial or full, needs `orders.cancel` and a reason, and is audited. A cashier was refused (403, verified). There is no request-then-approve step and no refund limit. |
| Receipts | 2 | Thermal-width print (stage 21) and reprint from Orders. **Reprints are not audited.** There is no PDF download, and no ZRA fiscal reference. |
| Stamp card loyalty (8 bowls or burritos earn a free one) | 1 | Simple and server-side. Keep it. |
| Customer list | 1 | Phone lookup at the till, plus the stamp card. |
| Feedback | 1 | Staff write down what customers say. It is small. |

### Cash and shifts

| Feature | Class | Evidence and notes |
|---|---|---|
| Open till with float | 1 | One open till per cashier, audited. |
| Close till: counted, expected, variance | 2 | Works, and the variance posts to the books. But **it is not blind**: the till screen and My till both show "the drawer should hold K…" before the count. Explaining a variance is optional, and no manager reviews it. |
| Expected cash takes off cash refunds | 1 | Cash taken is net of cash refunds. |
| Cash drops to the safe, petty cash, cash added, withdrawals | 8 | None. Moving cash out of the drawer today shows up as a shortage. |
| Handover between cashiers on one till | 8 | Each cashier opens their own till. There is no handover. |
| Bank deposits, mobile money and card reconciliation | 8 | None. |

### Kitchen

| Feature | Class | Evidence and notes |
|---|---|---|
| Live board: new, preparing, ready, collected | 1 | Live updates were fixed in stage 18 (a new order shows in under 2 s). There is also an undo and a chime. |
| Waiting time, colour by age, prep list | 1 | |
| Stations (kitchen, cold, juice bar) | 2 | The brief says only add stations if the kitchen needs them. One kitchen probably means "Everything" is all that's needed. Keep it, since it is cheap. |
| Tickets for unpaid orders | 8 | *Corrected in stage 22:* tickets are already sent only when the order is paid. No change was needed. |
| Delayed-order alert to managers | 3 | Ages turn red on the board only. There is no alert. |
| Telling the cashier an order is ready | 2 | My till lists "Ready at the pass", refreshed every 20 s. There is no sound. |
| Kitchen ticket printing | 8 | |
| Who in the kitchen did what | 2 | Recorded as the signed-in account, which is one shared kitchen login in practice. |
| "Wait" figure | 5 | **It counts every ticket never marked collected.** On the test data it says "386 min". If staff stop tapping *Collected*, the number becomes meaningless. Needs a cut-off. |

### Menu, recipes, costing

| Feature | Class | Evidence and notes |
|---|---|---|
| Sections, items, choices, prices | 1 | The printed menu is loaded (stage 20). |
| Price history | 1 | `price_changes` records old, new, who and reason. Past orders keep their prices (lines store the unit price). |
| Scheduled price changes, margin shown on the change | 8 | |
| Sold-out switch | 1 | |
| Recipes (item and choice), stock deduction | 1 | Verified: 2 refreshers took exactly 700 ml, once. |
| Food cost %, margin per item | 2 | Analytics shows margins, but the ingredient costs are **my estimates** (stage 20) until real ones are entered. |
| Unit conversion (kg↔g, crate↔each) | 3 | Each ingredient has one unit, and purchases must be in that unit. There are no pack sizes. |
| Recipe versions, yield | 8 | |

### Stock and purchasing

| Feature | Class | Evidence and notes |
|---|---|---|
| Stock levels, value, reorder levels, shopping list | 1 | |
| Movements history | 1 | Every change is a `stock_moves` row with a running balance. |
| Count (one item) and adjust (signed, with a kind) | 2 | Works item by item. There is no whole-store count sheet comparing theoretical with counted, and no approval for large adjustments. |
| Waste | 3 | Waste is only an adjustment with kind "waste" and a note. There are no waste reasons, no "who", and no waste report. |
| Expiry dates, batches | 8 | |
| Suppliers, purchases, receive, pay, owed and ageing | 1 | A purchase posts to the books on receipt, and a payment posts too. |
| Partial deliveries, damaged goods | 8 | Receiving takes the whole purchase as ordered. |
| Duplicate supplier invoice check | 8 | |
| Supplier price comparison | 3 | Purchase lines keep unit costs, but nothing compares them. |
| Approval thresholds for purchases | 8 | |
| Attaching a receipt photo | 3 | There is file storage (`documents`) for photos, but it is not linked to purchases. |

### Books

| Feature | Class | Evidence and notes |
|---|---|---|
| Chart of accounts, journal, approve, reverse | 1 | |
| Trial balance, P&L, balance sheet, cash flow | 1 | The trial balance balances after the audit sales (verified). |
| Automatic postings: sales, cost of sales, purchases, supplier payments, payroll, till variances | 1 | |
| Expenses (rent, ZESCO, gas, fuel, …) | 3 | Only as manual journal entries. There is no expense form, no categories screen and no receipt attachment. |
| Bank reconciliation | 8 | |
| Closing a period | 8 | Nothing stops a back-dated entry into a finished month. |
| Fixed assets | 3 | There is an `assets.manage` permission, but no screen. |

### Tax

| Feature | Class | Evidence and notes |
|---|---|---|
| VAT | 2 | **Every item assumes 16% VAT inside the price**, and receipts print "VAT included". The brief rightly says not to assume the restaurant is VAT-registered. **Needs your answer.** |
| TPIN, ZRA Smart Invoice | 8 | Nothing is built. This needs ZRA credentials and an approved integration. |
| Turnover tax | 8 | If the business is on turnover tax rather than VAT, receipts and reports must change. |

### People and payroll

| Feature | Class | Evidence and notes |
|---|---|---|
| Employee records, documents | 1 | |
| Clock in and out, My clocking | 1 | Stage 21. |
| Rosters, late arrivals, missed shifts | 8 | There is no schedule, so lateness can't be measured. |
| Attendance corrections with approval | 8 | |
| Leave requests, approval, balances | 1 | |
| Payroll: PAYE, NAPSA, NHIMA, payslips, approve, pay, books | 1 | Rates are editable, and each run keeps the rates it used. **Not checked here against current official 2026 rates.** That must be done before the first real payroll. |
| Overtime, advances, bonuses, daily or hourly wages | 8 | Only monthly basic, allowances and unpaid days. |

### Accounts, permissions, security

| Feature | Class | Evidence and notes |
|---|---|---|
| Individual accounts, roles, custom roles | 1 | |
| Permission codes checked on the server | 1 | 36 security tests and 29 permission probes pass. A cashier is refused books, payroll and refunds. |
| Disabling an account cuts off its open session | 1 | Verified: the very next request is refused (403). |
| Password reset ends old sessions | 5 | **The old session kept working after a reset** (verified, 200). It lasts up to 8 hours. |
| Two owners with equal power | 2 | A second owner can be made, with full access (verified). **But owner 2 can switch off owner 1** (verified, 200), and nothing stops both owners being switched off by a third admin. |
| One person, several roles | 8 | Each account has one role. |
| Extra or removed permissions for one person | 8 | Only by making a whole new role. |
| Login history, active sessions, sign out everywhere | 3 | Sign-in attempts are kept (with IP). There is no sessions list and no way to revoke one. |
| Two-factor sign-in for owners | 8 | |
| Audit log | 2 | It covers sales, till, stock, menu, prices, users, roles, settings, books and payroll, with before and after values. It doesn't record the role at the time, success or failure, or the device. It records receipt reprints and page exports nowhere. It has search, but no CSV export. |
| Approval centre, notifications | 8 | Only journal entries and payroll have approvals. There is no notification centre. |
| System health | 2 | The System home shows the database, backups and lockouts. There are no amber/grey states, and no check of failed postings. |

### Operations

| Feature | Class | Evidence and notes |
|---|---|---|
| Opening and closing checklists, temperatures, cleaning | 8 | |
| Equipment and faults | 8 | |

### Running the system

| Feature | Class | Evidence and notes |
|---|---|---|
| Runs on the restaurant PC with no internet | 1 | Fonts are bundled, nothing is fetched from the internet, and other devices use the restaurant Wi-Fi. |
| Load shedding | 2 | The data is safe: PostgreSQL survives power cuts. But the till stops if the PC or router loses power. A UPS is the answer, and is documented below. |
| Offline till if the PC itself is unreachable | 8 | Large to build, with real risks of double sales. See the plan. |
| Backups, scheduled backups, restore into a test database | 2 | Scripts exist (`backup.ps1`, `schedule-backup.ps1`, `restore.ps1`). **A restore has not been verified on your PC.** |
| Status, fix-database, reset-owner, update | 1 | |
| Test sign-in mode | 1 | For trying out only, and refused in production. **It must be switched off before real use.** |

---

## 3. Leftovers to clean up

**Duplicates.**
- *Reports → Downloads* (CSV files) and *Sales analytics* overlap. Downloads
  should become the export button on each report, not a separate page.
- `/reports/dashboard` is no longer used by any screen.
- The old *Payments* page and the *Money* home show the same takings.

**Demonstration-only.** None in the running screens. Every figure comes
from the database. One estimate the screen doesn't flag: ingredient
costs from the menu load are marked in their notes, but the margin figures
don't say they are estimates.

**Unused, from the removed customer-ordering stages.**
- Columns on `orders`: `channel`, `track_status`, `public_token`, `zone_*`,
  `address`, `rider_*`, `delivery_fee_ngwee`, `points_*`.
- Tables: `delivery_zones`, `catering_bookings`, `messages`, `points_entries`.
- Permissions: `dispatch.manage`, `catering.manage`.
- The `services/messaging.py` module.

They do no harm and hold no current data of value. They can be removed later,
with a backup, if you approve.

---

## 4. What must stay unchanged

- How money is stored (ngwee), and how stock is stored (thousandths).
- The double-entry rule.
- The counters, idempotency keys and the audit log table.
- Order lines keep their own price, name and VAT, so history never changes.
- Server-side permission checks.
- The kitchen live connection fix (announce after commit, from any thread).
- Your existing accounts, menu, orders, payments, shifts, stock moves, journal
  and payroll records.
- The scripts you already use: `update`, `status`, `fix-database`,
  `reset-owner`, `backup`, `restore`.

---

## 5. Risks in the proposed changes

| Change | Risk | How it is handled |
|---|---|---|
| New columns (payment status, session version, …) | An update fails half-way | Columns are only ever added, then filled in, then made required (the existing `add_missing_columns`). Take a backup before each update. |
| Blind cash count | Cashiers lose a check they rely on | Show the expected figure only *after* the count is saved. Managers still see it. |
| Mobile money "pending until confirmed" | Slows the queue if every payment needs a manager | The cashier confirms after seeing the SMS on the till phone, and a manager matches against the statement at end of day. The confirmation is audited. |
| Discount limits | Annoys staff, and a limit set too low blocks real promotions | Promo codes are unaffected. The limit is a setting, and a manager can approve above it on the spot. |
| Ending sessions on password reset | Everyone signed out at once if this is done wrongly | A per-account version number: only that account's sessions end. |
| Owner protection | Both owners locked out | You can't switch off the last active owner, and you can't switch off another owner without the second owner confirming. `reset-owner.ps1` on the PC stays as the last resort. |
| Dropping leftover tables | Losing data you later want | Not done without your yes, and only after a backup. |
| Offline till | Double sales, money recorded twice | Not started until the in-restaurant setup plus a UPS is shown to be insufficient. |
| No Git | No way to roll code back | Proposed: a Git repository on the PC (free, and it needs no internet). |
