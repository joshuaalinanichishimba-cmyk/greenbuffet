# Developer learning guide

## Concepts to keep in mind

- **Routes, services, models:** a route is the HTTP entry point, a service contains reusable business rules, and a model maps Python objects to database tables. Keep validation at the request boundary and financial invariants in trusted backend logic.
- **Transactions and idempotency:** a sale and its payment, stock effects, and ledger entries must succeed together or be recoverable together. A retry must not post the same sale twice; unique IDs and database constraints are stronger than a frontend button lock.
- **Authentication and authorization:** authentication proves which account is calling; authorization checks what that account may do. A hidden button is not permission enforcement. Every protected API action must enforce role/owner rules on the server.
- **Schema migration:** `create_all()` creates missing tables but does not evolve existing tables. The custom helper adds columns; the seed path also calls a destructive cleanup. Read [DATABASE-MIGRATION-REVIEW.md](DATABASE-MIGRATION-REVIEW.md) before any database update work.
- **Offline operation:** the browser can queue eligible cash actions, but the backend must re-check identity, ownership, prices, and duplicate IDs when synchronization resumes. Offline mode cannot safely assume a payment provider has confirmed funds.
- **Test isolation:** integration tests are programs that can write data and send messages. The test guard proves the target is a loopback synthetic database and API, and redirects email to files. Never weaken that guard to make a test convenient.

## How to investigate a change

1. Find the route, schema, model, service, and frontend caller for the feature.
2. Trace which account/permission protects the route and what transaction boundaries exist.
3. Find tests that exercise success, denial, duplicate/retry, and failure recovery.
4. Identify database changes and backup/restore consequences before editing.
5. Write acceptance criteria in restaurant terms and enforce them in backend tests.
6. Use isolated data, run the targeted tests, then the full safe suite and build. Record the actual result and environment.

## Current learning priorities

Start with PostgreSQL transactions and schema evolution, then FastAPI dependencies and role checks, then the sale/payment/ledger flow, then frontend API/offline synchronization. The current critical example is `backend/app/seed.py` calling `drop_retired()` from `backend/app/core/schema_update.py`: a routine seed/update path can remove historical business fields. Understand that path before running any database initialization command.

