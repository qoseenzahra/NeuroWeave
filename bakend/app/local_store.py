from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .conversation_models import (
    ConversationListItem,
    ConversationMessageRecord,
    ConversationRecord,
)
from .dataset_models import DatasetRecord
from .run_models import WorkflowRun
from .run_store import RunStoreMixin
from .workflow_models import Workflow


class LocalStore(RunStoreMixin):
    """Durable local SQLite storage for datasets, workflows and workflow events."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                archived INTEGER NOT NULL DEFAULT 0,
                summary TEXT NOT NULL DEFAULT '',
                summary_version INTEGER NOT NULL DEFAULT 0,
                summarized_through_sequence INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS conversation_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                estimated_tokens INTEGER NOT NULL,
                metadata_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(conversation_id, sequence),
                FOREIGN KEY(conversation_id) REFERENCES conversations(conversation_id)
                    ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_updated_at
            ON conversations(updated_at DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS datasets (
                dataset_id TEXT PRIMARY KEY,
                root_id TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                display_name TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_datasets_root_path
            ON datasets(root_id, relative_path)
            """,
            """
            CREATE TABLE IF NOT EXISTS workflows (
                workflow_id TEXT PRIMARY KEY,
                dataset_id TEXT,
                status TEXT NOT NULL,
                revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(dataset_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workflows_dataset_updated
            ON workflows(dataset_id, updated_at DESC)
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                revision INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow_revision
            ON workflow_events(workflow_id, revision)
            """,
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                workflow_id TEXT NOT NULL,
                workflow_revision INTEGER NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id)
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_runs_workflow_updated
            ON runs(workflow_id, updated_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_runs_active_status
            ON runs(status, updated_at DESC)
            WHERE status IN ('queued', 'running', 'cancel_requested')
            """,
            """
            CREATE TABLE IF NOT EXISTS run_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                level TEXT NOT NULL,
                message TEXT NOT NULL,
                progress REAL,
                step_id TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_run_events_run_event
            ON run_events(run_id, event_id)
            """,
        ]
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            for statement in statements:
                connection.execute(statement)
            conversation_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(conversations)").fetchall()
            }
            if "archived" not in conversation_columns:
                connection.execute(
                    "ALTER TABLE conversations ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
                )
            if "workspace_id" not in conversation_columns:
                connection.execute("ALTER TABLE conversations ADD COLUMN workspace_id TEXT")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_archived_updated_id "
                "ON conversations(archived, updated_at DESC, conversation_id DESC)"
            )
            run_columns = {row["name"] for row in connection.execute("PRAGMA table_info(runs)")}
            for name in ("storage_version", "state_revision"):
                if name not in run_columns:
                    connection.execute(f"ALTER TABLE runs ADD COLUMN {name} INTEGER NOT NULL DEFAULT 0")
            connection.execute("""CREATE TABLE IF NOT EXISTS run_plans (
                run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE, payload_json TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS run_steps (
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, step_id TEXT NOT NULL,
                position INTEGER NOT NULL, payload_json TEXT NOT NULL, state_revision INTEGER NOT NULL,
                PRIMARY KEY(run_id,step_id))""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_run_steps_revision ON run_steps(run_id,state_revision)")
            connection.execute("""CREATE TABLE IF NOT EXISTS run_artifact_order (
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                artifact_id TEXT NOT NULL, position INTEGER NOT NULL,
                PRIMARY KEY(run_id,artifact_id))""")
            connection.execute("""CREATE TABLE IF NOT EXISTS execution_drafts (
                workflow_id TEXT PRIMARY KEY REFERENCES workflows(workflow_id) ON DELETE CASCADE,
                workflow_revision INTEGER NOT NULL, draft_revision INTEGER NOT NULL,
                payload_json TEXT NOT NULL, updated_at TEXT NOT NULL)""")
            connection.execute("PRAGMA optimize")

    def create_conversation(self, conversation: ConversationRecord) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations (
                    conversation_id, title, workspace_id, summary, summary_version,
                    summarized_through_sequence, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation.conversation_id,
                    conversation.title,
                    conversation.workspace_id,
                    conversation.summary,
                    conversation.summary_version,
                    conversation.summarized_through_sequence,
                    conversation.created_at,
                    conversation.updated_at,
                ),
            )

    def execution_draft(self, workflow_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM execution_drafts WHERE workflow_id=?", (workflow_id,)).fetchone()
            if row:
                return dict(execution=json.loads(row["payload_json"]), draft_revision=row["draft_revision"],
                            workflow_revision=row["workflow_revision"])
        latest = self.list_runs(workflow_id=workflow_id, limit=1, summary=True)
        return dict(execution=latest[0].get("execution") if latest else None, draft_revision=0,
                    workflow_revision=latest[0]["workflow_revision"] if latest else None)

    def save_execution_draft(self, workflow_id, workflow_revision, draft_revision, execution):
        with self._lock, self._connect() as connection:
            workflow = connection.execute("SELECT revision FROM workflows WHERE workflow_id=?", (workflow_id,)).fetchone()
            if workflow is None:
                raise KeyError(workflow_id)
            if workflow["revision"] != workflow_revision:
                raise ValueError("流程已更新，请重新载入后保存运行设置")
            current = connection.execute("SELECT draft_revision FROM execution_drafts WHERE workflow_id=?", (workflow_id,)).fetchone()
            if (current["draft_revision"] if current else 0) != draft_revision:
                raise ValueError("运行设置已在其他页面更新，请重新载入后修改")
            connection.execute("""INSERT INTO execution_drafts VALUES(?,?,?,?,?)
                ON CONFLICT(workflow_id) DO UPDATE SET workflow_revision=excluded.workflow_revision,
                draft_revision=excluded.draft_revision,payload_json=excluded.payload_json,updated_at=excluded.updated_at""",
                (workflow_id,workflow_revision,draft_revision+1,execution.model_dump_json(),datetime.now(timezone.utc).isoformat()))
        return dict(execution=execution.model_dump(mode="json"),draft_revision=draft_revision+1,workflow_revision=workflow_revision)

    def get_conversation(self, conversation_id: str | None) -> ConversationRecord | None:
        if not conversation_id:
            return None
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT conversation_id, title, archived, workspace_id, summary, summary_version,
                       summarized_through_sequence, created_at, updated_at
                FROM conversations
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            ).fetchone()
        return ConversationRecord.model_validate(dict(row)) if row else None

    def list_conversations(
        self,
        limit: int = 100,
        *,
        query: str = "",
        archived: bool = False,
        before_updated_at: str | None = None,
        before_conversation_id: str | None = None,
    ) -> list[ConversationListItem]:
        safe_limit = max(1, min(limit, 200))
        normalized_query = query.strip()
        search_pattern = f"%{normalized_query}%"
        cursor_filter = ""
        parameters: list[Any] = [int(archived)]
        if before_updated_at is not None and before_conversation_id is not None:
            cursor_filter = "AND (c.updated_at, c.conversation_id) < (?, ?)"
            parameters.extend((before_updated_at, before_conversation_id))
        parameters.extend((normalized_query, search_pattern, search_pattern, safe_limit))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    c.conversation_id,
                    c.workspace_id,
                    c.title,
                    c.archived,
                    c.created_at,
                    c.updated_at,
                    (
                        SELECT COUNT(*)
                        FROM conversation_messages AS counted
                        WHERE counted.conversation_id = c.conversation_id
                    ) AS message_count,
                    COALESCE(
                        (
                            SELECT REPLACE(REPLACE(SUBSTR(latest.content, 1, 160), CHAR(13), ' '), CHAR(10), ' ')
                            FROM conversation_messages AS latest
                            WHERE latest.conversation_id = c.conversation_id
                            ORDER BY latest.sequence DESC
                            LIMIT 1
                        ),
                        ''
                    ) AS last_message_preview,
                    (
                        SELECT latest.role
                        FROM conversation_messages AS latest
                        WHERE latest.conversation_id = c.conversation_id
                        ORDER BY latest.sequence DESC
                        LIMIT 1
                    ) AS last_message_role
                FROM conversations AS c
                WHERE c.archived = ?
                  {cursor_filter}
                  AND (
                    ? = ''
                    OR c.title LIKE ?
                    OR EXISTS (
                        SELECT 1
                        FROM conversation_messages AS searched
                        WHERE searched.conversation_id = c.conversation_id
                          AND searched.content LIKE ?
                    )
                  )
                ORDER BY c.updated_at DESC, c.conversation_id DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [ConversationListItem.model_validate(dict(row)) for row in rows]

    def delete_archived_conversation(self, conversation_id: str) -> bool:
        # Check and delete within the same write transaction. Message rows are
        # removed by ON DELETE CASCADE; workflows, runs and files remain intact.
        with self._lock, self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT archived FROM conversations WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                return False
            if not row["archived"]:
                raise ValueError("只能永久删除已归档的对话")
            connection.execute(
                "DELETE FROM conversations WHERE conversation_id = ? AND archived = 1",
                (conversation_id,),
            )
            return True

    def update_conversation(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        archived: bool | None = None,
        updated_at: str,
    ) -> ConversationRecord | None:
        assignments: list[str] = []
        parameters: list[Any] = []
        if title is not None:
            assignments.append("title = ?")
            parameters.append(title)
        if archived is not None:
            assignments.append("archived = ?")
            parameters.append(int(archived))
        if not assignments:
            return self.get_conversation(conversation_id)

        assignments.append("updated_at = ?")
        parameters.extend((updated_at, conversation_id))
        with self._lock, self._connect() as connection:
            cursor = connection.execute(
                f"UPDATE conversations SET {', '.join(assignments)} WHERE conversation_id = ?",
                parameters,
            )
        if cursor.rowcount == 0:
            return None
        return self.get_conversation(conversation_id)

    def append_conversation_message(
        self,
        conversation_id: str,
        *,
        role: str,
        content: str,
        estimated_tokens: int,
        metadata: dict[str, Any],
        created_at: str,
    ) -> ConversationMessageRecord:
        with self._lock, self._connect() as connection:
            sequence = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1
                    FROM conversation_messages
                    WHERE conversation_id = ?
                    """,
                    (conversation_id,),
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO conversation_messages (
                    conversation_id, sequence, role, content,
                    estimated_tokens, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id,
                    sequence,
                    role,
                    content,
                    estimated_tokens,
                    json.dumps(metadata, ensure_ascii=False),
                    created_at,
                ),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE conversation_id = ?",
                (created_at, conversation_id),
            )
            message_id = int(cursor.lastrowid)
        return ConversationMessageRecord(
            message_id=message_id,
            conversation_id=conversation_id,
            sequence=sequence,
            role=role,
            content=content,
            estimated_tokens=estimated_tokens,
            metadata=metadata,
            created_at=created_at,
        )

    def conversation_messages(
        self,
        conversation_id: str,
        *,
        after_sequence: int = 0,
        limit: int | None = None,
        before_sequence: int | None = None,
        newest_first: bool = False,
    ) -> list[ConversationMessageRecord]:
        query = """
            SELECT message_id, conversation_id, sequence, role, content,
                   estimated_tokens, metadata_json, created_at
            FROM conversation_messages
            WHERE conversation_id = ? AND sequence > ?
        """
        parameters: list[Any] = [conversation_id, after_sequence]
        if before_sequence is not None:
            query += " AND sequence < ?"
            parameters.append(before_sequence)
        query += " ORDER BY sequence " + ("DESC" if newest_first else "ASC")
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(max(1, min(limit, 500)))
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [
            ConversationMessageRecord(
                message_id=row["message_id"],
                conversation_id=row["conversation_id"],
                sequence=row["sequence"],
                role=row["role"],
                content=row["content"],
                estimated_tokens=row["estimated_tokens"],
                metadata=json.loads(row["metadata_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def conversation_context(self, conversation_id):
        result = {}
        with self._connect() as connection:
            for key in ("workflow_id", "dataset_id", "interaction_mode", "selected_skills"):
                # Ordinary assistant replies store workflow_id=null; they do not
                # unlock or clear an earlier workflow. Dataset null is explicit.
                condition = "= 'text'" if key == "workflow_id" else "IS NOT NULL"
                row = connection.execute(f"""SELECT metadata_json FROM conversation_messages
                    WHERE conversation_id=? AND json_type(metadata_json, ?) {condition}
                    ORDER BY sequence DESC LIMIT 1""", (conversation_id, "$."+key)).fetchone()
                if row:
                    result[key] = json.loads(row["metadata_json"])[key]
        return result

    def update_conversation_summary(
        self,
        conversation_id: str,
        *,
        summary: str,
        summary_version: int,
        summarized_through_sequence: int,
        updated_at: str,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET summary = ?,
                    summary_version = ?,
                    summarized_through_sequence = ?,
                    updated_at = ?
                WHERE conversation_id = ?
                """,
                (
                    summary,
                    summary_version,
                    summarized_through_sequence,
                    updated_at,
                    conversation_id,
                ),
            )

    def save_dataset(self, dataset: DatasetRecord) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO datasets (
                    dataset_id, root_id, relative_path, display_name,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    dataset.dataset_id,
                    dataset.root_id,
                    dataset.relative_path,
                    dataset.display_name,
                    dataset.model_dump_json(),
                    dataset.created_at,
                    dataset.updated_at,
                ),
            )

    def find_dataset_by_path(self, root_id: str, relative_path: str) -> DatasetRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM datasets WHERE root_id = ? AND relative_path = ?",
                (root_id, relative_path),
            ).fetchone()
        return DatasetRecord.model_validate_json(row["payload_json"]) if row else None

    def get_dataset(self, dataset_id: str) -> DatasetRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM datasets WHERE dataset_id = ?",
                (dataset_id,),
            ).fetchone()
        return DatasetRecord.model_validate_json(row["payload_json"]) if row else None

    def list_datasets(self) -> list[DatasetRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM datasets ORDER BY updated_at DESC"
            ).fetchall()
        return [DatasetRecord.model_validate_json(row["payload_json"]) for row in rows]

    def save_workflow(
        self,
        workflow: Workflow,
        *,
        event_type: str,
        event_payload: dict[str, Any] | None = None,
    ) -> None:
        payload_json = workflow.model_dump_json()
        created_at = workflow.created_at
        updated_at = workflow.updated_at
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflows (
                    workflow_id, dataset_id, status, revision,
                    payload_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id) DO UPDATE SET
                    dataset_id = excluded.dataset_id,
                    status = excluded.status,
                    revision = excluded.revision,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    workflow.workflow_id,
                    workflow.dataset_id,
                    workflow.status,
                    workflow.revision,
                    payload_json,
                    created_at,
                    updated_at,
                ),
            )
            connection.execute(
                """
                INSERT INTO workflow_events (
                    workflow_id, revision, event_type, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    workflow.workflow_id,
                    workflow.revision,
                    event_type,
                    json.dumps(event_payload or {}, ensure_ascii=False),
                    updated_at,
                ),
            )

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM workflows WHERE workflow_id = ?",
                (workflow_id,),
            ).fetchone()
        return Workflow.model_validate_json(row["payload_json"]) if row else None

    def list_workflows(self, limit: int = 50) -> list[Workflow]:
        safe_limit = max(1, min(limit, 200))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload_json FROM workflows ORDER BY updated_at DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [Workflow.model_validate_json(row["payload_json"]) for row in rows]

    def workflow_events(self, workflow_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT revision, event_type, payload_json, created_at
                FROM workflow_events
                WHERE workflow_id = ?
                ORDER BY event_id ASC
                """,
                (workflow_id,),
            ).fetchall()
        return [
            {
                "revision": row["revision"],
                "event_type": row["event_type"],
                "payload": json.loads(row["payload_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def append_run_event(
        self,
        run_id: str,
        *,
        event_type: str,
        message: str,
        level: str = "info",
        progress: float | None = None,
        step_id: str | None = None,
        payload: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO run_events (
                    run_id, event_type, level, message, progress,
                    step_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    event_type,
                    level,
                    message,
                    progress,
                    step_id,
                    json.dumps(payload or {}, ensure_ascii=False),
                    created_at or datetime.now(timezone.utc).isoformat(),
                ),
            )

    def fail_incomplete_runs(
        self,
        updated_at: str,
        error_code: str,
        error_message: str,
        *,
        preserve_slurm: bool = False,
    ) -> int:
        runs = self.incomplete_runs()
        if preserve_slurm:
            runs = [run for run in runs if run.execution.backend != "slurm"]
        for run in runs:
            run.status = "failed"
            run.error_code = error_code
            run.error_message = error_message
            run.finished_at = updated_at
            run.updated_at = updated_at
            for step in run.steps:
                if step.status in {"queued", "running"}:
                    step.status = "failed"
                    step.error_code = error_code
                    step.error_message = error_message
                    step.finished_at = updated_at
            self.save_run(
                run,
                event_type="run_recovered_as_failed",
                event_message=error_message,
                level="error",
            )
        return len(runs)
