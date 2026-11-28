# Requirements traceability

**Authoritative input pending.** The user has stated that a complete 114-section specification follows, but the specification text has not been received in the conversation or found in the project. Therefore this file does not invent requirement identifiers, acceptance criteria, or completed statuses. The historical 110-section `MASTER-SPEC-STATUS.md` is not authoritative for new work.

When received, save the complete text verbatim to `MASTER-PRODUCTION-SPECIFICATION.md` and add one row per requirement in the matrix below. Preserve specification section and requirement identifiers exactly. Cite code and test evidence separately: implemented does not mean tested.

| Requirement ID | Specification section | Status | Frontend evidence | API / service evidence | Model / constraint evidence | Test evidence | Verified behavior | Gap / risk | Dependencies | Acceptance criteria |
|---|---|---|---|---|---|---|---|---|---|---|
| Pending specification | Pending | Not assessed | — | — | — | — | — | — | — | — |

## Preliminary source inventory (not a requirements verdict)

This index helps locate implementation during reconciliation. It is not a claim that every behavior satisfies the forthcoming specification.

| Domain | Located implementation | Existing test evidence | Audit note |
|---|---|---|---|
| Authentication and sessions | `backend/app/api/v1/auth.py`; `backend/app/core/security.py`; `backend/app/services/accounts.py`; `backend/app/models/access.py`; frontend session store and API service | `backend/tests/test_security.py`, `test_profiles.py`, `test_email.py` | Argon2, HS256 JWT and server-side session/version checks exist. `JWT_SECRET` has a weak fallback. Test/demo gates need production fail-closed review. |
| Sales and payments | `backend/app/api/v1/sales.py`; `backend/app/services/ordering.py`; `backend/app/models/sales.py` | `backend/tests/test_money_flows.py`, `test_it.py` | Server pricing, cash/split payments, idempotency, manual electronic-payment confirmation and refunds exist. No Lenco webhook integration was located. |
| Accounting | `backend/app/services/posting.py`; `backend/app/api/v1/books.py`; `backend/app/models/books.py` | `test_money_flows.py`, `test_security.py`, `test_it.py` | Journal writer validates debit/credit equality in application logic. Validate database-level guarantees, concurrent posting, reversal rules and report reconciliation against the full specification. |
| Offline cash | `backend/app/api/v1/offline.py`; `frontend/src/services/offline.ts`; service worker/PWA assets | `backend/tests/test_offline.py` | Server reprices and records cash-only offline sales; database unique index supports deduplication. Browser/device and concurrent-sync coverage remains to be verified. |
| Stock, purchases and kitchen | `backend/app/api/v1/stock.py`; `backend/app/api/v1/kitchen.py`; `backend/app/models/stock.py`, `kitchen.py` | Existing coverage is distributed; map after spec | Inspect concurrency, historical records, and accounting integration per requirement. |
| Deployment and operations | `deploy/docker-compose.yml`, `deploy/DEPLOY.md`, `deploy/Caddyfile`, `backend/run_server.py` | Compose could not be run because Docker is unavailable | Local configuration does not establish a Vercel/Render production deployment. No Lenco configuration identified. |
| Schema lifecycle | `backend/app/seed.py`; `backend/app/core/schema_update.py`; `scripts/update.ps1`; `scripts/restore.ps1` | No isolated legacy migration suite found | Seed path invokes destructive retired-schema cleanup. See `DATABASE-MIGRATION-REVIEW.md`. |

