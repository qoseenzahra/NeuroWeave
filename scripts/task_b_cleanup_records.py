"""Remove obsolete, unassigned development records (database rows only).

Dry run by default; ``--apply`` removes everything in one transaction or
nothing. Only records without an owner can be removed. Files on disk are
never touched, and tasks with runs, datasets used by tasks or run snapshots,
and outputs with active runs or pending file operations are refused. This
tool does not deploy anything; run it within the unified release workflow.

Usage:
  python scripts/task_b_cleanup_records.py <sqlite-db> <cleanup.json>
  python scripts/task_b_cleanup_records.py <sqlite-db> <cleanup.json> --apply

cleanup.json: {"remove": [{"resource_type": "conversation", "resource_id": "conv_x"}]}
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bakend"))
from app.access.ownership_migration import (  # noqa: E402
    MappingError, apply_cleanup, load_cleanup_list, plan_cleanup,
)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    flags = {a for a in argv if a.startswith("--")}
    if len(args) != 2 or flags - {"--apply"}:
        print(__doc__)
        return 2
    database = Path(args[0]).expanduser().resolve()
    if not database.is_file():
        print(json.dumps({"error": "database_not_found", "path": str(database)}))
        return 2
    try:
        items = load_cleanup_list(Path(args[1]).read_text(encoding="utf-8"))
        if "--apply" in flags:
            plan = apply_cleanup(database, items)
            print(json.dumps({"removed": len(plan), "records": plan}, indent=2))
        else:
            connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
            try:
                plan = plan_cleanup(connection, items)
            finally:
                connection.close()
            print(json.dumps({"dry_run": True, "would_remove": len(plan), "records": plan}, indent=2))
    except (MappingError, OSError, sqlite3.Error) as exc:
        print(json.dumps({"error": "cleanup_rejected", "detail": str(exc)}))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
