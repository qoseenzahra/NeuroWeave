"""Read-only Task B legacy ownership report.

Usage:
    python scripts/task_b_resource_scope_report.py <sqlite-db>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bakend"))

from app.local_store import LocalStore


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python scripts/task_b_resource_scope_report.py <sqlite-db>")
        return 2
    report = LocalStore(Path(sys.argv[1])).resource_policies.legacy_scope_report()
    print(json.dumps({
        "count": len(report),
        "resources": report,
        "action": "assign_explicit_creator_manager_project_scope_before_release",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
