"""B-owned business-authorization schema, invoked after A's identity schema.

Additive and idempotent: it never deletes rows, never assigns ownership to
existing records and never touches running jobs.
"""

from __future__ import annotations

from .audit import initialize_audit_schema
from .directory_grants import initialize_grant_schema
from .execution_control import initialize_execution_schema


def _add_column(connection, table: str, column: str, ddl: str) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return
    columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    if column not in columns:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def initialize_access_schema(connect) -> None:
    with connect() as connection:
        initialize_audit_schema(connection)
        initialize_grant_schema(connection)
        initialize_execution_schema(connection)


def add_owner_columns(connection) -> None:
    """Owner binding for per-user queues created by business services."""
    _add_column(connection, "chat_turns", "owner_id", "TEXT")
    _add_column(connection, "operations", "owner_id", "TEXT")
