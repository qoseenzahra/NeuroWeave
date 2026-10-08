from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .contracts import ProjectRole


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


class ExecutionAuthorizer:
    """Checks a new submission and freezes the accepted authorization scope.

    Accepted grants are intentionally independent of browser/login lifetime:
    logout or later membership changes must not silently mutate an accepted
    execution plan. New submissions/retries must be checked again.
    """

    @staticmethod
    def authorize_submission(
        request: ExecutionRequest,
        *,
        current_user_id: str,
        current_project_id: str,
        role: ProjectRole,
        can_read_inputs: bool,
        can_write_output: bool,
        reserved_units: int,
        quota_units: int,
    ) -> FrozenExecutionGrant:
        if current_user_id != request.submitter_id:
            raise ExecutionAuthorizationError("submitter_identity_mismatch")
        if current_project_id != request.project_id:
            raise ExecutionAuthorizationError("wrong_project")
        if role not in {ProjectRole.ADMINISTRATOR, ProjectRole.MEMBER}:
            raise ExecutionAuthorizationError("invalid_project_role")
        if not can_read_inputs:
            raise ExecutionAuthorizationError("input_access_denied")
        if not can_write_output:
            raise ExecutionAuthorizationError("output_write_denied")
        if request.execution_units <= 0:
            raise ExecutionAuthorizationError("invalid_execution_units")
        if request.execution_units > request.max_execution_units:
            raise ExecutionAuthorizationError("per_execution_limit_exceeded")
        if reserved_units + request.execution_units > quota_units:
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
        grant: FrozenExecutionGrant,
        role: ProjectRole,
        action: str,
    ) -> None:
        if current_user_id != grant.submitter_id and role is not ProjectRole.ADMINISTRATOR:
            raise ExecutionAuthorizationError("task_management_denied")
        if action not in {"retry", "cancel"}:
            raise ExecutionAuthorizationError("unsupported_execution_action")
