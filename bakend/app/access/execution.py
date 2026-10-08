from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import Lock

from .contracts import ProjectMembership, ProjectRole


class ExecutionAuthorizationError(PermissionError):
    pass


class ExecutionState(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ExecutionRequest:
    submitter_id: str
    project_id: str
    input_resource_ids: tuple[str, ...]
    output_resource_id: str
    permission_revision: int
    execution_units: int
    max_execution_units: int


@dataclass(frozen=True)
class FrozenExecutionGrant:
    submitter_id: str
    project_id: str
    input_resource_ids: tuple[str, ...]
    output_resource_id: str
    permission_revision: int
    execution_units: int


class ExecutionQuota:
    """Atomic in-process reservation primitive.

    Production should back this protocol with the shared LocalStore transaction;
    this primitive is also useful for deterministic concurrency tests.
    """

    def __init__(self, quota_units: int):
        self.quota_units = quota_units
        self._reserved = 0
        self._lock = Lock()

    @property
    def reserved_units(self) -> int:
        with self._lock:
            return self._reserved

    def try_reserve(self, units: int) -> bool:
        if units <= 0:
            return False
        with self._lock:
            if self._reserved + units > self.quota_units:
                return False
            self._reserved += units
            return True

    def release(self, units: int) -> None:
        with self._lock:
            self._reserved = max(0, self._reserved - max(0, units))


class ExecutionAuthorizer:
    """Validate a submission and freeze the accepted authorization scope."""

    @staticmethod
    def authorize_submission(
        request: ExecutionRequest,
        *,
        current_user_id: str,
        current_project_id: str,
        membership: ProjectMembership | None,
        can_read_inputs: bool,
        can_write_output: bool,
        quota: ExecutionQuota,
    ) -> FrozenExecutionGrant:
        if current_user_id != request.submitter_id:
            raise ExecutionAuthorizationError("submitter_identity_mismatch")
        if current_project_id != request.project_id:
            raise ExecutionAuthorizationError("wrong_project")
        if membership is None or not membership.active:
            raise ExecutionAuthorizationError("project_membership_required")
        if membership.project_id != request.project_id:
            raise ExecutionAuthorizationError("wrong_project")
        if membership.role not in {ProjectRole.ADMINISTRATOR, ProjectRole.MEMBER}:
            raise ExecutionAuthorizationError("invalid_project_role")
        if not can_read_inputs:
            raise ExecutionAuthorizationError("input_access_denied")
        if not can_write_output:
            raise ExecutionAuthorizationError("output_write_denied")
        if request.execution_units <= 0:
            raise ExecutionAuthorizationError("invalid_execution_units")
        if request.execution_units > request.max_execution_units:
            raise ExecutionAuthorizationError("per_execution_limit_exceeded")
        if not quota.try_reserve(request.execution_units):
            raise ExecutionAuthorizationError("concurrency_quota_exceeded")

        return FrozenExecutionGrant(
            submitter_id=request.submitter_id,
            project_id=request.project_id,
            input_resource_ids=request.input_resource_ids,
            output_resource_id=request.output_resource_id,
            permission_revision=request.permission_revision,
            execution_units=request.execution_units,
        )

    @staticmethod
    def require_retry_or_cancel(
        *,
        current_user_id: str,
        current_project_id: str,
        membership: ProjectMembership | None,
        grant: FrozenExecutionGrant,
        action: str,
        target_is_project_shared: bool,
    ) -> None:
        if membership is None or not membership.active or membership.project_id != grant.project_id:
            raise ExecutionAuthorizationError("project_membership_required")
        if action not in {"retry", "cancel"}:
            raise ExecutionAuthorizationError("unsupported_execution_action")
        if current_user_id != grant.submitter_id:
            if membership.role is not ProjectRole.ADMINISTRATOR or not target_is_project_shared:
                raise ExecutionAuthorizationError("task_management_denied")
