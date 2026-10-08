from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class GrantScope(str, Enum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class DirectoryGrant:
    user_id: str
    project_id: str
    root: Path
    scope: GrantScope
    revision: int = 0


@dataclass(frozen=True)
class FileProposal:
    proposal_id: str
    initiator_id: str
    project_id: str
    action: str
    path: Path
    grant_revision: int
    file_revision: int
    resource_id: str | None = None


class FilesystemAuthorizationError(PermissionError):
    pass


class FilesystemAuthorizer:
    """Scope checks for registered directories and human-confirmed mutations.

    The account/membership provider is deliberately injected by the caller.
    This class never trusts a browser-supplied user id or role.
    """

    def __init__(
        self,
        grants: list[DirectoryGrant] | None = None,
        *,
        grant_provider: Callable[[str, str, Path, GrantScope], DirectoryGrant | None] | None = None,
    ):
        self._grants = tuple(grants or ())
        self._grant_provider = grant_provider

    def _grant(self, user_id: str, project_id: str, path: Path, scope: GrantScope):
        path = path.resolve()
        if self._grant_provider is not None:
            current = self._grant_provider(user_id, project_id, path, scope)
            if current is not None:
                return current

        matches = [
            g for g in self._grants
            if (
                g.user_id == user_id
                and g.project_id == project_id
                and g.scope is scope
                and (path == g.root.resolve() or g.root.resolve() in path.parents)
            )
        ]
        if not matches:
            raise FilesystemAuthorizationError("directory_grant_required")
        return max(matches, key=lambda g: len(g.root.parts))

    def require_read(self, user_id: str, project_id: str, path: Path):
        return self._grant(user_id, project_id, path, GrantScope.READ)

    def require_write(self, user_id: str, project_id: str, path: Path):
        return self._grant(user_id, project_id, path, GrantScope.WRITE)

    @staticmethod
    def ensure_no_parent_child_overlap(existing_roots: list[Path], candidate: Path):
        candidate = candidate.resolve()
        for root in existing_roots:
            root = root.resolve()
            if candidate == root or candidate in root.parents or root in candidate.parents:
                raise FilesystemAuthorizationError(
                    "directory_registration_overlaps_existing_scope"
                )

    @staticmethod
    def require_proposal_initiator(
        proposal: FileProposal,
        current_user_id: str,
        current_project_id: str,
        grant_revision: int,
        file_revision: int,
        *,
        resource_authorized: bool = True,
    ):
        if proposal.initiator_id != current_user_id:
            raise FilesystemAuthorizationError("proposal_initiator_required")
        if proposal.project_id != current_project_id:
            raise FilesystemAuthorizationError("wrong_project")
        if proposal.grant_revision != grant_revision:
            raise FilesystemAuthorizationError("grant_revoked_or_changed")
        if proposal.file_revision != file_revision:
            raise FilesystemAuthorizationError("file_changed_since_proposal")
        if not resource_authorized:
            raise FilesystemAuthorizationError("resource_access_revoked")
