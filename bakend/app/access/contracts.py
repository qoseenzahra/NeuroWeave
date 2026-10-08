from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, FrozenSet


class ProjectRole(str, Enum):
    ADMINISTRATOR = "project_administrator"
    MEMBER = "research_member"


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
    user_id: str
    enabled: bool = True


@dataclass(frozen=True)
class ProjectMembership:
    project_id: str
    user_id: str
    role: ProjectRole
    active: bool = True


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
