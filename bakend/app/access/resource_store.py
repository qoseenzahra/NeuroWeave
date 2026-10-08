from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class ResourceStoreError(RuntimeError):
    pass


class ResourceScope(str, Enum):
    PRIVATE = "private"
    PROJECT = "project"


@dataclass(frozen=True)
class StoredResourcePolicy:
    resource_type: str
    resource_id: str
    creator_id: str
    manager_id: str
    project_id: str | None
    scope: ResourceScope
    permission_revision: int = 0


class ResourcePolicyStore(Protocol):
    def get_policy(self, resource_type: str, resource_id: str) -> StoredResourcePolicy | None: ...
    def put_policy(self, policy: StoredResourcePolicy) -> None: ...
    def delete_policy(self, resource_type: str, resource_id: str) -> None: ...


class SQLiteResourcePolicyStore:
    """Durable ownership/sharing registry used by business resources.

    The registry is deliberately separate from account/membership storage. A owns
    identity and project membership; B owns resource policy state.
    """

    def __init__(self, connect):
        self._connect = connect

    def get_policy(self, resource_type: str, resource_id: str):
        with self._connect() as db:
            row = db.execute(
                """SELECT resource_type,resource_id,creator_id,manager_id,project_id,
                          scope,permission_revision
                   FROM resource_policies WHERE resource_type=? AND resource_id=?""",
                (resource_type, resource_id),
            ).fetchone()
        if row is None:
            return None
        return StoredResourcePolicy(
            resource_type=row["resource_type"], resource_id=row["resource_id"],
            creator_id=row["creator_id"], manager_id=row["manager_id"],
            project_id=row["project_id"], scope=ResourceScope(row["scope"]),
            permission_revision=row["permission_revision"],
        )

    def put_policy(self, policy: StoredResourcePolicy) -> None:
        if not policy.creator_id or not policy.manager_id:
            raise ResourceStoreError("creator_and_manager_required")
        with self._connect() as db:
            db.execute(
                """INSERT INTO resource_policies
                   (resource_type,resource_id,creator_id,manager_id,project_id,scope,permission_revision)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(resource_type,resource_id) DO UPDATE SET
                   manager_id=excluded.manager_id,project_id=excluded.project_id,
                   scope=excluded.scope,permission_revision=excluded.permission_revision""",
                (policy.resource_type, policy.resource_id, policy.creator_id,
                 policy.manager_id, policy.project_id, policy.scope.value,
                 policy.permission_revision),
            )

    def delete_policy(self, resource_type: str, resource_id: str) -> None:
        with self._connect() as db:
            db.execute(
                "DELETE FROM resource_policies WHERE resource_type=? AND resource_id=?",
                (resource_type, resource_id),
            )

    def legacy_scope_report(self) -> list[dict[str, object]]:
        """Report existing business records that have no ownership assignment.
        The report is read-only so migration cannot accidentally expose records.
        """
        tables = {
            "conversation": "conversations",
            "dataset": "datasets",
            "pipeline": "workflows",
            "run": "runs",
        }
        report: list[dict[str, object]] = []
        with self._connect() as db:
            for resource_type, table in tables.items():
                id_column = {
                    "conversation": "conversation_id",
                    "dataset": "dataset_id",
                    "pipeline": "workflow_id",
                    "run": "run_id",
                }[resource_type]
                rows = db.execute(
                    f"""SELECT {id_column} AS resource_id FROM {table}
                        WHERE NOT EXISTS (
                          SELECT 1 FROM resource_policies p
                          WHERE p.resource_type=? AND p.resource_id={table}.{id_column}
                        )""",
                    (resource_type,),
                ).fetchall()
                for row in rows:
                    report.append({
                        "resource_type": resource_type,
                        "resource_id": row["resource_id"],
                        "status": "unassigned",
                    })
        return report

    def unassigned(self, resource_type: str | None = None) -> list[tuple[str, str]]:
        with self._connect() as db:
            if resource_type:
                rows = db.execute(
                    "SELECT resource_type,resource_id FROM resource_policies "
                    "WHERE creator_id='' OR manager_id='' AND resource_type=?",
                    (resource_type,),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT resource_type,resource_id FROM resource_policies "
                    "WHERE creator_id='' OR manager_id=''"
                ).fetchall()
        return [(row["resource_type"], row["resource_id"]) for row in rows]
