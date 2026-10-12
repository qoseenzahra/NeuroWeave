"""Bounded, persistent background scans and dry-runs. Never executes workflow jobs."""
from __future__ import annotations

import contextvars
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Event, RLock
from uuid import uuid4

from .operation_context import OperationCancelled, OperationContext, checkpoint, current_operation


class OperationService:
    def __init__(self, store):
        self.store = store
        self._lock = RLock()
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="neuroweave-check")
        self._events = {}
        with store._connect() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS operations(
                operation_id TEXT PRIMARY KEY, kind TEXT NOT NULL, entity_key TEXT NOT NULL,
                status TEXT NOT NULL, message TEXT NOT NULL, result_json TEXT, error_json TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            connection.execute("""UPDATE operations SET status='failed',message='后端重启，请重新发起检查'
                WHERE status IN ('queued','running','cancel_requested')""")
            from .access.schema import add_owner_columns
            add_owner_columns(connection)

    def get(self, operation_id, *, owner_id=None):
        with self.store._connect() as connection:
            row = connection.execute("SELECT * FROM operations WHERE operation_id=?", (operation_id,)).fetchone()
        if row is None:
            raise KeyError(operation_id)
        # Background checks belong to their initiator; another user's operation
        # is reported as nonexistent rather than forbidden.
        if owner_id is not None and row["owner_id"] != owner_id:
            raise KeyError(operation_id)
        value = dict(row)
        value["result"] = json.loads(value.pop("result_json")) if value["result_json"] else None
        value.pop("result_json", None)
        value["error"] = json.loads(value.pop("error_json")) if value["error_json"] else None
        value.pop("error_json", None)
        return value

    def submit(self, kind, entity_key, action, *, owner_id=None):
        with self._lock, self.store._connect() as connection:
            active = connection.execute("SELECT * FROM operations WHERE status IN ('queued','running','cancel_requested')").fetchall()
            same = next((row for row in active if row["kind"] == kind and row["entity_key"] == entity_key
                         and row["owner_id"] == owner_id), None)
            if same:
                return dict(operation_id=same["operation_id"],status=same["status"],message=same["message"])
            if len(active) >= 16:
                raise ValueError("后台检查队列已满，请稍后重试")
            identifier = "op_" + uuid4().hex[:16]
            now = datetime.now(timezone.utc).isoformat()
            connection.execute("""INSERT INTO operations(operation_id,kind,entity_key,status,message,result_json,
                               error_json,created_at,updated_at,owner_id) VALUES(?,?,?,?,?,NULL,NULL,?,?,?)""",
                               (identifier,kind,entity_key,"queued","等待后台检查",now,now,owner_id))
            # Register the cancellation token before exposing the committed job.
            event = Event()
            self._events[identifier] = event
        # Carry the request context (identity session, project scope, request id)
        # so the background job re-checks the *current* identity before committing.
        context = contextvars.copy_context()
        self._executor.submit(context.run, self._run, identifier, event, action)
        return dict(operation_id=identifier,status="queued",message="等待后台检查")

    def _run(self, identifier, event, action):
        last_report = 0.0
        def report(message):
            nonlocal last_report
            now = time.monotonic()
            if now - last_report >= 0.5:
                with self.store._connect() as connection:
                    connection.execute("UPDATE operations SET message=?,updated_at=? WHERE operation_id=?",
                                       (message,datetime.now(timezone.utc).isoformat(),identifier))
                last_report = now
        token = current_operation.set(OperationContext(event, report))
        try:
            checkpoint()
            with self.store._connect() as connection:
                connection.execute("UPDATE operations SET status='running' WHERE operation_id=? AND status='queued'", (identifier,))
            value = action()
            result = value.model_dump(mode="json") if hasattr(value, "model_dump") else value
            # Mutating services check cancellation immediately before their commit.
            # After that commit, report success even if a late cancel arrives.
            self._finish(identifier,"succeeded","检查完成",result=result)
        except OperationCancelled as exc:
            self._finish(identifier,"cancelled",str(exc))
        except Exception as exc:
            error = {"message":str(exc)}
            if hasattr(exc, "current"):
                error["current"] = exc.current.model_dump(mode="json")
            self._finish(identifier,"failed",str(exc),error=error)
        finally:
            current_operation.reset(token)
            self._events.pop(identifier,None)

    def _finish(self, identifier, status, message, *, result=None, error=None):
        with self.store._connect() as connection:
            connection.execute("""UPDATE operations SET status=?,message=?,result_json=?,error_json=?,updated_at=?
                WHERE operation_id=?""", (status,message,json.dumps(result,ensure_ascii=False),
                json.dumps(error,ensure_ascii=False),datetime.now(timezone.utc).isoformat(),identifier))

    def cancel(self, identifier, *, owner_id=None):
        with self._lock:
            record = self.get(identifier, owner_id=owner_id)
            if record["status"] in {"queued","running","cancel_requested"}:
                event = self._events.get(identifier)
                if event:
                    event.set()
                with self.store._connect() as connection:
                    connection.execute("""UPDATE operations SET status='cancel_requested',
                        message='正在取消，等待当前检查退出' WHERE operation_id=? AND status IN ('queued','running')""",(identifier,))
        return self.get(identifier, owner_id=owner_id)

    def shutdown(self, *, wait=False):
        for event in list(self._events.values()):
            event.set()
        self._executor.shutdown(wait=wait,cancel_futures=True)
