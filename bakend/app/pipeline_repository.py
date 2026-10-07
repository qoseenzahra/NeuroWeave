"""Immutable pipeline versions and publication state, guarded by the store transaction lock."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from uuid import uuid4


class PipelineDeletedError(ValueError):
    pass


class PipelineRepository:
    def __init__(self, store, registry, compiler):
        self.store, self.registry, self.compiler = store, registry, compiler
        with store.transaction() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS pipeline_library (id TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id, version))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS pipeline_drafts(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS pipeline_draft_trash(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL, deleted_at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS pipeline_states(id TEXT NOT NULL, version INTEGER NOT NULL, status TEXT NOT NULL, PRIMARY KEY(id,version))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS pipeline_deletions(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, latest_version INTEGER NOT NULL, deleted_at TEXT)"
            )

    @staticmethod
    def require_active(db, identity):
        row = db.execute("SELECT deleted_at FROM pipeline_deletions WHERE id=?", (identity,)).fetchone()
        if row and row[0] is not None:
            raise PipelineDeletedError("Pipeline 已删除，请先恢复，或创建独立副本。")

    def records(self):
        with self.store.connection() as db:
            return [
                {**json.loads(row["payload"]), "status": row["status"] or "published",
                 "deletion_revision": row["deletion_revision"]}
                for row in db.execute(
                    "SELECT p.payload,s.status,COALESCE(d.revision,0) AS deletion_revision FROM pipeline_library p LEFT JOIN pipeline_states s ON p.id=s.id AND p.version=s.version LEFT JOIN pipeline_deletions d ON p.id=d.id WHERE d.deleted_at IS NULL ORDER BY p.id,p.version"
                )
            ]

    def get(self, identity, version=None):
        self.registry.definitions.load()
        if identity in self.registry.definitions.pipelines:
            return copy.deepcopy(self.registry.definitions.pipelines[identity])
        with self.store.connection() as db:
            deletion = db.execute("SELECT revision,deleted_at FROM pipeline_deletions WHERE id=?", (identity,)).fetchone()
            if deletion and deletion["deleted_at"] is not None:
                raise KeyError("Pipeline 已删除，请从已删除 Pipeline 中恢复。")
            row = db.execute(
                "SELECT payload FROM pipeline_library WHERE id=? AND (? IS NULL OR version=?) ORDER BY version DESC LIMIT 1",
                (identity, version, version),
            ).fetchone()
        if row is None:
            raise KeyError("Pipeline 不存在")
        result = json.loads(row[0])
        with self.store.connection() as db:
            state = db.execute(
                "SELECT status FROM pipeline_states WHERE id=? AND version=?",
                (identity, int(result["version"])),
            ).fetchone()
        return {**result, "status": state[0] if state else "published",
                "deletion_revision": deletion["revision"] if deletion else 0}

    def trash(self):
        with self.store.connection() as db:
            rows = db.execute(
                "SELECT d.*,p.payload,(SELECT COUNT(*) FROM pipeline_library v WHERE v.id=d.id) AS version_count FROM pipeline_deletions d JOIN pipeline_library p ON p.id=d.id AND p.version=d.latest_version WHERE d.deleted_at IS NOT NULL ORDER BY d.deleted_at DESC LIMIT 100"
            ).fetchall()
        return [dict(id=r["id"], label=json.loads(r["payload"])["label"],
                     version=str(r["latest_version"]), version_count=r["version_count"],
                     deletion_revision=r["revision"], deleted_at=r["deleted_at"]) for r in rows]

    def delete(self, identity, expected_version, expected_deletion_revision):
        if not identity.startswith("user-"):
            raise ValueError("内置 Pipeline 只读，不能删除。")
        with self.store.transaction() as db:
            latest = db.execute("SELECT MAX(version) FROM pipeline_library WHERE id=?", (identity,)).fetchone()[0]
            if latest is None:
                raise KeyError("Pipeline 不存在")
            if latest != expected_version:
                raise ValueError("Pipeline 已发布新版本，请刷新到最新版本后再删除。")
            row = db.execute("SELECT revision,deleted_at FROM pipeline_deletions WHERE id=?", (identity,)).fetchone()
            current = row["revision"] if row else 0
            if row and row["deleted_at"] is not None and current == expected_deletion_revision + 1:
                return dict(id=identity, deleted=True, deletion_revision=current)
            if current != expected_deletion_revision or (row and row["deleted_at"] is not None):
                raise ValueError("Pipeline 删除状态已变化，请刷新后再操作。")
            revision = current + 1
            db.execute("INSERT INTO pipeline_deletions VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,latest_version=excluded.latest_version,deleted_at=excluded.deleted_at",
                       (identity, revision, latest, datetime.now(timezone.utc).isoformat()))
        return dict(id=identity, deleted=True, deletion_revision=revision)

    def restore(self, identity, expected_deletion_revision):
        with self.store.transaction() as db:
            row = db.execute("SELECT revision,deleted_at FROM pipeline_deletions WHERE id=?", (identity,)).fetchone()
            if not row or row["deleted_at"] is None:
                raise KeyError("已删除 Pipeline 不存在")
            if row["revision"] != expected_deletion_revision:
                raise ValueError("Pipeline 删除状态已变化，请刷新后再恢复。")
            revision = row["revision"] + 1
            db.execute("UPDATE pipeline_deletions SET revision=?,deleted_at=NULL WHERE id=?", (revision, identity))
        return dict(id=identity, restored=True, deletion_revision=revision)

    def save(self, request, identity=None):
        self.registry.definitions.load()
        if identity in self.registry.definitions.pipelines:
            raise ValueError("内置 Pipeline 只读，请创建独立副本后编辑")
        with self.store.transaction() as db:
            if identity is None:
                identity = "user-" + uuid4().hex[:16]
                version = 1
            else:
                self.require_active(db, identity)
                row = db.execute(
                    "SELECT MAX(version) FROM pipeline_library WHERE id=?", (identity,)
                ).fetchone()
                if row[0] is None:
                    raise KeyError("只能更新用户 Pipeline")
                if row[0] != request.expected_version:
                    raise ValueError("Pipeline 版本已变化，请刷新后保存")
                version = row[0] + 1
            p = self.compiler.compile(request, identity, version)
            db.execute(
                "INSERT INTO pipeline_library VALUES (?,?,?)",
                (identity, version, json.dumps(p, ensure_ascii=False)),
            )
            return p
