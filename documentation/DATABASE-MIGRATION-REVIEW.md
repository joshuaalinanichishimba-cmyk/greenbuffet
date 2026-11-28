# Database migration safety review

**Status:** critical blocker; review only. No destructive schema operation was executed against existing business data.

## Current behavior

`backend/app/seed.py` runs `Base.metadata.create_all(engine)`, `add_missing_columns`, audit-log protection, unique-index creation, and then calls `drop_retired(engine)` on every seed run. `scripts/update.ps1` makes a PostgreSQL dump before running the seed unless `-SkipBackup` is supplied. The API server's initialization also uses the additive schema helper; the retired-object deletion is in the seed/update path.

`backend/app/core/schema_update.py` has two distinct behaviors. `add_missing_columns()` adds model columns but does not change existing column types, constraints, or defaults. It may leave a non-null model column nullable where there is no scalar Python default, and it suppresses index creation errors. `drop_retired()` runs SQL `DROP ... CASCADE` and deletes retired permission rows.

## Exact data at risk from `drop_retired()`

- Entire `messages` and `catering_bookings` tables.
- Entire `delivery_zones` table.
- `orders`: `channel`, `fulfilment`, `track_status`, `public_token`, `requested_for`, `accepted_at`, `accepted_by`, `reject_reason`, `zone_id`, `zone_name`, `address`, `directions`, `delivery_fee_ngwee`, `rider_name`, `rider_phone`, `dispatched_at`, `delivered_at`, `points_earned`, `points_spent`.
- `customers`: `points`, `is_blocked`, `block_reason`.
- Permission records `dispatch.manage` and `catering.manage` in `role_permissions` and `permissions`.

`CASCADE` can also remove database objects that depend on a dropped table or column, such as foreign-key constraints and indexes. Existing `points_entries` is not explicitly dropped, but historical point balances and order references listed above can be lost. Catering records may include booking and deposit history; delivery columns may be part of historical order and customer-service records. The prior comments cite Stage 20 retirement and owner approval on 24 Nov 2026, and describe a backup-first one-time cleanup. That historical rationale does not establish that these records are disposable under current preservation requirements.

## Backup and recovery evidence

`scripts/update.ps1` uses `pg_dump`; it offers `-SkipBackup`, which bypasses the safeguard. `scripts/restore.ps1` restores to a named restore-test database and compares row counts, but this review did not run it against a real database. A count-only check does not validate schema, exact row contents, financial totals, sequence values, constraints, or application usability. No independent/off-host backup configuration or verified disaster-recovery run was found in the inspected local deployment configuration. Do not infer a backup is recoverable until an isolated restore has succeeded.

## Safer migration strategy

1. Stop automatic destructive schema cleanup. Preserve retired tables and fields until the owner explicitly approves a data-retention decision backed by a documented inventory and verified restore.
2. Use version-controlled Alembic revisions for forward schema changes. Alembic is already a dependency, but `backend/alembic/versions` is empty and there is no usable revision history in the inspected repository. Do not generate an initial revision blindly against an unknown live schema: first compare a schema-only dump and model metadata from isolated copies, then baseline deliberately.
3. Prefer expand/migrate/contract: add compatible fields or tables; deploy code that can tolerate both shapes; backfill in bounded, restartable transactions; validate counts, nulls, foreign keys, and financial invariants; switch reads/writes; only later consider a separately approved archive/removal revision.
4. Require an independently stored, encrypted, timestamped backup and a checksum/manifest; restore it into a separate isolated PostgreSQL database and verify schema, row counts, key business totals (sales, payments, refunds, stock, ledger), and application reads before any migration.
5. Run each revision on a disposable copy of representative data, test idempotency where appropriate, inspect generated SQL, measure locks/downtime, and require explicit operator confirmation for destructive SQL.
6. Keep a recovery path: stop writes, preserve the failed database snapshot, restore the pre-migration backup into a new database, validate financial reconciliation, then switch configuration only after review. A down migration is not a substitute for a verified backup, especially after data-changing migrations.

Alembic is appropriate for future controlled schema changes, but adopting it safely requires inventorying/baselining the current schema and reconciling the custom initializer. No migration-system replacement or migration execution was performed in this review.

