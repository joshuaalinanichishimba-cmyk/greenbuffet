# Codebase guide

## System shape

- `frontend/` is the browser application. `frontend/src/services/api.ts` centralizes HTTP requests and authentication headers; page/components live under `frontend/src/`. The service worker and web manifest provide the PWA shell; API responses are not intended to be cached offline.
- `backend/app/main.py` builds the FastAPI application and mounts routers. `backend/app/api/` contains route handlers; `backend/app/models/` contains SQLAlchemy table definitions; `backend/app/schemas/` defines request/response validation; `backend/app/services/` holds business operations such as posting.
- `backend/app/core/config.py` loads settings; `database.py` creates the SQLAlchemy engine/session; `security.py` holds password/token primitives; `permissions.py` defines role permissions. Authentication/session enforcement is shared across the API rather than implemented independently in each screen.
- `scripts/` contains Windows operational scripts for update, backup/restore, startup, and account setup. Treat scripts that connect to databases as privileged operational code and inspect their targets before execution.
- `documentation/` contains historical stage reports and current planning/audit material. Stage reports describe intent and past claims; implementation status must be verified in code and tests.

## Request and data path

1. A frontend screen calls the API helper in `frontend/src/services/api.ts`.
2. FastAPI routes validate payloads using Pydantic schemas and call model/service logic.
3. SQLAlchemy sessions persist records in PostgreSQL. Money posting should preserve balanced ledger entries and use database uniqueness/transactions for retries.
4. Shared authentication validates a signed token, active session/version, account state, and role permission before protected work.

## Important areas to inspect by feature

- Schema and initialization: `backend/app/models/`, `backend/app/seed.py`, `backend/app/core/schema_update.py`, `scripts/update.ps1`.
- Auth and access: `backend/app/core/security.py`, `backend/app/core/config.py`, auth-related API routes and `backend/tests/test_security.py`, `test_email.py`, `test_it.py`.
- Money: order/payment/shift/accounting models, corresponding routers/services, `backend/tests/test_money_flows.py`.
- Offline cash synchronization: offline API and frontend service-worker/offline queue code; test idempotency and ownership rules before changing it.
- Integrations/deployment: `docker-compose.yml`/deployment files, `.env.example`, frontend production environment, email and payment integration modules. Local configuration currently does not establish a Vercel/Render/Lenco production deployment.

## Safe local verification

Run pytest only with the guard variables and disposable loopback resources described in `backend/tests/safety.py`; pytest now refuses unsafe execution. Do not copy production credentials into test settings. Frontend build is `npm run build` from `frontend/`. Do not run seed/update/restore scripts against a business database during ordinary development.

