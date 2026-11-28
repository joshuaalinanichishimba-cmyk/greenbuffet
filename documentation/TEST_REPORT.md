# Test report

## Current isolated regression checkpoint (28 November 2026)

| Check | Result |
|---|---|
| Backend integration suite | **115 passed, 1 warning** on an isolated local PostgreSQL test database and loopback test API |
| Frontend production build | Passed |
| Python compilation | Passed |
| Browser smoke | Sign-in screen loaded without JavaScript errors; authenticated workflow not verified |
| Docker Compose | Not run: Docker is unavailable on this workstation |

The suite did not use business records. The PostgreSQL cluster and API were local, the database name was `greenbuffet_test_…`, the database role was a separate `gb_app_…` role, email was captured to files, and payment-provider credentials were not set. The test guard is `backend/tests/safety.py`; pytest discovery is restricted by `backend/pytest.ini` to `tests/test_*.py`, so the standalone `load_test.py` is not imported as a test.

For the currently retained disposable sandbox (when its `%TEMP%\greenbuffet-isolated-1fb6813a` directory still exists), start PostgreSQL in one PowerShell window:

```powershell
& "$env:ProgramFiles\PostgreSQL\18\bin\pg_ctl.exe" -D "$env:TEMP\greenbuffet-isolated-1fb6813a\pgdata" -l "$env:TEMP\greenbuffet-isolated-1fb6813a\postgres.log" start
```

From `backend/`, start the API in a second window after loading its private settings from the temp file (the loop prints no values):

```powershell
Get-Content "$env:TEMP\greenbuffet-isolated-1fb6813a\.env.test" | ForEach-Object {
  if ($_ -match '^([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}
$env:GB_TEST_MODE = '1'
$env:GB_BASE = 'http://127.0.0.1:18000/api/v1'
$env:LOGIN_RATE_PER_MINUTE = '200'
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 18000
```

With the API running, open a third PowerShell window in `backend/`, load the same private test settings without printing their values, then run:

```powershell
Get-Content "$env:TEMP\greenbuffet-isolated-1fb6813a\.env.test" | ForEach-Object {
  if ($_ -match '^([^#=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
}
$env:GB_TEST_MODE = '1'
$env:ENVIRONMENT = 'test'
$env:GB_BASE = 'http://127.0.0.1:18000/api/v1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
..\.venv\Scripts\python.exe -m pytest -q
```

The run's single pytest warning was the cache provider's inability to write `.pytest_cache` in this environment; it did not fail tests. A later Uvicorn log also contains a Starlette deprecation warning for `HTTP_422_UNPROCESSABLE_ENTITY`; that is a separate server warning and was not established as the one pytest summary warning. Re-run with `-p no:cacheprovider` to check whether the pytest warning is eliminated; that variation has not yet been run. Never point the API or test variables at a production or ordinary development database.

These 115 integration tests are the current regression baseline. The baseline does not prove browser workflows, actual installed-PWA behavior, concurrent stress, migration safety, restore readiness, hardware behavior, or production configuration.

## Stage 27, 25 November 2026 (installable app and offline cash sales)

| Suite | Result |
|---|---|
| `tests/test_offline.py` (see `STAGE-27-REPORT.md`) | 12 passed |
| `test_money_flows`, `test_security`, `test_profiles`, `test_it`, `test_email` | 103 passed |
| `tests/probe_customer_security.py` | 29 passed |
| Browser, server switched off and on: offline reload, sale, sending once, till back to normal | 11 / 11 |
| Screen sweep: 57 screens × phone and desktop × light and dark | 228 / 228 clean |

## Stage 25, 25 November 2026 (email)

Run against a test copy of the database with email written to files instead of sent. Your live data was not touched.

| Suite | Result |
|---|---|
| `tests/test_email.py` (see `STAGE-25-REPORT.md` for the list) | 17 passed |
| `tests/test_money_flows.py`, `tests/test_security.py`, `tests/test_profiles.py`, `tests/test_it.py` | 86 passed |
| `tests/probe_customer_security.py` | 29 passed |
| Browser: forgotten password and reset link, emailed code sign-in | Pass |
| Screen sweep: 57 screens × phone and desktop × light and dark | 228 / 228 clean |

## Stage 23, 24 November 2026 (profiles, presence, security)

Run against a test copy of the database. Your live data was not touched.

| Suite | Result |
|---|---|
| `tests/test_profiles.py`: both owners have their own profiles and cannot suspend or archive each other; each cashier and cook has a profile; presence follows the heartbeat (online, away, connection lost and back, offline, unknown, closed, signed out); on duty comes from clocking not presence; nobody changes their own role or pay; suspend cuts access and restore gives it back; archived people leave the directory; one device signed out alone; a manager cannot see sign-in history; profile changes audited without passwords; cashiers cannot read each other's details; locked screen refused (423) until the same person unlocks; switching person ends the session; two-step sign-in with codes and single-use recovery codes; owners must set up two-step; owners told about new accounts and lockouts, never about online/offline; Team status figures match the database | 16 passed |
| `tests/test_money_flows.py`, `tests/test_security.py` | 54 passed |
| `tests/probe_customer_security.py` | 29 passed |
| Browser run-through of the new screens | 21 / 21 |
| Screen sweep: 45 screens × phone and desktop × light and dark | 180 / 180 clean |


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
