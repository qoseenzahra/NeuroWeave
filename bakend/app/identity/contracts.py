"""Shared identity, project-access and audit contracts (collaboration agreement §3.1).

Developer A owns this module and its implementation. The types below are the
agreed minimal contract so Task B can consume it; A may extend them
compatibly (new optional fields), never by changing names or meanings.

* ``ActorContext``  - backend-authenticated actor: user id, platform role,
  account status, identity revision and an internal session id. Never a
  password or raw cookie.
* ``ProjectAccess`` - the actor's current relationship to one project: role,
  project state, membership revision and project revision.
* ``IdentityReader`` - validates the current session and reads project access.
  Every call may take ``connection`` so checks can run inside the same SQLite
  transaction as a business mutation (atomic validation).
* ``AuditSink`` / ``AuditEvent`` - common audit, writable inside a business
  transaction.

Fixed enums: platform ``admin | user``; project ``manager | member``
(``manager`` is the Project Administrator UI role); account
``active | disabled``; project ``active | archived``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol


class PlatformRole(str, Enum):
    ADMIN = "admin"
    USER = "user"


class ProjectRole(str, Enum):
    MANAGER = "manager"
    MEMBER = "member"
    # Alias used by Task B code for the "Project Administrator" UI role.
    ADMINISTRATOR = "manager"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class ProjectState(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


@dataclass(frozen=True)
class ActorContext:
    user_id: str
    platform_role: PlatformRole = PlatformRole.USER
    status: AccountStatus = AccountStatus.ACTIVE
    identity_revision: int = 0
    session_id: str = ""

    @property
    def active(self) -> bool:
        return self.status is AccountStatus.ACTIVE and bool(self.user_id)


@dataclass(frozen=True)
class ProjectAccess:
    project_id: str
    user_id: str
    role: ProjectRole
    project_state: ProjectState = ProjectState.ACTIVE
    membership_revision: int = 0
    project_revision: int = 0


class IdentityReader(Protocol):
    """Implemented by A. ``None`` means unauthenticated / no membership."""

    def current_actor(self, *, connection: Any = None) -> ActorContext | None: ...

    def project_access(self, project_id: str, *, connection: Any = None) -> ProjectAccess | None: ...

    def project_access_for(
        self, user_id: str, project_id: str, *, connection: Any = None
    ) -> ProjectAccess | None: ...


@dataclass(frozen=True)
class AuditEvent:
    event_id: str
    timestamp: str
    actor_id: str
    project_id: str | None
    resource_type: str
    resource_id: str | None
    action: str
    outcome: str  # "allowed" | "denied" | "succeeded" | "failed"
    reason: str | None = None
    request_id: str | None = None
    execution_identity: str | None = None
    changes: dict = field(default_factory=dict)


class AuditSink(Protocol):
    def record(self, event: AuditEvent, *, connection: Any = None) -> None: ...
