"""Assign explicit owners to records created before Task B authorization.

Dry run by default: validates the mapping against a read-only connection and
prints the plan. ``--apply`` writes every assignment in one transaction or
none at all. Unlisted records stay invisible to every user. The tool never
deletes records, never edits schema and never touches running jobs; it does
not deploy anything.

Usage:
  python scripts/task_b_assign_ownership.py <sqlite-db> --template > mapping.json
  python scripts/task_b_assign_ownership.py <sqlite-db> <mapping.json>
  python scripts/task_b_assign_ownership.py <sqlite-db> <mapping.json> --apply

Mapping format:
  {"assignments": [{"resource_type": "dataset", "resource_id": "ds_1",
                    "creator_id": "alice", "manager_id": "alice",
                    "project_id": "lab", "scope": "project"}]}
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bakend"))
from app.access.ownership_migration import (  # noqa: E402
    OWNED_TABLES, MappingError, apply, load_mapping, unassigned_report, validate,
)


def _read_only(database: Path):
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if len(args) not in {1, 2} or flags - {"--apply", "--template"}:
        print(__doc__)
        return 2
    database = Path(args[0]).expanduser().resolve()
    if not database.is_file():
        print(json.dumps({"error": "database_not_found", "path": str(database)}))
        return 2
    if "--template" in flags:
        connection = _read_only(database)
        try:
            report = [r for r in unassigned_report(connection) if r["resource_type"] in OWNED_TABLES]
        finally:
            connection.close()
        print(json.dumps({"assignments": [
            {"resource_type": r["resource_type"], "resource_id": r["resource_id"],
             "creator_id": "", "manager_id": "", "project_id": None, "scope": "private"}
            for r in report
        ]}, indent=2))
        return 0
    if len(args) != 2:
        print(__doc__)
        return 2
    try:
        assignments = load_mapping(Path(args[1]).read_text(encoding="utf-8"))
        if "--apply" in flags:
            plan = apply(database, assignments)
            print(json.dumps({"applied": len(plan), "assignments": plan}, indent=2))
        else:
            connection = _read_only(database)
            try:
                plan = validate(connection, assignments)
            finally:
                connection.close()
            print(json.dumps({"dry_run": True, "would_assign": len(plan), "assignments": plan}, indent=2))
    except (MappingError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": "mapping_rejected", "detail": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
