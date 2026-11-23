# Roadmap

Twelve stages. Each ends with a report and waits for approval before the next
begins. Estimates assume part-time work around university.

| Stage | Delivers | Estimate | State |
| --- | --- | --- | --- |
| 0 | Audit of the demo, architecture, database design, this plan | — | Done |
| 1 | Foundation: Vue, FastAPI, PostgreSQL, sign-in, roles, permissions | 1 week | Done |
| 2 | User management screens, password resets, session handling | 1 week | Done |
| 3 | Menu, products, option groups, recipes | 1 week | Done |
| 4 | Point of sale and checkout: real transactions, receipts, shifts | 2 weeks | Done |
| 5 | Kitchen display over WebSockets | 1 week | Done |
| 6 | Inventory, suppliers, purchases, recipe stock deduction | 2 weeks | Done |
| 7 | Accounting: chart of accounts, all books, statements | 2–3 weeks | Done |
| 8 | HR, attendance, payroll, payslips | 2 weeks | Done |
| 9 | Dashboards and reports, with PDF, Excel and CSV export | 1–2 weeks | Done |
| 10 | Settings, document storage, automated backups and restore | 2 weeks | Done |
| 11 | Security review, testing, load testing | 1–2 weeks | Done |
| 12 | Production deployment, documentation, staff training | 1 week | Next |

## What Stage 1 contains

- PostgreSQL schema for access control: users, roles, permissions,
  role_permissions, login_attempts, audit_log, settings.
- Argon2 password hashing and JWT sessions, with an eight-hour expiry.
- 35 permissions across five areas, stored as rows so they can be changed
  without a new deployment.
- Seven starting roles: owner, administrator, manager, accountant, cashier,
  kitchen staff, inventory staff.
- Sign-in, forced first password change, sign-out, session restore on reload.
- Brute-force protection: five failed attempts locks that email for 15 minutes.
- Lockout protections: nobody can disable their own account, demote their own
  role, or strip role management from owner or administrator.
- Append-only audit log recording sign-ins, account changes and role changes
  with the values before and after.
- A dashboard that proves the three layers are connected and shows which
  modules the signed-in role may open.

## Checked before this stage was called done

| Test | Result |
| --- | --- |
| Health endpoint reports the database connected | Pass |
| Correct sign-in returns a token and 35 permissions for the owner | Pass |
| Wrong password is refused with the same message as an unknown email | Pass |
| Six failed attempts trigger the 15-minute lock | Pass |
| Cashier refused from users, roles and audit endpoints (403) | Pass |
| Cashier cannot promote themselves to owner | Pass |
| Owner cannot disable their own account or demote themselves | Pass |
| Owner cannot remove role management from the owner role | Pass |
| A legitimate role edit saves and takes effect | Pass |
| Forced password change on first sign-in | Pass |
| Session survives a page reload, sign-out clears it | Pass |
| Cashier sees 3 of 8 modules, owner sees all | Pass |
| No sideways scrolling on a 390px phone screen | Pass |
| TypeScript compiles with no errors, production build succeeds | Pass |

## Decisions worth recording

**One application, not microservices.** A single FastAPI service keeps one
source of truth for money and is far simpler for one developer to run.

**Permissions in the database, not in code.** The restaurant can change who
may do what without waiting for a deployment.

**Journal entries written once, at the time of the sale.** The browser demo
rebuilds the accounting journal from source records on every read, which is
fine for hundreds of rows and far too slow for years of real data.

**The till must work offline.** Power and internet cuts are routine in Kitwe.
From Stage 4, cash orders queue locally and sync later. A mobile money payment
is never shown as successful until the provider confirms it.
