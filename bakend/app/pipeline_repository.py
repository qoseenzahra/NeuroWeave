"""Immutable pipeline versions and publication state, guarded by the store transaction lock."""

from __future__ import annotations

import copy
import json
from uuid import uuid4


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

    def records(self):
        with self.store.connection() as db:
            return [
                {**json.loads(row["payload"]), "status": row["status"] or "published"}
                for row in db.execute(
                    "SELECT p.payload,s.status FROM pipeline_library p LEFT JOIN pipeline_states s ON p.id=s.id AND p.version=s.version ORDER BY p.id,p.version"
                )
            ]

    def get(self, identity, version=None):
        self.registry.definitions.load()
        if identity in self.registry.definitions.pipelines:
            return copy.deepcopy(self.registry.definitions.pipelines[identity])
        with self.store.connection() as db:
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
        return {**result, "status": state[0] if state else "published"}

    def save(self, request, identity=None):
        with self.store.transaction() as db:
            if identity is None:
                identity = "user-" + uuid4().hex[:16]
                version = 1
            else:
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
