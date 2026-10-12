from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "task_b_resource_scope_report.py"


def test_scope_report_does_not_create_missing_database(tmp_path):
    missing = tmp_path / "must-not-be-created.sqlite"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(missing)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not missing.exists()


def test_scope_report_reads_existing_database_without_schema_changes(tmp_path):
    database = tmp_path / "legacy.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE conversations (conversation_id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO conversations VALUES ('conv-legacy')")
        db.execute("CREATE TABLE datasets (dataset_id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO datasets VALUES ('dataset-legacy')")
    before = database.stat().st_size

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(database)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["count"] == 2
    assert {item["resource_id"] for item in report["resources"]} == {
        "conv-legacy", "dataset-legacy"
    }
    assert database.stat().st_size == before
    with sqlite3.connect(database) as db:
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert "resource_policies" not in tables
