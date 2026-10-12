"""Explicit ownership assignment for records created before Task B.

Records without a policy row are invisible to everyone (fail closed). This
module never guesses an owner: it reports unassigned records and applies an
explicit, reviewed mapping. It never deletes records, never touches running
jobs and never changes schema; the application initializes the schema.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Iterable

# resource_type -> (table, id column). Runs, messages and historical results
# inherit from their parent and therefore never get their own row.
OWNED_TABLES: dict[str, tuple[str, str]] = {
    "conversation": ("conversations", "conversation_id"),
    "dataset": ("datasets", "dataset_id"),
    "task": ("workflows", "workflow_id"),
    "output": ("workspaces", "id"),
    "pipeline": ("pipeline_library", "id"),
    "pipeline_draft": ("pipeline_drafts", "id"),
}
INHERITED_TABLES: dict[str, tuple[str, str, str]] = {
    # resource_type -> (table, id column, parent id column); parent type is task.
    "run": ("runs", "run_id", "workflow_id"),
}


class MappingError(ValueError):
    pass


@dataclass(frozen=True)
class Assignment:
    resource_type: str
    resource_id: str
    creator_id: str
    manager_id: str
    project_id: str | None
    scope: str

    @classmethod
    def parse(cls, raw: dict) -> "Assignment":
        if not isinstance(raw, dict):
            raise MappingError("each assignment must be an object")
        resource_type = str(raw.get("resource_type") or "")
        if resource_type not in OWNED_TABLES:
            raise MappingError(f"unsupported resource_type: {resource_type!r}")
        resource_id = str(raw.get("resource_id") or "")
        creator = str(raw.get("creator_id") or "")
        manager = str(raw.get("manager_id") or creator)
        project = raw.get("project_id")
        project = str(project) if project not in (None, "") else None
        scope = str(raw.get("scope") or "private")
        if not resource_id or not creator or not manager:
            raise MappingError(f"{resource_type}:{resource_id} needs resource_id and creator_id")
        if scope not in {"private", "project"}:
            raise MappingError(f"{resource_type}:{resource_id} has invalid scope {scope!r}")
        if scope == "project" and project is None:
            raise MappingError(f"{resource_type}:{resource_id} project scope requires project_id")
        if resource_type == "conversation" and scope != "private":
            raise MappingError(f"conversation:{resource_id} must stay private")
        return cls(resource_type, resource_id, creator, manager, project, scope)


def _tables(db) -> set[str]:
    return {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def unassigned_report(db) -> list[dict[str, str]]:
    """Read-only list of records that nobody can currently see."""
    tables = _tables(db)
    has_policies = "resource_policies" in tables
    report: list[dict[str, str]] = []
    for resource_type, (table, column) in OWNED_TABLES.items():
        if table not in tables:
            continue
        if has_policies:
            rows = db.execute(
                f"SELECT DISTINCT r.{column} FROM {table} r WHERE NOT EXISTS ("
                "SELECT 1 FROM resource_policies p WHERE p.resource_type=? AND p.resource_id=r."
                f"{column})",
                (resource_type,),
            ).fetchall()
        else:
            rows = db.execute(f"SELECT DISTINCT {column} FROM {table}").fetchall()
        report.extend(
            {"resource_type": resource_type, "resource_id": str(row[0]), "status": "unassigned"}
            for row in rows
        )
    unassigned_tasks = {item["resource_id"] for item in report if item["resource_type"] == "task"}
    for resource_type, (table, column, parent) in INHERITED_TABLES.items():
        if table not in tables or not unassigned_tasks:
            continue
        for row in db.execute(f"SELECT {column},{parent} FROM {table}"):
            if str(row[1]) in unassigned_tasks:
                report.append({
                    "resource_type": resource_type, "resource_id": str(row[0]),
                    "status": "inherits_unassigned_task", "task_id": str(row[1]),
                })
    return report


def load_mapping(text: str) -> list[Assignment]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MappingError(f"mapping is not valid JSON: {exc}") from exc
    items = data.get("assignments") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise MappingError("mapping must contain a non-empty 'assignments' list")
    assignments = [Assignment.parse(item) for item in items]
    keys = [(a.resource_type, a.resource_id) for a in assignments]
    if len(set(keys)) != len(keys):
        raise MappingError("mapping assigns the same resource more than once")
    return assignments


def validate(db, assignments: Iterable[Assignment]) -> list[dict]:
    """Check every assignment against the database without writing."""
    tables = _tables(db)
    if "resource_policies" not in tables:
        raise MappingError("resource_policies table missing; start the application once to initialize schema")
    plan = []
    for item in assignments:
        table, column = OWNED_TABLES[item.resource_type]
        if table not in tables or db.execute(
            f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1", (item.resource_id,)
        ).fetchone() is None:
            raise MappingError(f"{item.resource_type}:{item.resource_id} does not exist")
        if db.execute(
            "SELECT 1 FROM resource_policies WHERE resource_type=? AND resource_id=?",
            (item.resource_type, item.resource_id),
        ).fetchone() is not None:
            raise MappingError(f"{item.resource_type}:{item.resource_id} is already assigned")
        plan.append({**item.__dict__, "action": "assign"})
    return plan


def apply(database_path, assignments: list[Assignment]) -> list[dict]:
    """Validate and insert all assignments in one transaction (all or nothing)."""
    connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")
        plan = validate(connection, assignments)
        connection.executemany(
            "INSERT INTO resource_policies(resource_type,resource_id,creator_id,manager_id,"
            "project_id,scope,permission_revision) VALUES(?,?,?,?,?,?,0)",
            [
                (a.resource_type, a.resource_id, a.creator_id, a.manager_id, a.project_id, a.scope)
                for a in assignments
            ],
        )
        connection.execute("COMMIT")
        return plan
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
