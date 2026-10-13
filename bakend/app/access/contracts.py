from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, FrozenSet


# Roles are Task A's fixed enums (identity/contracts.py); B never defines
# its own role table. ``ProjectRole.ADMINISTRATOR`` is an alias of MANAGER.
from ..identity.contracts import PlatformRole, ProjectRole  # noqa: E402,F401


class ResourceType(str, Enum):
    CONVERSATION = "conversation"
    MESSAGE = "message"
    DATASET = "dataset"
    OUTPUT = "output"
    TASK = "task"
    RUN = "run"
    PIPELINE = "pipeline"
    PIPELINE_VERSION = "pipeline_version"
    HISTORICAL_RESULT = "historical_result"
    FILE = "file"
    DIRECTORY = "directory"
    PIPELINE_DRAFT = "pipeline_draft"
    OPERATION = "operation"


class ResourceAction(str, Enum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RESTORE = "restore"
    PUBLISH = "publish"
    SHARE = "share"
    HANDOVER = "handover"
    TAKEOVER = "takeover"
    SUBMIT = "submit"
    RETRY = "retry"
    CANCEL = "cancel"
    CONFIRM = "confirm"
    EXPORT = "export"


class SharingScope(str, Enum):
    PRIVATE = "private"
    PROJECT = "project"


@dataclass(frozen=True)
class Identity:
    """Trusted backend identity supplied by A's authentication component.

    ``platform_role`` is a compatible extension: it defaults to a standard user,
    and a platform role alone never grants access to private resources.
    """

    user_id: str
    enabled: bool = True
    platform_role: PlatformRole = PlatformRole.USER
    identity_revision: int = 0

    @property
    def authenticated(self) -> bool:
        return self.enabled and bool(self.user_id)


@dataclass(frozen=True)
class ProjectMembership:
    project_id: str
    user_id: str
    role: ProjectRole
    active: bool = True
    # Archived projects allow historical viewing only (requirements §6.1).
    archived: bool = False
    membership_revision: int = 0
    project_revision: int = 0


@dataclass(frozen=True)
class ResourceOwner:
    creator_id: str
    manager_id: str
    project_id: str | None
    scope: SharingScope
    permission_revision: int = 0


@dataclass(frozen=True)
class ResourceRef:
    resource_type: ResourceType
    resource_id: str
    owner: ResourceOwner


@dataclass(frozen=True)
class AuthorizationContext:
    identity: Identity
    membership: ProjectMembership | None
    resource: ResourceRef | None = None


class IdentityReader(Protocol):
    def current_identity(self) -> Identity: ...
    def project_membership(self, project_id: str) -> ProjectMembership | None: ...


class MembershipDirectory(Protocol):
    """Optional A-side lookup used only by handover to validate the recipient."""

    def membership_of(self, user_id: str, project_id: str) -> ProjectMembership | None: ...


class AuditSink(Protocol):
    def record(
        self, event: str, *, user_id: str, project_id: str | None,
        resource_type: str, resource_id: str | None,
        action: str, reason: str | None = None
    ) -> None: ...


@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    allowed_actions: FrozenSet[ResourceAction] = frozenset()


class AuthorizationDenied(PermissionError):
    pass


class ResourceNotFound(KeyError):
    """Raised for missing *and* invisible resources so existence is not leaked."""
