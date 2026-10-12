"""Read-only Task B legacy ownership report.

This command MUST NOT initialize LocalStore or apply migrations.
Usage: python scripts/task_b_resource_scope_report.py <sqlite-db>
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bakend"))
# Imports only the pure mapping/report module: no LocalStore, no schema setup.
from app.access.ownership_migration import unassigned_report  # noqa: E402


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
            report = unassigned_report(db)
    except sqlite3.Error as exc:
        print(json.dumps({"error": "database_read_failed", "detail": str(exc)}))
        return 2

    print(json.dumps({
        "count": len(report),
        "resources": report,
        "action": "assign_explicit_creator_manager_project_scope_before_release",
        "next_step": "python scripts/task_b_assign_ownership.py <sqlite-db> <mapping.json> [--apply]",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
