"""Durable execution authorization: quotas, idempotent submission, frozen scopes.

Reservations live in the shared SQLite database and are taken inside
``BEGIN IMMEDIATE`` transactions, so two API processes (or two threads) cannot
both observe free capacity and overrun the same quota. Concurrency is measured
in actual execution units (parallel samples across nodes), not in runs.

Each accepted run stores a frozen authorization scope: submitter, project,
server execution identity, inputs, output and the grant/permission revisions in
force at acceptance. Running workers never consult browser login state, and the
frozen scope is never reused to authorize new submissions or new directories.
Revocation does not cancel Slurm jobs.
"""

from __future__ import annotations

import getpass
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from .contracts import AuthorizationDenied

SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_quotas (
    subject TEXT PRIMARY KEY,
    max_concurrent_units INTEGER NOT NULL,
    max_cpus_per_unit INTEGER NOT NULL,
    max_memory_gb_per_unit INTEGER NOT NULL,
    max_gpus_per_unit INTEGER NOT NULL,
    allowed_nodes_json TEXT,
    updated_by TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_authorizations (
    reservation_id TEXT PRIMARY KEY,
    run_id TEXT UNIQUE,
    workflow_id TEXT NOT NULL,
    submitter_id TEXT NOT NULL,
    project_id TEXT,
    execution_identity TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    units INTEGER NOT NULL,
    frozen_scope_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('reserved','released')),
    cancelled_by TEXT,
    created_at TEXT NOT NULL,
    released_at TEXT,
    UNIQUE(submitter_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_run_authorizations_active
    ON run_authorizations(status, submitter_id, project_id);
"""

TERMINAL_RUN_STATES = ("cancelled", "succeeded", "failed")
UNBOUND_RESERVATION_TTL = timedelta(minutes=10)


def initialize_execution_schema(connection) -> None:
    connection.executescript(SCHEMA)


class QuotaExceeded(PermissionError):
    pass


@dataclass(frozen=True)
class QuotaPolicy:
    max_concurrent_units: int
    max_cpus_per_unit: int
    max_memory_gb_per_unit: int
    max_gpus_per_unit: int
    allowed_nodes: tuple[str, ...] | None = None

    def as_dict(self) -> dict:
        return {
            "max_concurrent_units": self.max_concurrent_units,
            "max_cpus_per_unit": self.max_cpus_per_unit,
            "max_memory_gb_per_unit": self.max_memory_gb_per_unit,
            "max_gpus_per_unit": self.max_gpus_per_unit,
            "allowed_nodes": list(self.allowed_nodes) if self.allowed_nodes is not None else None,
        }


def default_quota() -> QuotaPolicy:
    """Restricted default for users without an explicit quota row."""
    return QuotaPolicy(
        max_concurrent_units=max(1, int(os.getenv("NEUROWEAVE_DEFAULT_CONCURRENT_UNITS", "2"))),
        max_cpus_per_unit=max(1, int(os.getenv("NEUROWEAVE_DEFAULT_MAX_CPUS_PER_UNIT", "8"))),
        max_memory_gb_per_unit=max(1, int(os.getenv("NEUROWEAVE_DEFAULT_MAX_MEMORY_GB_PER_UNIT", "32"))),
        max_gpus_per_unit=max(0, int(os.getenv("NEUROWEAVE_DEFAULT_MAX_GPUS_PER_UNIT", "0"))),
    )


def execution_units(execution) -> list[dict]:
    """Expand execution options into the actual concurrently running units."""
    base = {
        "cpus": execution.cpus, "memory_gb": execution.memory_gb,
        "gpus": execution.gpus, "node": execution.node,
    }
    if not execution.nodes:
        return [base]
    units = []
    for allocation in execution.nodes:
        parallel = allocation.parallel_samples if execution.sample_mode == "per_sample" else 1
        units.extend(
            {
                "cpus": allocation.cpus, "memory_gb": allocation.memory_gb,
                "gpus": allocation.gpus, "node": allocation.node,
            }
            for _ in range(parallel)
        )
    return units


class ExecutionControl:
    def __init__(self, store):
        self.store = store

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # ---------------------------------------------------------------- quotas
    def quota_for(self, subject: str, connection=None) -> QuotaPolicy:
        def read(db):
            return db.execute("SELECT * FROM execution_quotas WHERE subject=?", (subject,)).fetchone()
        if connection is not None:
            row = read(connection)
        else:
            with self.store._connect() as db:
                row = read(db)
        if row is None:
            return default_quota()
        nodes = json.loads(row["allowed_nodes_json"]) if row["allowed_nodes_json"] else None
        return QuotaPolicy(
            row["max_concurrent_units"], row["max_cpus_per_unit"],
            row["max_memory_gb_per_unit"], row["max_gpus_per_unit"],
            tuple(nodes) if nodes is not None else None,
        )

    def set_quota(self, subject: str, policy: QuotaPolicy, *, updated_by: str) -> dict:
        if policy.max_concurrent_units < 1 or policy.max_cpus_per_unit < 1 or policy.max_memory_gb_per_unit < 1:
            raise ValueError("quota_values_must_be_positive")
        if policy.max_gpus_per_unit < 0:
            raise ValueError("quota_values_must_be_positive")
        with self.store._lock, self.store._connect() as db:
            db.execute(
                """INSERT INTO execution_quotas VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(subject) DO UPDATE SET
                   max_concurrent_units=excluded.max_concurrent_units,
                   max_cpus_per_unit=excluded.max_cpus_per_unit,
                   max_memory_gb_per_unit=excluded.max_memory_gb_per_unit,
                   max_gpus_per_unit=excluded.max_gpus_per_unit,
                   allowed_nodes_json=excluded.allowed_nodes_json,
                   updated_by=excluded.updated_by, updated_at=excluded.updated_at""",
                (
                    subject, policy.max_concurrent_units, policy.max_cpus_per_unit,
                    policy.max_memory_gb_per_unit, policy.max_gpus_per_unit,
                    json.dumps(list(policy.allowed_nodes)) if policy.allowed_nodes is not None else None,
                    updated_by, self._now(),
                ),
            )
        return {"subject": subject, **policy.as_dict()}

    @staticmethod
    def _check_unit_limits(units: list[dict], policy: QuotaPolicy, label: str) -> None:
        for unit in units:
            if unit["cpus"] > policy.max_cpus_per_unit:
                raise QuotaExceeded(f"{label}_per_unit_cpu_limit_exceeded")
            if unit["memory_gb"] > policy.max_memory_gb_per_unit:
                raise QuotaExceeded(f"{label}_per_unit_memory_limit_exceeded")
            if unit["gpus"] > policy.max_gpus_per_unit:
                raise QuotaExceeded(f"{label}_per_unit_gpu_limit_exceeded")
            if policy.allowed_nodes is not None and unit["node"] and unit["node"] not in policy.allowed_nodes:
                raise QuotaExceeded(f"{label}_node_not_allowed")

    # ---------------------------------------------------------- reservations
    @staticmethod
    def _release_finished(db) -> None:
        placeholders = ",".join("?" for _ in TERMINAL_RUN_STATES)
        db.execute(
            f"""UPDATE run_authorizations SET status='released', released_at=?
                WHERE status='reserved' AND run_id IN (
                    SELECT run_id FROM runs WHERE status IN ({placeholders}))""",
            (datetime.now(timezone.utc).isoformat(), *TERMINAL_RUN_STATES),
        )
        expired = (datetime.now(timezone.utc) - UNBOUND_RESERVATION_TTL).isoformat()
        db.execute(
            "UPDATE run_authorizations SET status='released', released_at=? "
            "WHERE status='reserved' AND run_id IS NULL AND created_at < ?",
            (datetime.now(timezone.utc).isoformat(), expired),
        )

    def existing(self, submitter_id: str, idempotency_key: str) -> dict | None:
        with self.store._connect() as db:
            row = db.execute(
                "SELECT * FROM run_authorizations WHERE submitter_id=? AND idempotency_key=?",
                (submitter_id, idempotency_key),
            ).fetchone()
        return dict(row) if row else None

    def reserve(
        self, *, workflow_id: str, submitter_id: str, project_id: str | None,
        idempotency_key: str, execution, frozen_scope: dict,
    ) -> dict:
        """Atomically check quotas and reserve units across processes.

        Returns the reservation row. If the same submitter already used the
        idempotency key, the existing reservation is returned unchanged and no
        new capacity is consumed (``replayed`` is True).
        """
        units = execution_units(execution)
        user_policy = None
        connection = sqlite3.connect(self.store.database_path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM run_authorizations WHERE submitter_id=? AND idempotency_key=?",
                (submitter_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                connection.execute("COMMIT")
                if existing["workflow_id"] != workflow_id:
                    raise ValueError("idempotency_key_reused_for_different_task")
                return {**dict(existing), "replayed": True}
            self._release_finished(connection)
            user_policy = self.quota_for(f"user:{submitter_id}", connection)
            self._check_unit_limits(units, user_policy, "user")
            in_use = connection.execute(
                "SELECT COALESCE(SUM(units),0) FROM run_authorizations WHERE status='reserved' AND submitter_id=?",
                (submitter_id,),
            ).fetchone()[0]
            if in_use + len(units) > user_policy.max_concurrent_units:
                raise QuotaExceeded("user_concurrency_quota_exceeded")
            if project_id:
                project_policy = self.quota_for(f"project:{project_id}", connection)
                self._check_unit_limits(units, project_policy, "project")
                project_use = connection.execute(
                    "SELECT COALESCE(SUM(units),0) FROM run_authorizations WHERE status='reserved' AND project_id=?",
                    (project_id,),
                ).fetchone()[0]
                if project_use + len(units) > project_policy.max_concurrent_units:
                    raise QuotaExceeded("project_concurrency_quota_exceeded")
            reservation_id = "resv_" + uuid4().hex[:16]
            frozen = {**frozen_scope, "units": units, "execution_identity": getpass.getuser()}
            connection.execute(
                "INSERT INTO run_authorizations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    reservation_id, None, workflow_id, submitter_id, project_id,
                    getpass.getuser(), idempotency_key, len(units),
                    json.dumps(frozen, ensure_ascii=False, sort_keys=True),
                    "reserved", None, self._now(), None,
                ),
            )
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        row = self.reservation(reservation_id)
        return {**(row or {}), "replayed": False}

    def reservation(self, reservation_id: str) -> dict | None:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM run_authorizations WHERE reservation_id=?", (reservation_id,)).fetchone()
        return dict(row) if row else None

    def bind_run(self, reservation_id: str, run_id: str) -> None:
        with self.store._lock, self.store._connect() as db:
            db.execute(
                "UPDATE run_authorizations SET run_id=? WHERE reservation_id=? AND run_id IS NULL",
                (run_id, reservation_id),
            )

    def release(self, reservation_id: str) -> None:
        with self.store._lock, self.store._connect() as db:
            db.execute(
                "UPDATE run_authorizations SET status='released', released_at=? WHERE reservation_id=? AND status='reserved'",
                (self._now(), reservation_id),
            )

    def for_run(self, run_id: str) -> dict | None:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM run_authorizations WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["frozen_scope"] = json.loads(result.pop("frozen_scope_json"))
        return result

    def record_cancellation(self, run_id: str, actor_id: str) -> None:
        with self.store._lock, self.store._connect() as db:
            db.execute(
                "UPDATE run_authorizations SET cancelled_by=? WHERE run_id=? AND cancelled_by IS NULL",
                (actor_id, run_id),
            )

    def usage(self, *, submitter_id: str | None = None, project_id: str | None = None) -> int:
        with self.store._lock, self.store._connect() as db:
            self._release_finished(db)
            if submitter_id is not None:
                return db.execute(
                    "SELECT COALESCE(SUM(units),0) FROM run_authorizations WHERE status='reserved' AND submitter_id=?",
                    (submitter_id,),
                ).fetchone()[0]
            return db.execute(
                "SELECT COALESCE(SUM(units),0) FROM run_authorizations WHERE status='reserved' AND project_id=?",
                (project_id,),
            ).fetchone()[0]


def require_not_expanded(frozen_scope: dict, *, workflow_id: str, workflow_revision: int) -> None:
    """A frozen grant only covers the exact accepted plan."""
    if frozen_scope.get("workflow_id") != workflow_id or frozen_scope.get("workflow_revision") != workflow_revision:
        raise AuthorizationDenied("execution_grant_does_not_cover_plan")
