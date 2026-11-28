# Production readiness checklist

This is an evidence checklist, not a declaration that the system is ready. Mark an item complete only with a linked test/report and environment evidence. No production access or deployment was performed for this checklist.

## Requirements and scope

- [ ] Preserve full authoritative 114-section text in `MASTER-PRODUCTION-SPECIFICATION.md`.
- [ ] Trace every requirement to source, tests, dependencies and measurable acceptance criteria.
- [ ] Review owner-approved scope and data retention for historical delivery/catering/customer records.

## Data safety and recovery

- [ ] Remove destructive cleanup from routine initialization through a reviewed versioned migration plan.
- [ ] Inventory schema and representative historical records; compare legacy and target structures.
- [ ] Create independent encrypted backups with checksums and retention policy.
- [ ] Restore into an isolated database and verify rows, relationships, balances, sequences and app reads.
- [ ] Exercise migration, failure recovery, and reconciliation without touching valued records.

## Authentication and cybersecurity

- [ ] Fail startup closed for missing/default/weak JWT signing secrets and unsafe environment combinations.
- [ ] Prove demo/test sign-in and 2FA bypass cannot activate in staging or production.
- [ ] Verify password, email verification/change, recovery, two-step, session revocation, owner rules and IT permissions against specification.
- [ ] Review browser token storage/XSS exposure, CORS, rate limits, uploads, logs, CSP and security headers.
- [ ] Confirm secrets use deployment secret stores and are absent from images, logs, source and client bundles.

## Financial integrity and operations

- [ ] Prove server-authoritative prices, cash/split flows, refunds, duplicate prevention, journal balance, shifts, stock deduction, offline sync and report reconciliation.
- [ ] Test concurrent sale/payment/offline retries and database uniqueness under contention.
- [ ] Verify Lenco sandbox callbacks, signatures, replay prevention, amount/currency/order matching and settlement reconciliation before any live keys.
- [ ] Verify accounting, ZRA Smart Invoice, payroll and statutory calculations against the specification and current authoritative rules.
- [ ] Complete role workflows for owner, manager, cashier, kitchen, accountant and IT; hardware-dependent items require physical-device evidence.

## Infrastructure and release

- [ ] Validate selected Vercel/Render/PostgreSQL configuration, TLS, CORS, health/readiness checks and storage lifecycle.
- [ ] Verify object-storage access controls and backup inclusion.
- [ ] Establish monitoring, alert routing, log retention, incident response and service ownership.
- [ ] Complete staging deploy, migration, restore and acceptance run using nonproduction secrets/data.
- [ ] Approve a rollback/recovery plan and production checklist before any go-live action.
