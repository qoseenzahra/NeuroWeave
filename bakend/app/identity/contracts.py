from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from sqlite3 import Connection
from typing import Mapping, Protocol


class PlatformRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class ProjectRole(str, Enum):
    MANAGER = "manager"
    MEMBER = "member"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ProjectStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class ActorContext:
    user_id: str
    platform_role: PlatformRole
    identity_revision: int
    session_id: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.user_id or not self.session_id:
            raise ValueError("User and internal session identifiers are required")
        if not isinstance(self.platform_role, PlatformRole):
            raise ValueError("Invalid platform role")
        if type(self.identity_revision) is not int or self.identity_revision < 0:
            raise ValueError("Identity revision must be nonnegative")


@dataclass(frozen=True)
class ProjectAccess:
    user_id: str
    project_id: str
    project_role: ProjectRole
    project_status: ProjectStatus
    membership_revision: int
    project_revision: int

    def __post_init__(self) -> None:
        if not self.user_id or not self.project_id:
            raise ValueError("User and project identifiers are required")
        if not isinstance(self.project_role, ProjectRole):
            raise ValueError("Invalid project role")
        if not isinstance(self.project_status, ProjectStatus):
            raise ValueError("Invalid project status")
        if any(type(revision) is not int or revision < 0 for revision in (
            self.membership_revision, self.project_revision
        )):
            raise ValueError("Project and membership revisions must be nonnegative")


class IdentityUnavailable(PermissionError):
    """No valid account/session, or a previously trusted identity was revoked."""


class IdentityReader(Protocol):
    def current_identity(self, *, connection: Connection | None = None) -> ActorContext:
        """Validate the request's account/session on every call or raise IdentityUnavailable.

        Disabling, platform-role changes, and session revocation invalidate previous identity
        revisions. Restoration must not reactivate revoked sessions.
        """
        ...

    def revalidate(
        self, actor: ActorContext, *, connection: Connection | None = None
    ) -> ActorContext:
        """Recheck a trusted initiating actor, including session and identity revision.

        Pending background work uses its persisted actor, never a current browser
        user. Accepted run grants have a separate lifetime owned by execution.
        """
        ...

    def project_access(
        self,
        actor: ActorContext,
        project_id: str,
        *,
        connection: Connection | None = None,
    ) -> ProjectAccess | None:
        """Revalidate the actor and read their current relationship; None means no membership.

        Role/removal changes advance membership revisions, including rejoining.
        Project changes advance project revisions. Archival preserves membership
        and historical reads; business policies deny new mutations/submissions.
        Callers compare revisions again inside the mutation's transaction.
        """
        ...


@dataclass(frozen=True)
class UnavailableIdentityReader:
    def current_identity(self, *, connection: Connection | None = None) -> ActorContext:
        raise IdentityUnavailable("Authentication required")

    def revalidate(
        self, actor: ActorContext, *, connection: Connection | None = None
    ) -> ActorContext:
        raise IdentityUnavailable("Authentication required")

    def project_access(
        self,
        actor: ActorContext,
        project_id: str,
        *,
        connection: Connection | None = None,
    ) -> ProjectAccess | None:
        raise IdentityUnavailable("Authentication required")


def unavailable_identity_reader(_request: object) -> IdentityReader:
    return UnavailableIdentityReader()


class TransactionProvider(Protocol):
    def transaction(self) -> AbstractContextManager[Connection]:
        """Share one connection across identity checks, mutation, and success audit.

        Implementations must serialize competing read-check-write operations.
        Readers and sinks using this connection must not commit or close it.
        """
        ...


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    timestamp: datetime
    actor_id: str
    project_id: str | None
    resource_type: str
    resource_id: str | None
    action: str
    outcome: str
    reason: str | None
    request_id: str
    execution_identity: str | None = None
    changes: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)


class AuditSink(Protocol):
    def record(self, event: AuditEvent, *, connection: Connection | None = None) -> None:
        """Persist safe change summaries without credentials, keys, or file contents.

        Success events use the business transaction. Failure events are recorded
        independently after rollback. Async events retain actor and service identity.
        """
        ...
