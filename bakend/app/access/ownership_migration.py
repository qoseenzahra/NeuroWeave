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


# ------------------------------------------------------------------ cleanup
# Obsolete *unassigned* development records may be removed from the database.
# Research files on disk are never touched, and anything that valid results or
# active executions depend on is refused.
CLEANUP_TYPES = {"conversation", "dataset", "task", "output", "pipeline_draft"}
ACTIVE_RUN_STATES = ("queued", "running", "cancel_requested")


def _cleanup_blockers(db, resource_type: str, resource_id: str, tables: set[str]) -> list[str]:
    blockers: list[str] = []
    if resource_type == "task" and "runs" in tables:
        if db.execute("SELECT 1 FROM runs WHERE workflow_id=? LIMIT 1", (resource_id,)).fetchone():
            blockers.append("task has run records (results or active execution snapshots)")
    if resource_type == "dataset":
        if "workflows" in tables and db.execute(
            "SELECT 1 FROM workflows WHERE dataset_id=? LIMIT 1", (resource_id,)
        ).fetchone():
            blockers.append("dataset is used by a task")
        if "runs" in tables and db.execute(
            "SELECT 1 FROM runs r LEFT JOIN run_plans p ON p.run_id=r.run_id WHERE "
            "json_extract(COALESCE(p.payload_json, json_extract(r.payload_json,'$.plan_snapshot')),'$.dataset_id')=? LIMIT 1",
            (resource_id,),
        ).fetchone():
            blockers.append("dataset is part of a run snapshot")
    if resource_type == "output":
        placeholders = ",".join("?" for _ in ACTIVE_RUN_STATES)
        if "runs" in tables and db.execute(
            f"SELECT 1 FROM runs WHERE status IN ({placeholders}) AND json_extract(payload_json,'$.workspace_id')=? LIMIT 1",
            (*ACTIVE_RUN_STATES, resource_id),
        ).fetchone():
            blockers.append("output directory receives an active run")
        if "workspace_operations" in tables and db.execute(
            "SELECT 1 FROM workspace_operations WHERE workspace_id=? AND status IN ('pending','running') LIMIT 1",
            (resource_id,),
        ).fetchone():
            blockers.append("output directory has a pending file operation")
    return blockers


def load_cleanup_list(text: str) -> list[tuple[str, str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MappingError(f"cleanup list is not valid JSON: {exc}") from exc
    items = data.get("remove") if isinstance(data, dict) else data
    if not isinstance(items, list) or not items:
        raise MappingError("cleanup list must contain a non-empty 'remove' list")
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise MappingError("each cleanup entry must be an object")
        rtype, rid = str(item.get("resource_type") or ""), str(item.get("resource_id") or "")
        if rtype not in CLEANUP_TYPES:
            raise MappingError(f"cleanup of {rtype!r} is not supported")
        if not rid:
            raise MappingError("resource_id is required")
        result.append((rtype, rid))
    if len(set(result)) != len(result):
        raise MappingError("cleanup list repeats a resource")
    return result


def plan_cleanup(db, items: list[tuple[str, str]]) -> list[dict]:
    """Validate a cleanup list without writing; any problem rejects the whole list."""
    tables = _tables(db)
    has_policies = "resource_policies" in tables
    plan = []
    for rtype, rid in items:
        table, column = OWNED_TABLES[rtype]
        if table not in tables or db.execute(f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1", (rid,)).fetchone() is None:
            raise MappingError(f"{rtype}:{rid} does not exist")
        if has_policies and db.execute(
            "SELECT 1 FROM resource_policies WHERE resource_type=? AND resource_id=?", (rtype, rid)
        ).fetchone():
            raise MappingError(f"{rtype}:{rid} has an owner; only unassigned records can be cleaned up")
        blockers = _cleanup_blockers(db, rtype, rid, tables)
        if blockers:
            raise MappingError(f"{rtype}:{rid} kept: " + "; ".join(blockers))
        plan.append({"resource_type": rtype, "resource_id": rid, "action": "remove_database_record",
                     "files_on_disk": "untouched"})
    return plan


def apply_cleanup(database_path, items: list[tuple[str, str]]) -> list[dict]:
    connection = sqlite3.connect(database_path, timeout=30, isolation_level=None)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("BEGIN IMMEDIATE")
        plan = plan_cleanup(connection, items)
        tables = _tables(connection)
        for rtype, rid in items:
            if rtype == "conversation":
                if "chat_turns" in tables:
                    connection.execute("DELETE FROM chat_turns WHERE conversation_id=?", (rid,))
                connection.execute("DELETE FROM conversation_messages WHERE conversation_id=?", (rid,))
                connection.execute("DELETE FROM conversations WHERE conversation_id=?", (rid,))
            elif rtype == "task":
                for table in ("workflow_events", "execution_drafts"):
                    if table in tables:
                        connection.execute(f"DELETE FROM {table} WHERE workflow_id=?", (rid,))
                connection.execute("DELETE FROM workflows WHERE workflow_id=?", (rid,))
            elif rtype == "dataset":
                connection.execute("DELETE FROM datasets WHERE dataset_id=?", (rid,))
            elif rtype == "output":
                connection.execute("DELETE FROM workspaces WHERE id=?", (rid,))
            elif rtype == "pipeline_draft":
                connection.execute("DELETE FROM pipeline_drafts WHERE id=?", (rid,))
        connection.execute("COMMIT")
        return plan
    except BaseException:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
