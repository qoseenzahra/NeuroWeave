"""Read-only Task B legacy ownership report.

This command MUST NOT initialize LocalStore or apply migrations.
Usage: python scripts/task_b_resource_scope_report.py <sqlite-db>
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


RESOURCE_TABLES = {
    "conversation": ("conversations", "conversation_id"),
    "dataset": ("datasets", "dataset_id"),
    "pipeline": ("workflows", "workflow_id"),
    "run": ("runs", "run_id"),
}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/task_b_resource_scope_report.py <sqlite-db>")
        return 2

    database = Path(sys.argv[1]).expanduser().resolve()
    if not database.is_file():
        print(json.dumps({"error": "database_not_found", "path": str(database)}))
        return 2

    # SQLite mode=ro prevents accidental creation, schema changes, and writes.
    uri = database.as_uri() + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True) as db:
            db.row_factory = sqlite3.Row
            existing = {
                row["name"]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            has_policies = "resource_policies" in existing
            report: list[dict[str, str]] = []
            for resource_type, (table, id_column) in RESOURCE_TABLES.items():
                if table not in existing:
                    continue
                if has_policies:
                    query = f"""
                        SELECT r.{id_column} AS resource_id
                        FROM {table} AS r
                        WHERE NOT EXISTS (
                            SELECT 1 FROM resource_policies AS p
                            WHERE p.resource_type = ?
                              AND p.resource_id = r.{id_column}
                        )
                    """
                    rows = db.execute(query, (resource_type,)).fetchall()
                else:
                    rows = db.execute(
                        f"SELECT {id_column} AS resource_id FROM {table}"
                    ).fetchall()
                report.extend(
                    {
                        "resource_type": resource_type,
                        "resource_id": str(row["resource_id"]),
                        "status": "unassigned",
                    }
                    for row in rows
                )
    except sqlite3.Error as exc:
        print(json.dumps({"error": "database_read_failed", "detail": str(exc)}))
        return 2

    print(json.dumps({
        "count": len(report),
        "resources": report,
        "action": "assign_explicit_creator_manager_project_scope_before_release",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
