# Master specification: where each section stands

Checked against the code on 25 November 2026, after stage 24. Sections
that were already built were skipped, as asked. "Needs you" means it cannot
be finished without an account, a key, a purchase or a decision from the
owners. Nothing in that column was bought or switched on.

| Status | Meaning |
|---|---|
| **Done** | Built and covered by automated tests |
| **Done, untested live** | Built, tested with stand-ins; needs the real service to prove it |
| **Partly** | Some of it exists; the gap is named |
| **Planned** | Not built yet; the stage it is in |
| **Needs you** | Blocked on an account, key, payment or decision |

## Foundations and rules (1–4)

| § | Subject | Status | Notes |
|---|---|---|---|
| 1–2 | Role, non-negotiable rules | Followed | Inspected before changing; nothing removed without approval; no fake features |
| 3 | Technology stack | **Needs you** | Today: FastAPI + PostgreSQL + Vue, served from one server. Vercel + Render split is prepared in stage 29 and needs your Vercel and Render accounts and a domain |
| 4 | Central architecture | Done | One backend, one PostgreSQL database; the screens never touch the database |

## Hosting, database, migration (5–9)

| § | Subject | Status | Notes |
|---|---|---|---|
| 5 | Vercel front end | Planned (29) | `vercel.json`, API address, preview isolation |
| 6 | Render back end | Partly | Docker image, health endpoint, PORT binding, startup migrations work (the demo runs on Render). `render.yaml`, paid plan: stage 29 |
| 7 | Front/back security, CORS | Partly | Strict CORS list, HTTPS headers. Cross-domain set-up comes with Vercel (29) |
| 8 | PostgreSQL | Done | Keys, foreign keys, unique constraints, indexes, money in whole ngwee, UTC times |
| 9 | Migration, data preservation | Done | Add-only migrations at start-up, backup before every update, verified restore |

## Accounts and security (10–24)

| § | Subject | Status | Notes |
|---|---|---|---|
| 10 | Six account types | **Done (stage 24)** | Owner ×2, Manager, Cashier, Kitchen, Accountant, **IT administrator** (new) |
| 11 | Two-owner control | Done | Equal owners; neither can suspend, demote or archive the other. Dual approval for exceptional actions: planned (25) |
| 12 | Granular permissions | Done | 60+ permissions, checked on the server for every request |
| 13 | Secure authentication | Done | Argon2id, lockout, rate limiting (stage 24), sessions, lock screen. Email verification and recovery by email (stage 25) |
| 14 | Email two-factor codes | Done (25) | Six digits, 5 minutes, once, five tries, resend after 60 s, stored only as a keyed fingerprint. Owners and IT choose email or authenticator app |
| 15 | Transactional email | Done (25), Gmail for now | SMTP. Sends from Joshua's Gmail with an App Password (`email-setup.ps1`). For the restaurant's own domain later: Resend or Brevo SMTP and DNS records |
| 16 | Secure email change | Done (25) | Codes to both old and new; both told; other devices signed out; owners' addresses cannot be changed by anyone else |
| 17 | Recovery | Done | Recovery codes, reset by owner, reset-owner script, email reset links (30 minutes, once, ends every session) |
| 18–19 | Attack protection | **Partly (stage 24)** | Parameterised queries (ORM), validation, CSP, HSTS, frame, referrer, rate limits. Threat model and outside test: 29 |
| 20 | Security centre | **Done (stage 24)** | IT workspace → Security: failed and locked sign-ins, refusals, rate limits, with review notes |
| 21 | Sessions and devices | Done | Per-device sessions, revoke one or all, inactivity lock |
| 22 | Infrastructure secrets | Partly | Secrets only in `.env`, never in Git, push script refuses them. Branch protection, scanning: 29 |
| 23 | Profiles and presence | Done | Stage 23 |
| 24 | Audit log | **Done (stage 24)** | Now append-only inside PostgreSQL: no one can edit or delete an entry |

## Progressive Web App and offline (25–29, 82–85)

| § | Subject | Status | Notes |
|---|---|---|---|
| 25–28 | Installable app, caching, updates | Done (27) | Manifest, icons, service worker keeps every screen; the page is always checked first, so updates show on the next open with the connection up; the API is never cached |
| 29 | Push notifications | Moved to 29 | Needs https and a push service. In-system and email notices work |
| 82–84 | Offline cash sales | Done (27) | IndexedDB queue, saved before the receipt; one id one sale (unique index); server re-prices and dates to the sale; price gaps and late arrivals told to owners; works for whoever was signed in, signing in fresh needs the server |
| 85 | Kitchen during outages | Done (27) | Printed receipt is the ticket; recent offline sales reach the board on sending, older ones are recorded as served |

## Selling and payments (30–37)

| § | Subject | Status | Notes |
|---|---|---|---|
| 30 | POS | Done | Server-side totals, idempotent orders and payments, reversals not deletes |
| 31–34 | Lenco gateway | Planned (26) / **Needs you** | API read from Lenco's documentation: mobile money collection, status by reference, HMAC-SHA512 webhook. Live use needs the merchant account and keys |
| 35 | Reconciliation and settlement | Partly | Manual matching (stage 22). Lenco settlement and fees: 26 |
| 36 | Cash and split payments | Done | |
| 37 | Refunds | Done | Manual refunds with manager approval. Lenco refunds: 26, if Lenco supports them |

## Kitchen, menu, stock (38–46)

| § | Subject | Status | Notes |
|---|---|---|---|
| 38 | Kitchen display | Done | Live board, stations, timings. Delayed-order alert: 28 |
| 39 | Menu and price history | Done | Price changes kept with who and when; past sales keep their prices |
| 40 | Ingredient inventory | Partly | Stock, counts, reorder levels, valuation. Expiry dates and unit conversions: 28 |
| 41 | Recipes and costing | Done | Recipes, cost, margin |
| 42 | Consumption | Done | Deducted at payment, once |
| 43 | Waste | Partly | Waste is a stock movement with cost. Reasons, approval, reports: 28 |
| 44 | Suppliers and purchasing | Partly | Suppliers, purchases, receiving, paying, owed. Invoice attachments, returns, duplicate-invoice check: 28 |
| 45 | Cashier shifts | Done | Blind count, variance notes, review |
| 46 | Opening and closing checklists | Planned (28) | |

## Money, people, tax (47–52)

| § | Subject | Status | Notes |
|---|---|---|---|
| 47 | Accounting | Partly | Double entry, statements, reversals. Accounting periods and closing, bank reconciliation: 28 |
| 48 | Expenses | Partly | Through journal entries. A proper expense form with receipts and approval: 28 |
| 49 | HR and attendance | Partly | Staff list, clocking, leave. Rotas, lateness, overtime, corrections: 28 |
| 50 | Payroll | Partly | PAYE, NAPSA, NHIMA with editable rates. Effective dates, bonuses, advances: 28. **Rates must be checked with ZRA, NAPSA and NHIMA before the first real payroll** |
| 51 | ZRA Smart Invoice | **Needs you** | Needs your ZRA registration details and the VSDC documentation. Payment and fiscal status will be kept separate |
| 52 | Receipts | Done | Reprints marked and audited. PDF download: 28 |

## Oversight and reporting (53–56)

| § | Subject | Status | Notes |
|---|---|---|---|
| 53 | Owner dashboard | Done | Plus Team status (23). Security and system health summary: 25 |
| 54 | Reports | Done | Sales by item, category, cashier, method, hour; exports |
| 55 | Loss detection | Partly | Till variances, approvals, refused access, failed sign-ins. Configurable alerts: 28 |
| 56 | Approval centre | Partly | "Waiting for you" collects them. Thresholds and dual approval: 25 |

## IT administration (57–80)

| § | Subject | Status | Notes |
|---|---|---|---|
| 57–58 | IT workspace | **Done (stage 24)** | One workspace with sections, separate from the business screens |
| 59 | System overview | **Done (stage 24)** | Real checks only; unknown and not configured are said plainly |
| 60 | Infrastructure (Vercel, Render, GitHub APIs) | **Needs you** | Needs restricted API keys from each provider; shown as not available until then |
| 61 | Diagnostics | **Done (stage 24)** | Health, structure, configuration and every integrity check |
| 62–63 | Remote repairs, safe framework | **Done (stage 24)** | Fixed list with risk, preview, reason, one-at-a-time, verification and audit; no commands or SQL from the screen |
| 64 | Self-healing | Partly | Database reconnects; failed requests are logged. Job retries come with background jobs (26) |
| 65 | Database integrity | **Done (stage 24)** | Nine checks, four with repairs |
| 66 | Lenco technical | Planned (26) | |
| 67 | Email technical | Done (25) | Email log without bodies, codes or links; IT status and test; failures with reasons |
| 68–70 | PWA, devices, sync centre | Done (27) | Waiting and refused offline sales shown on the till and in the top bar; devices and sessions listed per person |
| 71 | Deployments | **Needs you** | Needs provider API keys |
| 72–73 | Configuration, feature flags, emergency | **Done (stage 24)** | Cash-only, stop orders, read-only; password and reason; owners told |
| 74 | Error log | **Done (stage 24)** | Grouped, counted, cleaned of secrets, with reference numbers. Sentry: optional, needs an account |
| 75 | Incidents | **Done (stage 24)** | |
| 76 | Support tickets | **Done (stage 24)** | Everyone can report; replies show on the reporter's profile |
| 77 | IT permissions | **Done (stage 24)** | No money, pay, prices, refunds or staff records |
| 78 | Technical audit | **Done (stage 24)** | |
| 79 | Emergency administration | Partly | `documentation/EMERGENCY-RECOVERY.md`; provider consoles once accounts exist |
| 80 | AI troubleshooting | Deferred | As the brief says: after monitoring is reliable |

## Platform (81, 86–110)

| § | Subject | Status | Notes |
|---|---|---|---|
| 81 | Real-time | Partly | WebSocket for the kitchen. Wider events: 27 |
| 86 | Transaction integrity | Done | One transaction per sale; idempotency keys; stage 24 fixed failed mobile money after hand-over |
| 87 | Background jobs | Planned (26) | Needed for Lenco re-checks |
| 88 | File storage | **Needs you** | Local disk today. Cloud needs S3-compatible storage (Cloudflare R2 has a free tier) |
| 89 | Backups and recovery | Partly | Backup before updates, restore test. Off-site copies: needs storage |
| 90 | Independent monitoring | **Needs you** | A free uptime monitor (UptimeRobot, Better Stack) pointed at `/api/v1/health` |
| 91 | Notifications | Partly | In-system and email (25). Push: 27 |
| 92 | Food safety, equipment | Planned (28) | |
| 93 | Hardware conditions | Partly | Works on low-end PCs and phones; printer tested in the browser |
| 94–95 | UI, performance | Ongoing | Every screen checked at phone and desktop width, light and dark |
| 96 | Data protection | Partly | Least access, pay hidden, no surveillance. Retention policy: 29 |
| 97–98 | Environments, secrets | Partly | Development, demo and production kept apart. Staging: 29 |
| 99 | CI/CD | Planned (29) | GitHub Actions |
| 100–101 | Costs, ownership | Planned (29) | `HOSTING-COSTS.md` |
| 102 | Remove or defer | Done earlier | Delivery, online ordering, catering and messages removed in stage 22 with your approval |
| 103–110 | Mandatory testing, go-live | Ongoing | Each stage adds tests; go-live checklist in stage 29 |

## Order of the remaining stages

| Stage | Content | Needs from you |
|---|---|---|
| 25 | Email | Built. Switched on last, before go-live: a Google App Password typed into `email-setup.ps1` |
| 26 | Lenco: payments, webhooks, re-checks, settlement and fees, background jobs | Lenco merchant account and **sandbox** keys |
| 27 | Installable app and offline cash sales | Done |
| 28 | Expenses, waste, expiry, checklists, food safety, equipment, accounting periods, rotas, payroll extras, approval thresholds, dual approval, owner security summary | Nothing |
| 29 | Vercel + Render production, CI, monitoring, storage, recovery, go-live checklist, costs | Accounts, domain, approval to pay |
