# Technical handover

For whoever maintains this, including future you.

## What it is

A restaurant management system for The Green Buffet, Liberty Mall, Kitwe:
ordering and payment, a kitchen display, stock, double-entry books, payroll,
reporting. Built in twelve stages; each has its own report in this folder
describing what it does, what it refuses to do, and what was deliberately left
out.

## The shape of it

```
Browser (Vue 3 + TypeScript)
        │  JSON over HTTP, bearer token
FastAPI (Python 3.12)
        │  SQLAlchemy 2
PostgreSQL 18
```

In development the front end runs on its own at port 5173 and talks to the
backend at 8000. In service the front end is built once and served by the
backend itself, so there is one address, one process, and no CORS.

| Part | Where |
| --- | --- |
| API | `backend/app/api/v1/` — one module per area |
| Tables | `backend/app/models/` |
| Request and response shapes | `backend/app/schemas/` |
| Posting to the books, numbering, exports, audit | `backend/app/services/` |
| Settings, permissions, security, database | `backend/app/core/` |
| Screens | `frontend/src/views/` |
| Shared screen pieces | `frontend/src/components/` |
| The one place that talks to the API | `frontend/src/services/api.ts` |

## The rules the code holds to

These are not style preferences. Each one prevents a class of bug that costs
money.

1. **Permissions are checked on the server, on every request**, from the
   database rather than from the token. Hiding a button is never the only
   protection, and changing a role takes effect immediately.
2. **Money is whole ngwee.** K95.00 is 9500. Kwacha as a decimal drifts once
   discounts, VAT and change are involved. Two functions convert for display;
   nothing else touches it.
3. **Prices are copied onto the line when sold.** A price change tomorrow must
   never alter what a receipt from today says. The same applies to payslips.
4. **Financial rows are never edited.** A mistake is reversed by a second entry
   and both stay visible.
5. **Writes carry an idempotency key**, so a retry cannot charge twice.
6. **Nothing sold is deleted.** Items are retired, staff disabled.
7. **Document numbers come from the `counters` table**, never from counting
   rows. See the stage 11 report for what happens otherwise.
8. **The books never stop the till.** If an entry cannot be written the sale
   still stands and the gap shows in the trial balance.

## What posts to the books automatically

| Event | Entry |
| --- | --- |
| An order is paid | Money in per payment method; sales and VAT out |
| That order's food | Cost of food sold up, stock on hand down |
| A refund | Sales and VAT reduced, money out |
| A delivery checked in | Stock up, owed to supplier up |
| Stock wasted | Waste up, stock down |
| A till counted | The over or short |
| Payroll approved | Wages and employer costs up; net pay, PAYE, NAPSA, NHIMA owed |
| Payroll paid | Net pay out of the bank |

Everything else is written by hand in the Journal and approved by someone else.

## Running it

| | |
| --- | --- |
| Development, two windows, reloads on change | `.\scripts\run.ps1` |
| Service: built, one address, on the network | `.\scripts\serve.ps1` |
| Starts with Windows, firewall opened | `.\scripts\install-service.ps1` once, as Administrator |
| New stage installed | Extract the zip, then `.\scripts\update.ps1` |
| Tests | `cd backend` then `.\.venv\Scripts\python.exe -m pytest tests -q` |
| Backup now | `.\scripts\backup.ps1` |
| Backup nightly | `.\scripts\schedule-backup.ps1` once, as Administrator |
| Prove a backup restores | `.\scripts\restore.ps1` |

## Settings that matter

`backend\.env`, never committed:

| | |
| --- | --- |
| `DATABASE_URL` | `postgresql+psycopg://user:password@host:5432/database` |
| `JWT_SECRET` | Long and random. Changing it signs everyone out |
| `JWT_EXPIRE_MINUTES` | 480 — one shift |
| `ENVIRONMENT` | `development` or `production`. Production hides `/docs` and sends HSTS |
| `CORS_ORIGINS` | Only needed when the front end is served separately |

Payroll rates and the business details are rows in the database, edited in the
app, not in code.

## When something is wrong

**The backend will not start.** Run it in the foreground —
`cd backend; .\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000` —
and read the error. Usually PostgreSQL is not running, the port is held by an
older copy, or `.env` is missing.

**A statement does not balance.** Books → Trial balance names the difference.
Journal → filter by source to find entries from one place. Nothing is ever
edited to fix it; write a correcting entry.

**Stock is negative.** Either nothing was counted in, a delivery was not
checked in, or a recipe is wrong. A count corrects it and records the
difference.

**Someone cannot sign in.** Five failures locks an account for fifteen minutes.
Sign-ins → Reset password clears the lockout and issues a new password. If
nobody can get in at all:
`cd backend; .\.venv\Scripts\python.exe reset_owner_password.py`.

**After any change, run the tests.** They take about a second and cover the
things that cost money.

## Moving it to a server

`deploy/` holds a Dockerfile, a compose file with PostgreSQL and Caddy for
HTTPS, and `DEPLOY.md` with the steps. The application code needs no changes.

## Known limits

- **One PostgreSQL, one application process.** Right for one restaurant; a
  second branch needs thought about how the two share data.
- **Mobile money and card are recorded, not collected.** The money is taken on
  the operator's device and the reference is stored. Live collection needs a
  merchant account.
- **No rate limit beyond the sign-in lockout.** Fine on a shop counter, needed
  on the open internet.
- **Payroll rates must be confirmed** with ZRA, NAPSA and NHIMA. The system
  flags them until someone does.
