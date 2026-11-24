# Stage 22: protection, your decisions, and cash control at the till

Stage 22 covers Phase 0 and Phase 1 of DEVELOPMENT_PLAN.md. It also carries
out the four decisions you made after the audit, and two Phase 5 safeguards
that could not wait: one owner cannot switch the other off, and a password
reset ends the old session.

## Your decisions, as carried out

| Decision | What was done |
|---|---|
| VAT: registered at 16%, owner can change it | Settings → Tax has a "VAT registered" switch and the rate. Switched off, sales carry no VAT, the receipt drops the VAT line and the "Prices include VAT" footer, and the books post no VAT. An item marked 0% stays exempt either way. |
| Administrator and Inventory staff removed, their features moved | On update, Administrator accounts become **Manager** and Inventory staff accounts become **Kitchen**. Nobody loses an account. The kitchen role can now adjust stock, and the manager's home has Store room and System panels. Five kinds of account remain: Owner (two), Manager, Accountant, Cashier, Kitchen. |
| Cash and till first, GitHub when done | Done in that order. `push-to-github.ps1` sends the code to GitHub from the restaurant PC (see *GitHub* below). |
| Old delivery, catering and messages data removed after a backup | `update.ps1` now takes a backup first. Only then are the old tables (messages, catering bookings, delivery zones) and the old order and customer columns removed. The backup is kept in `backups\`. |

## Phase 0: protection

- **Every update takes a backup first** (`before-update` in `backups\`). If
  the backup fails, the update stops and changes nothing.
- **`restore.ps1` proves the backup**: it restores into a separate test
  database, then compares the row counts of the key tables (orders, payments,
  tills, stock moves, journal, users, products, payslips, audit log) with the
  live one and prints *Verified* or a warning.
- **A baseline test pack**, `tests/test_money_flows.py`, with 18 tests of the
  money flows. It must pass before any later stage is shipped.
- **Git**: `push-to-github.ps1` makes a Git repository in the project folder, saves the code and sends it to GitHub. Every later run saves the changes since the last one, so any update can be rolled back.

## Phase 1: cash and the till

| What | How it works |
|---|---|
| **Blind till count** | While the till is open, the cashier never sees how much cash should be in the drawer: not on the till, not on their home, not through the API. At closing they count and type the cash first. Only then does the system compare. |
| **Variance needs a reason** | If the count is out by more than the limit (K20 to start, set in Settings → Cash controls), the close is refused until the cashier writes what happened. The first count is kept even if they count again. |
| **Manager review** | Tills that were out go to the manager's End of day screen to be reviewed with a note. Nobody can review their own till. Reviewing records a conversation; it does not accuse anyone and deducts nothing from pay. |
| **Cash drops, petty cash, cash added** | The cashier records each one on the till with an amount and a reason. It counts toward expected cash straight away, and a manager confirms or rejects it later. A drop moves cash to the safe (account 1005). Petty cash spent is an expense (6950). A rejected move is reversed in the books. |
| **Mobile money: pending until confirmed** | A mobile money or card payment is *pending* unless the cashier ticks "I have seen the message saying the money arrived". Pending ones are listed on Payments → To match against the statement for a manager or accountant to mark *confirmed* or *failed*. A failed payment stops counting, the order shows as owing again, and the books are corrected. |
| **A reference can't be used twice** | The same transaction reference on a second order is refused, naming the order that already used it. |
| **Discount limits** | Every discount needs a reason. A discount above the limit (10% to start), or any discount by someone without the discount permission, needs a manager's approval at the till. The manager types their own email and password into the approval box. Wrong passwords count toward the lockout. Nobody can approve their own. |
| **Refund requests** | A cashier can now start a refund, and a manager approves it in the same approval box. Managers still refund directly. |
| **Reprints recorded** | A receipt opened again from Orders is marked as a reprint and written to the audit log. |
| **Held orders, changing an unpaid order** | The till lists unpaid orders under *Waiting for payment*. *Take payment* or *Change* reloads the order into the cart, and placing it again updates the same order and number. A paid order can't be changed. |
| **Waiting for you** | Manager, accountant and owner homes show what needs a decision: payments to match, cash moves to confirm, tills to review, tills open more than 16 hours, journals, leave and payroll waiting. |
| **Wait time** | The kitchen wait figure counts only the last 2 hours, so it no longer shows a meaningless "386 min". |

## Owner protection (from Phase 5, done early)

- One owner cannot switch off, demote or remove the other. The last active
  owner can't be switched off at all.
- A password reset, a password change, or switching an account off ends every
  session of that account at once.
- `starter-accounts.ps1` now makes the second owner account
  (`owner2@greenbuffet.zm`) with a temporary password that must be changed at
  first sign-in. No owner password is written in the code.

## Checks

| Suite | Result |
|---|---|
| Money flows (`tests/test_money_flows.py`) | 18 passed |
| Security (`tests/test_security.py`) | 36 passed |
| Role and removed-feature probes | 29 passed |
| Screen sweep: 25 screens × phone and desktop × light and dark | 100 / 100 clean |
| Browser run-through: manager approves a discount at the till, MTN payment pending, cash drop, blind close refused at K225 short, closed with a note, manager reviews | Pass |

All of it was run on a test database here. Your live data was not touched.

## Not done yet (moved to the next stage)

- **Till handover** between two cashiers on one drawer. For now, close one
  till and open another.
- **A daily discount report.** Discounts and who approved them are on each
  order and in the audit log, but not yet in one report.
- **PDF receipt download.** Printing works; saving as PDF is through the
  browser's print dialog.
- **Kitchen tickets** were already sent only at payment, so no setting was
  needed. (The audit said otherwise; that was corrected.)

## GitHub

`.\scripts\push-to-github.ps1` sends the code to your `greenbuffet`
repository on a branch called `system`, so the demo website on `main` is not
touched. It needs Git for Windows; the first push opens a browser to sign in.
It refuses to send `.env` (the database password and secrets), backups or
logs, even if they were somehow added.

`greenbuffet` is a **public** repository: anyone can read the code. No
passwords or business data are in it, but a private repository is better for
a business system. Make one on GitHub, then run
`.\scripts\push-to-github.ps1 -Repo https://github.com/<you>/<new-repo>.git`.

## Installing

1. Extract `green-buffet-stage22.zip` over `D:\The Green Buffet`.
2. `.\scripts\update.ps1`. It backs up, removes the old tables, moves the old
   roles and starts the system.
3. `.\scripts\starter-accounts.ps1` to make the second owner account.
4. Sign in and check the till.
