import sqlite3

from app.access.resource_store import (
    ResourceScope, SQLiteResourcePolicyStore, StoredResourcePolicy,
)


def connect_factory():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE resource_policies (
        resource_type TEXT NOT NULL, resource_id TEXT NOT NULL,
        creator_id TEXT NOT NULL, manager_id TEXT NOT NULL, project_id TEXT,
        scope TEXT NOT NULL, permission_revision INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(resource_type, resource_id))""")
    return db


def test_resource_policy_round_trip():
    db = connect_factory()
    try:
        store = SQLiteResourcePolicyStore(lambda: _ctx(db))
        store.put_policy(StoredResourcePolicy(
            "conversation", "c1", "u1", "u1", "p1", ResourceScope.PRIVATE, 2
        ))
        policy = store.get_policy("conversation", "c1")
        assert policy is not None
        assert policy.creator_id == "u1"
        assert policy.permission_revision == 2
    finally:
        db.close()


class _ctx:
    def __init__(self, db):
        self.db = db
    def __enter__(self):
        return self.db
    def __exit__(self, *_):
        self.db.commit()
