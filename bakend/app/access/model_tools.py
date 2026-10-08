from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .async_tools import BackgroundAuthorizationError
from .contracts import AuditSink


class ModelAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class ModelCallContext:
    user_id: str
    project_id: str
    resource_ids: tuple[str, ...]
    allow_external_model: bool
    token_budget: int
    request_id: str = ""


class ModelToolAuthorizer:
    """Reauthorize model/tool inputs and private delivery at execution time."""

    @staticmethod
    def authorize(
        context: ModelCallContext,
        *,
        current_user_id: str,
        current_project_id: str,
        resources_authorized: bool | Callable[[str], bool],
        audit: AuditSink | None = None,
    ) -> None:
        if current_user_id != context.user_id:
            raise ModelAuthorizationError("identity_mismatch")
        if current_project_id != context.project_id:
            raise ModelAuthorizationError("wrong_project")
        checker = resources_authorized if callable(resources_authorized) else lambda _id: resources_authorized
        if not all(checker(resource_id) for resource_id in context.resource_ids):
            raise ModelAuthorizationError("resource_access_denied")
        if context.token_budget <= 0:
            raise ModelAuthorizationError("invalid_token_budget")
        if not context.allow_external_model:
            raise ModelAuthorizationError("external_model_policy_denied")
        if audit is not None:
            audit.record(
                "model.call.authorized",
                user_id=current_user_id,
                project_id=current_project_id,
                resource_type="model_call",
                resource_id=context.request_id or None,
                action="execute",
                reason="current_resource_scope",
            )

    @staticmethod
    def require_private_result_recipient(
        *, current_user_id: str, recipient_id: str
    ) -> None:
        if current_user_id != recipient_id:
            raise BackgroundAuthorizationError("recipient_authorization_failed")
