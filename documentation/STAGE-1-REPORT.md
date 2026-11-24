# Stage 1 report: foundation

**Delivered.** The three layers are connected and access control works.

## What was built

`backend/` is a FastAPI application with SQLAlchemy models, argon2 password
hashing, JWT sessions and permission guards on every protected route.
`frontend/` is a Vue 3 and TypeScript application with a sign-in screen, a
forced password change and a dashboard. `scripts/` holds five PowerShell
commands that set up, run and back up the system on Windows.

Seven tables: `users`, `roles`, `permissions`, `role_permissions`,
`login_attempts`, `audit_log`, `settings`. Seeding creates 35 permissions,
7 roles, 130 role-permission links and one owner account with a random
temporary password.

## Two bugs found by testing, both fixed

**Email validation rejected the owner account.** The default address ended in
`.local`, which the email validator treats as a reserved name, so nobody could
sign in. Sign-in now takes the address as a plain string, since it only looks
it up, and the default address was changed. Validation still applies when an
administrator creates an account.

**A wrong password said "your session has ended".** The API client treated
every 401 as an expired session. Someone who simply mistyped their password
was told something confusing and misleading. The client now only treats a 401
as expiry when it is not the sign-in request.

## Not in this stage

No menu, orders, till, kitchen, stock, accounting or payroll yet: those are
stages 3 to 8. No PDF export, file storage or automated backups: stage 10.
Payments and messaging are still unbuilt; the adapters in the demo's `server/`
folder are the starting point for stage 4.

## Before Stage 2

1. Run `.\scripts\check.ps1` and send me the output.
2. Confirm the hosting budget, roughly 25 to 40 US dollars a month before
   go-live. Free tiers sleep, which is unacceptable for a till.
3. Confirm whether Green Buffet has commissioned the production system or is
   still deciding. It changes whether we build on their real menu and accounts
   or keep using sample data.
4. Choose a payment provider when we reach stage 4. Their merchant account is
   needed before payments can be finished.
