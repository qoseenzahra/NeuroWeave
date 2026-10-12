"""Durable directory policies: personal/project data roots and output write grants.

A grant gives one user (or every active member of a project, ``user_id='*'``)
read or write access below one physical directory. Grants are looked up live on
every check; revocation increments the revision so pending proposals made under
the old grant can no longer be confirmed. Nothing is inherited from the old
global filesystem roots: a newly registered user without grants sees nothing.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .contracts import AuthorizationDenied, PlatformRole, ProjectRole
from .filesystem import DirectoryGrant, FilesystemAuthorizationError, FilesystemAuthorizer, GrantScope

PERSONAL = ""
ALL_MEMBERS = "*"

SCHEMA = """
CREATE TABLE IF NOT EXISTS directory_grants (
    grant_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    project_id TEXT NOT NULL DEFAULT '',
    root TEXT NOT NULL,
    scope TEXT NOT NULL CHECK(scope IN ('read','write')),
    revision INTEGER NOT NULL DEFAULT 1,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_directory_grants_subject
    ON directory_grants(project_id, user_id, revoked);
"""


def initialize_grant_schema(connection) -> None:
    connection.executescript(SCHEMA)


def _within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


class DirectoryGrantStore:
    def __init__(self, store):
        self.store = store

    @staticmethod
    def _row(row) -> DirectoryGrant:
        return DirectoryGrant(
            user_id=row["user_id"], project_id=row["project_id"], root=Path(row["root"]),
            scope=GrantScope(row["scope"]), revision=row["revision"],
        )

    def grants_for(self, user_id: str, project_id: str) -> list[tuple[str, DirectoryGrant]]:
        with self.store._connect() as db:
            rows = db.execute(
                "SELECT * FROM directory_grants WHERE revoked=0 AND project_id=? AND user_id IN (?,?)",
                (project_id, user_id, ALL_MEMBERS if project_id else user_id),
            ).fetchall()
        result = []
        for row in rows:
            grant = self._row(row)
            # A project-wide grant is materialized for the current member only.
            result.append((row["grant_id"], DirectoryGrant(
                user_id=user_id, project_id=grant.project_id, root=grant.root,
                scope=grant.scope, revision=grant.revision,
            )))
        return result

    def match(self, user_id: str, project_id: str, path: Path, scope: GrantScope) -> tuple[str, DirectoryGrant] | None:
        path = Path(path).resolve()
        candidates = [
            (grant_id, grant) for grant_id, grant in self.grants_for(user_id, project_id)
            if _within(path, grant.root.resolve())
            and (grant.scope is scope or (scope is GrantScope.READ and grant.scope is GrantScope.WRITE))
        ]
        if not candidates:
            return None
        # Most specific grant wins; a write grant satisfies a read requirement.
        return max(candidates, key=lambda item: (len(item[1].root.parts), item[1].scope is scope))

    def provider(self, user_id: str, project_id: str, path: Path, scope: GrantScope) -> DirectoryGrant | None:
        found = self.match(user_id, project_id, path, scope)
        if found is None:
            return None
        grant = found[1]
        # Report the requested scope so FilesystemAuthorizer's live check accepts
        # a write grant where only read access is required.
        return DirectoryGrant(grant.user_id, grant.project_id, grant.root, scope, grant.revision)

    def get(self, grant_id: str) -> dict | None:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM directory_grants WHERE grant_id=?", (grant_id,)).fetchone()
        return dict(row) if row else None

    def list(self, project_id: str, user_id: str | None = None) -> list[dict]:
        sql = "SELECT * FROM directory_grants WHERE project_id=?"
        params: tuple = (project_id,)
        if user_id is not None:
            sql += " AND user_id=?"
            params += (user_id,)
        with self.store._connect() as db:
            return [dict(row) for row in db.execute(sql + " ORDER BY root", params)]

    def create(self, *, user_id: str, project_id: str, root: Path, scope: GrantScope, created_by: str) -> dict:
        root = Path(root).resolve()
        if not root.is_absolute() or not root.is_dir():
            raise ValueError("grant_root_must_be_existing_directory")
        now = datetime.now(timezone.utc).isoformat()
        grant_id = "grant_" + uuid4().hex[:16]
        with self.store._lock, self.store._connect() as db:
            duplicate = db.execute(
                "SELECT grant_id FROM directory_grants WHERE revoked=0 AND user_id=? AND project_id=? AND root=? AND scope=?",
                (user_id, project_id, str(root), scope.value),
            ).fetchone()
            if duplicate:
                raise ValueError("grant_already_exists")
            db.execute(
                "INSERT INTO directory_grants VALUES(?,?,?,?,?,1,0,?,?,?)",
                (grant_id, user_id, project_id, str(root), scope.value, created_by, now, now),
            )
        return self.get(grant_id) or {}

    def revoke(self, grant_id: str) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        with self.store._lock, self.store._connect() as db:
            if db.execute(
                "UPDATE directory_grants SET revoked=1, revision=revision+1, updated_at=? WHERE grant_id=? AND revoked=0",
                (now, grant_id),
            ).rowcount != 1:
                raise KeyError(grant_id)
        return self.get(grant_id) or {}


class DirectoryAccess:
    """Business-facing filesystem scope for the current request."""

    def __init__(self, grants: DirectoryGrantStore, resources):
        self.grants = grants
        self.resources = resources
        self.authorizer = FilesystemAuthorizer(grant_provider=grants.provider)

    def scope(self) -> tuple[str, str]:
        identity = self.resources.actor()
        return identity.user_id, self.resources.current_project() or PERSONAL

    def require(self, path: Path, scope: GrantScope) -> DirectoryGrant:
        user_id, project_id = self.scope()
        try:
            if scope is GrantScope.WRITE:
                return self.authorizer.require_write(user_id, project_id, Path(path))
            return self.authorizer.require_read(user_id, project_id, Path(path))
        except FilesystemAuthorizationError as exc:
            raise PermissionError(str(exc)) from exc

    def grant_token(self, path: Path, scope: GrantScope) -> dict:
        """Grant identity/revision frozen into proposals and execution scopes."""
        user_id, project_id = self.scope()
        found = self.grants.match(user_id, project_id, Path(path), scope)
        if found is None:
            raise PermissionError("directory_grant_required")
        grant_id, grant = found
        return {"grant_id": grant_id, "revision": grant.revision, "root": str(grant.root), "scope": scope.value}

    def require_token(self, token: dict) -> None:
        """Recheck a frozen grant at confirmation/execution time."""
        record = self.grants.get(str(token.get("grant_id") or ""))
        if record is None or record["revoked"] or record["revision"] != token.get("revision"):
            raise PermissionError("grant_revoked_or_changed")
        user_id, project_id = self.scope()
        if record["project_id"] != project_id or record["user_id"] not in {user_id, ALL_MEMBERS}:
            raise PermissionError("grant_revoked_or_changed")

    def granted_roots(self, scope: GrantScope = GrantScope.READ) -> list[Path]:
        user_id, project_id = self.scope()
        return [
            grant.root.resolve() for _id, grant in self.grants.grants_for(user_id, project_id)
            if grant.scope is scope or (scope is GrantScope.READ and grant.scope is GrantScope.WRITE)
        ]

    def classify(self, path: Path, scope: GrantScope = GrantScope.READ) -> str | None:
        """``granted`` inside a grant, ``ancestor`` on the way to one, else ``None``.

        Ancestors may be browsed only to reach granted subtrees; callers must
        filter their listing with :meth:`leads_to_grant`.
        """
        path = Path(path).resolve()
        roots = self.granted_roots(scope)
        if any(_within(path, root) for root in roots):
            return "granted"
        if any(path in root.parents for root in roots):
            return "ancestor"
        return None

    def leads_to_grant(self, path: Path, scope: GrantScope = GrantScope.READ) -> bool:
        path = Path(path).resolve()
        return any(_within(path, root) or path in root.parents for root in self.granted_roots(scope))

    def visible_roots(self, candidates: list[Path]) -> list[Path]:
        """Configured browse roots reduced to the caller's granted subtrees."""
        user_id, project_id = self.scope()
        granted = [grant.root.resolve() for _id, grant in self.grants.grants_for(user_id, project_id)]
        visible: list[Path] = []
        for root in granted:
            for candidate in candidates:
                candidate = Path(candidate).resolve()
                if _within(root, candidate) and root not in visible:
                    visible.append(root)
        return sorted(visible)

    # ------------------------------------------------------------ administration
    def can_manage(self, project_id: str) -> bool:
        identity = self.resources.actor()
        if identity.platform_role is PlatformRole.ADMIN:
            return True
        if not project_id:
            return False
        membership = self.resources.identity_reader.project_membership(project_id)
        return bool(
            membership and membership.active and membership.project_id == project_id
            and membership.role is ProjectRole.ADMINISTRATOR
        )

    def require_manage(self, project_id: str) -> None:
        if not self.can_manage(project_id):
            raise AuthorizationDenied("directory_policy_management_denied")

    def create_grant(self, *, user_id: str, project_id: str, root: Path, scope: GrantScope) -> dict:
        self.require_manage(project_id)
        identity = self.resources.actor()
        if identity.platform_role is not PlatformRole.ADMIN:
            # Project administrators can only delegate inside a project-wide
            # root that a platform administrator already granted to the project.
            parent = self.grants.match(ALL_MEMBERS, project_id, Path(root), scope)
            if parent is None:
                raise AuthorizationDenied("grant_outside_project_scope")
        record = self.grants.create(
            user_id=user_id or ALL_MEMBERS, project_id=project_id, root=Path(root),
            scope=scope, created_by=identity.user_id,
        )
        self.resources._audit(
            "directory.grant.created", resource_type="directory", resource_id=record.get("grant_id"),
            action="create", reason=f"{scope.value}:{record.get('root')}", project_id=project_id or None,
        )
        return record

    def revoke_grant(self, grant_id: str) -> dict:
        record = self.grants.get(grant_id)
        if record is None:
            raise KeyError(grant_id)
        self.require_manage(record["project_id"])
        revoked = self.grants.revoke(grant_id)
        self.resources._audit(
            "directory.grant.revoked", resource_type="directory", resource_id=grant_id,
            action="delete", reason=f"{record['scope']}:{record['root']}",
            project_id=record["project_id"] or None,
        )
        return revoked
