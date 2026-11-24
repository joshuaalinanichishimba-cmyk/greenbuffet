# Test report

## Stage 22, 24 November 2026 (Phases 0 and 1)

Run against a test copy of the database. Your live data was not touched.

| Suite | Result |
|---|---|
| `tests/test_money_flows.py`: cash and change, retried payment charged once, split payment, books balance, mobile money pending then confirmed, a reference refused twice, a failed payment stops counting (books still balance), cashier can't confirm payments, discount needs a reason, big discount needs a manager (wrong password refused), no approving your own, cashier refund needs approval, unpaid order changed but paid one refused, open till blind to the cashier, cash drop needs another person, short till needs a note then a review, password reset ends the session, one owner can't switch off the other | 18 passed |
| `tests/test_security.py` | 36 passed |
| `tests/probe_customer_security.py` (now five roles) | 29 passed |
| Screen sweep: 25 screens × phone and desktop × light and dark | 100 / 100 clean |
| Browser run-through of the till: approval box, pending MTN payment, cash drop, blind close (refused at K225 short, closed with a note), manager's review and confirmation | Pass |
| Update on a copy of the live database: backup taken, old tables removed, roles moved (owner 2, manager 2, accountant 3, cashier 27, kitchen 3) | Pass |

Every failure in the audit checks below is now fixed and covered by a test.


## Baseline, 24 November 2026 (before Phase 0)

Run against a test copy of the database. Your live data was not touched.

| Suite | Result |
|---|---|
| `tests/test_security.py`: sign-in, lockout, permissions, injection, sign-in by kind of account | 36 passed |
| `tests/probe_customer_security.py`: what each role may and may not do, removed features gone | 29 passed |
| Screen sweep: 25 screens × phone and desktop × light and dark | 100 / 100 clean (no errors, no sideways scrolling) |
| Seven roles sign in and land on their own home, on phone and desktop | 14 / 14 |

### Audit checks (real transactions)

| Check | Result |
|---|---|
| A retried cash payment with the same idempotency key is charged once | Pass |
| A split payment (cash + Airtel) settles the order | Pass |
| Two refreshers take 700 ml of base from stock, exactly once | Pass |
| Change on K100 tendered for K50 is K50 | Pass |
| The trial balance balances after the sales | Pass |
| A cashier is refused a refund | Pass (403) |
| A disabled account's open session is refused on its next request | Pass (403) |
| The same mobile money reference is refused a second time | **Fail**: it was accepted. *Fixed in stage 22.* |
| A cashier's 98% discount needs approval | **Fail**: it was accepted. *Fixed in stage 22.* |
| A password reset ends the old session | **Fail**: the old session still worked. *Fixed in stage 22.* |
| One owner cannot switch off the other alone | **Fail**: they can. *Fixed in stage 22.* |
| A backup restores on the restaurant PC | Not run there yet (Phase 0). |
