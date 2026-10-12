"""Business audit emission for resource, file, run and model events.

A owns the common audit storage, query API and UI. Until A's ``AuditSink`` is
wired, B writes the same event shape to a local append-only table so no business
event is dropped; A's migration can import these rows. Sensitive values
(file contents, passwords, tokens, keys) are never passed to ``record``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

from .request_context import request_id

SCHEMA = """
CREATE TABLE IF NOT EXISTS business_audit_events (
    event_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    event TEXT NOT NULL,
    user_id TEXT NOT NULL,
    project_id TEXT,
    resource_type TEXT NOT NULL,
    resource_id TEXT,
    action TEXT NOT NULL,
    outcome TEXT NOT NULL,
    reason TEXT,
    request_id TEXT,
    summary_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_business_audit_resource
    ON business_audit_events(resource_type, resource_id, created_at);
"""

_FORBIDDEN_SUMMARY_KEYS = {"text", "content", "password", "token", "secret", "api_key", "cookie"}


def initialize_audit_schema(connection) -> None:
    connection.executescript(SCHEMA)


class SQLiteBusinessAuditSink:
    def __init__(self, connect, *, forward=None):
        self._connect = connect
        self.forward = forward  # A's common AuditSink, when wired

    def record(
        self, event: str, *, user_id: str, project_id: str | None,
        resource_type: str, resource_id: str | None,
        action: str, reason: str | None = None, summary: dict | None = None,
        connection=None,
    ) -> None:
        """Append one event.

        ``connection`` lets a caller that is already inside a write transaction
        (for example ownership assignment during creation) write the event in
        the same transaction instead of waiting on its own lock.
        """
        outcome = "denied" if (reason or "").startswith("denied:") else "allowed"
        clean = {
            key: value for key, value in (summary or {}).items()
            if key.lower() not in _FORBIDDEN_SUMMARY_KEYS
        }
        values = (
            uuid4().hex, datetime.now(timezone.utc).isoformat(), event,
            user_id or "", project_id, resource_type, resource_id, action,
            outcome, reason, request_id(), json.dumps(clean, ensure_ascii=False),
        )
        sql = "INSERT INTO business_audit_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?)"
        if connection is not None:
            connection.execute(sql, values)
        else:
            with self._connect() as db:
                db.execute(sql, values)
        if self.forward is not None:
            self.forward.record(
                event, user_id=user_id, project_id=project_id,
                resource_type=resource_type, resource_id=resource_id,
                action=action, reason=reason,
            )

    def events(self, resource_type: str | None = None, resource_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM business_audit_events"
        params: tuple = ()
        if resource_type:
            sql += " WHERE resource_type=?"
            params = (resource_type,)
            if resource_id:
                sql += " AND resource_id=?"
                params += (resource_id,)
        with self._connect() as db:
            return [dict(row) for row in db.execute(sql + " ORDER BY created_at", params)]
