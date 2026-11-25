# Roadmap

Twelve stages, plus four added afterwards. All are finished. Each has a
report in this folder saying what it does, what it refuses to do, and what was
left out on purpose.

Stages 14 to 16 add the customer-facing management the system was missing: a
customer list with a loyalty stamp card, deliveries and riders, and catering
bookings with deposits. They are staff screens. This is a point of sale and
management system: customers do not order through it.

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
| 12 | Production deployment, documentation, staff training | 1 week | Done |
| 13 | Paying suppliers: payments, what we owe, ageing | 2 days | Done |
| 14 | Customers and loyalty (points, later stamps) | 1 week | Done |
| 15 | Deliveries, areas and riders; catering with deposits | 1 week | Done |
| 16 | The message outbox for customers | 3 days | Done |
| 17 | Matching the demo: its screens, look, logo and stamp card | 1 week | Done |
| 18 | Server status check, kitchen sound and undo, period comparison, light or dark | 2 days | Done |
| 19 | A home screen for each of the seven roles | 2 days | Done |
| 20 | Counter point of sale only, the printed menu, one-tap sign-in | 2 days | Done |
| 21 | Dark mode fixed on every screen, receipt-only printing, My clocking, test sign-in | 1 day | Done |
| 22 | Plan phases 0 and 1: protection, cash and till controls, owner protection | 2 days | Done |
| 23 | Profiles, online status, team directory, devices, two-step sign-in, lock screen | 1 day | Done |
| 24 | IT workspace, security centre, append-only audit, rate limits | 1 day | Done |
| 25 | Email: verified addresses, email codes, reset links, email change; approval thresholds | 2–3 days | Needs an email provider |
| 26 | Lenco payments, webhooks, settlement, background jobs | 3–5 days | Needs Lenco sandbox keys |
| 27 | Installable app (PWA) and offline cash sales | about 1 week | Next |
| 28 | Expenses, waste, expiry, checklists, food safety, equipment, periods, rotas, till handover, discount report | about 1 week | |
| 29 | Vercel + Render production, CI, monitoring, storage, go-live | 3–5 days | Accounts, domain, approval to pay |

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

## Still not built

Two things promised in this plan were not built, and both should be decided on
rather than forgotten:

**The till working offline.** This plan said cash orders would queue locally
through a power or internet cut and sync afterwards. They do not. The till
needs the backend, which on the counter PC means the till stops if that
computer stops — and, if the system is ever moved to a server, if the internet
drops. On the counter PC the risk is small, since the browser and the backend
are the same machine; on a server it is the main argument for keeping the PC as
a fallback.

**Everything the customer sees** stays out of this system on purpose. It is a
point of sale and management system for staff: the till, the kitchen, the
store room, the books, and now customers, deliveries and functions. An order
is taken by a member of staff, never by a customer.

A customer-facing site, if one is ever wanted, is its own separate piece of
work that would read this system's menu. Online payment would need an Airtel
or MTN merchant account, and messages still need a WhatsApp or SMS gateway;
until then the Messages screen shows what to send and opens WhatsApp with it
typed.

**The map** is deliberately absent. Deliveries work by area: a fee, a usual
time and a smallest order per part of Kitwe, all editable. A real map needs a
Google Maps or Mapbox key that bills per load, and inside one town the area
list does the same job for nothing.
