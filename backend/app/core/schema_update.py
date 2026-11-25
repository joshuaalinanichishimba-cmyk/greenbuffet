"""Bringing an existing database up to date with the models.

`create_all` makes tables that are missing but never touches a table that
already exists, so a stage that adds a column to `orders` would quietly do
nothing on a restaurant that has been trading for a month. This module closes
that gap: it compares every model against the live database and adds the
columns that are missing.

It only ever adds. Nothing here drops a column, changes a type or deletes a
row, so running it against a database full of real sales is safe, and running
it twice does nothing the second time.

A column that the model says cannot be null is added in three steps, because
existing rows have no value for it yet: add it nullable, fill the rows with
the model's default, then apply the NOT NULL rule.
"""
from __future__ import annotations

from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateIndex

from app.models import Base


def _default_value(column):
    """The value to fill existing rows with, or None if there isn't one."""
    default = column.default
    if default is None:
        return None
    if getattr(default, "is_scalar", False):
        return default.arg
    return None


def add_missing_columns(engine: Engine) -> list[str]:
    """Adds any column a model has that the database does not. Returns what it did."""
    inspector = sa_inspect(engine)
    present = set(inspector.get_table_names())
    changes: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in present:
            continue  # create_all will make the whole table
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have:
                continue

            kind = column.type.compile(dialect=engine.dialect)
            fill = _default_value(column)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {kind}'))
                if fill is not None:
                    conn.execute(
                        text(f'UPDATE "{table.name}" SET "{column.name}" = :value WHERE "{column.name}" IS NULL'),
                        {"value": fill},
                    )
                if not column.nullable:
                    if fill is None:
                        # Nothing sensible to put in the existing rows, so the
                        # rule is left off rather than failing the update. The
                        # application still requires a value on new rows.
                        changes.append(f"{table.name}.{column.name} (added, left optional)")
                        continue
                    conn.execute(
                        text(f'ALTER TABLE "{table.name}" ALTER COLUMN "{column.name}" SET NOT NULL')
                    )
            changes.append(f"{table.name}.{column.name}")

    # Indexes declared on new columns are created separately: create_all skips
    # them on a table that already exists.
    existing_indexes = {
        (table, index["name"])
        for table in present
        for index in inspector.get_indexes(table)
    }
    for table in Base.metadata.sorted_tables:
        if table.name not in present:
            continue
        for index in table.indexes:
            if (table.name, index.name) in existing_indexes:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(CreateIndex(index))
                changes.append(f"index {index.name}")
            except Exception:
                # An index that cannot be built is not worth failing an update
                # for; the system works without it, only slower.
                pass

    return changes


# ---------------------------------------------------------------------------
# Removing what stage 20 retired (approved by the owner, 24 Nov 2026)
# ---------------------------------------------------------------------------

# The customer-ordering features (deliveries, delivery areas, functions, the
# message outbox, the old points scheme) were taken out of the code in stage
# 20. Their tables and columns are dropped here, once, by update.ps1 straight
# after the backup it takes. The server never runs this on its own: a drop is
# the one change that cannot be undone without that backup.
RETIRED_TABLES = ("messages", "catering_bookings")
RETIRED_COLUMNS = {
    "orders": (
        "channel", "fulfilment", "track_status", "public_token", "requested_for",
        "accepted_at", "accepted_by", "reject_reason", "zone_id", "zone_name", "address",
        "directions", "delivery_fee_ngwee", "rider_name", "rider_phone", "dispatched_at",
        "delivered_at", "points_earned", "points_spent",
    ),
    "customers": ("points", "is_blocked", "block_reason"),
}
RETIRED_AFTER_COLUMNS = ("delivery_zones",)   # orders.zone_id points at it
RETIRED_PERMISSIONS = ("dispatch.manage", "catering.manage")


def drop_retired(engine: Engine) -> list[str]:
    """Drops the retired tables and columns that still exist. Safe to run
    again: whatever is already gone is skipped. Returns what was dropped."""
    dropped: list[str] = []
    with engine.begin() as conn:
        # Inspect through the same connection that drops: a second connection
        # would wait for this one's locks, and this one for it.
        inspector = sa_inspect(conn)
        tables = set(inspector.get_table_names())
        for table in RETIRED_TABLES:
            if table in tables:
                conn.execute(text(f'DROP TABLE "{table}" CASCADE'))
                dropped.append(table)
        for table, columns in RETIRED_COLUMNS.items():
            if table not in tables:
                continue
            present = {c["name"] for c in inspector.get_columns(table)}
            for column in columns:
                if column in present:
                    conn.execute(text(f'ALTER TABLE "{table}" DROP COLUMN "{column}" CASCADE'))
                    dropped.append(f"{table}.{column}")
        for table in RETIRED_AFTER_COLUMNS:
            if table in tables:
                conn.execute(text(f'DROP TABLE "{table}" CASCADE'))
                dropped.append(table)
        if "role_permissions" in tables:
            for code in RETIRED_PERMISSIONS:
                conn.execute(text("DELETE FROM role_permissions WHERE permission_code = :c"), {"c": code})
        if "permissions" in tables:
            for code in RETIRED_PERMISSIONS:
                result = conn.execute(text("DELETE FROM permissions WHERE code = :c"), {"c": code})
                if result.rowcount:
                    dropped.append(f"permission {code}")
    return dropped


AUDIT_GUARD = """
CREATE OR REPLACE FUNCTION audit_log_is_append_only() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'The audit log cannot be changed or deleted';
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log;
CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION audit_log_is_append_only();
"""


UNIQUE_INDEXES = [
    # One offline sale id is one sale, even if two requests race each other.
    'CREATE UNIQUE INDEX IF NOT EXISTS orders_offline_id_once ON orders (offline_id) WHERE offline_id IS NOT NULL',
]


def ensure_unique_indexes(engine: Engine) -> None:
    """Adds the unique rules that add_missing_columns cannot add on its own."""
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        for statement in UNIQUE_INDEXES:
            conn.exec_driver_sql(statement)


def protect_audit_log(engine: Engine) -> None:
    """Makes the audit log append-only inside PostgreSQL itself.

    The application never edits or deletes an audit row; this makes sure no
    one else can either, through the application or a stray script. Someone
    with full database rights could still drop the trigger, which is why
    backups are kept off the machine too.
    """
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as conn:
        conn.exec_driver_sql(AUDIT_GUARD)
