# Post-audit development state

**Checkpoint:** Stage 27, branch `system`, commit `e0b65c1`, matching `origin/system` at the latest check. This observed Git state supersedes older commit references. The five authorized local Windows health-check URL changes and uncommitted test-harness improvements are preserved. No business application logic, production data, live payments, GitHub or deployment target was modified by this audit.

## Verified checkpoint

- Backend integration suite: **115 passed, 1 warning**, against a disposable local PostgreSQL database with synthetic records and a loopback-only test API. Email was captured to files; payment-provider environment variables were absent. One warning was pytest cache write access, not a test failure.
- Frontend production build: passed.
- Python compile check: passed.
- Browser smoke: sign-in screen loaded without JavaScript errors. A completed authenticated browser flow was not verified in the available run.
- Docker is not installed, so the existing Compose stack could not be exercised. A separate disposable local PostgreSQL cluster was used instead. No production/development business database was targeted.
- The initial test collection hang was caused by `backend/tests/load_test.py` matching pytest's broad `*_test.py` pattern and running a login/sale loop at import time. `backend/pytest.ini` now scopes discovery to `tests/test_*.py`; `backend/tests/safety.py` and `conftest.py` enforce a synthetic test DB, isolated loopback API, file email sink and absent payment credentials. Test clients/probes were adjusted to use the guarded test base URL. These are uncommitted audit-created test-infrastructure changes, not application feature changes.
- The one pytest warning was the pytest cache provider being unable to write `backend/.pytest_cache` in this environment. It did not affect test outcomes. A no-cache-provider rerun has not yet verified that the warning disappears.

## Known production blockers and risks

1. **Critical — data loss migration path:** `seed.py` invokes `drop_retired()` each time; it deletes retired order/customer fields and whole historical tables using `CASCADE`. Exact list and safer migration recommendation: [DATABASE-MIGRATION-REVIEW.md](DATABASE-MIGRATION-REVIEW.md).
2. **Critical — production JWT configuration:** configuration accepts the weak `change-me-in-env` fallback. Production startup must fail closed on default, weak, or missing signing secrets, and must validate all mandatory production settings. Do not treat a status page warning as a control.
3. **High — test-mode controls:** test sign-in and 2FA bypass controls depend on exact environment checks. Harden production/staging to fail closed and verify with tests proving that test-fill cannot be enabled there.
4. **High — no versioned migration history:** Alembic package exists but revisions are empty; current hand-written schema update can miss constraints and suppress index errors.
5. **High — backup confidence:** local backup/restore scripts exist, but restore validation is limited and independent/off-host backup plus recovery evidence is not established.
6. **High — payment/settlement:** no Lenco integration or verified webhook/reconciliation flow was found in this branch. Never enable live payments before callback authenticity, idempotency, amount/currency/order matching, settlement reconciliation and test-mode isolation are verified.
7. **Medium — browser regression coverage:** backend integration coverage is substantial; authenticated end-to-end browser coverage remains unverified.
8. **Requirements map pending:** the 114-section authoritative specification has not yet been supplied. The 110-section `MASTER-SPEC-STATUS.md` remains historical and cannot be treated as the current requirements baseline.

## Next work, in dependency order

1. Receive and preserve the full 114-section specification; reconcile it requirement-by-requirement with source and tests.
2. Keep retired data intact; design and review schema baseline plus versioned migration workflow; restore-test verified backups in isolation.
3. Make test setup reproducible (prefer existing Compose when available) and close remaining safe browser E2E coverage.
4. Fix production secret validation and test-mode fail-closed behavior; verify auth/session/email/owner/IT controls with explicit negative tests.
5. Verify existing sales, till, stock, purchasing, accounting and payroll invariants against source and test evidence.
6. Design Lenco sandbox integration and webhook/idempotency/reconciliation tests; only after specification and financial controls are assessed.
7. Implement remaining operational/accounting features from the specification, including ZRA Smart Invoice and payroll compliance where required.
8. Prepare deployment-specific Vercel/Render/PostgreSQL/object-storage configuration, independent backup and monitoring plans.
9. Run staging migration, restore and acceptance exercises; production readiness review and approval precede any production action.

## Audit-created worktree changes

Integration test discovery/target safety adjustments and audit documentation are uncommitted. Review `git diff` before deciding whether to keep them. They do not include application feature code and were created to enable safe test collection/execution. The complete authoritative specification was not present in the latest user message or local files; its 114-requirement reconciliation remains pending. No substantial application changes should begin until that reconciliation and critical-risk plan are presented.

