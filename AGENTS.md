# Green Buffet development instructions

- Continue from the current `system` branch and verify actual Git state before work. Preserve history and all existing uncommitted work. Do not merge unrelated `main`, `pos`, or `client-demo` histories.
- Read `documentation/POST-AUDIT-DEVELOPMENT-STATE.md`, `documentation/REQUIREMENTS-TRACEABILITY.md`, `documentation/DATABASE-MIGRATION-REVIEW.md`, `documentation/CODEBASE-GUIDE.md`, and `documentation/DEVELOPER-LEARNING-GUIDE.md` before substantial changes. The forthcoming 114-section master specification is authoritative once received and must be preserved verbatim.
- Never infer completion from stage reports. Verify actual frontend, API, service, model/constraint, and test behavior; record implementation and test coverage separately.
- Do not run database seed/update/reset/restore commands against a valued database. `backend/app/seed.py` currently calls `drop_retired()`; inspect the target and migration plan first. Never perform destructive schema changes without explicit approval and verified isolated restoration.
- Run integration tests only against a disposable loopback PostgreSQL database whose name begins `greenbuffet_test_`, with `ENVIRONMENT=test`, `GB_TEST_MODE=1`, test API at `http://127.0.0.1:18000/api/v1`, file email sink, and no provider credentials. The pytest safety guard is in `backend/tests/safety.py`. Never weaken it to target another database or host.
- Keep electronic payment integrations in test/sandbox mode until explicitly authorized. Do not expose secrets in output, logs, docs, commits, or screenshots.
- Preserve existing branding and working Stage 1–27 functionality. Do not push, deploy, purchase services, or access production systems without explicit authorization.
- Before substantial application changes, present the requirements assessment, risks, dependencies, and acceptance criteria. Update the traceability matrix, tests, state, roadmap, and learning material as work is verified.
- Explain significant findings in clear language first, then technical detail with Green Buffet file and function references.

## Continuation documents

- `documentation/MASTER-PRODUCTION-SPECIFICATION.md` — authoritative specification, to create only from the complete user-supplied text.
- `documentation/REQUIREMENTS-TRACEABILITY.md` — per-requirement source and test mapping.
- `documentation/POST-AUDIT-DEVELOPMENT-STATE.md` — checkpoint, verification and next work.
- `documentation/DATABASE-MIGRATION-REVIEW.md` — destructive schema inventory and safe migration approach.
- `documentation/TEST_REPORT.md` — verified test outcomes and limitations.
- `documentation/DEVELOPMENT_PLAN.md`, `ROADMAP.md` — historical plans to reconcile against actual requirements.
- `documentation/CODEBASE-GUIDE.md`, `DEVELOPER-LEARNING-GUIDE.md` — architecture and learning references.
