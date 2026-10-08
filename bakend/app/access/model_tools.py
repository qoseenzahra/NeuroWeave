from __future__ import annotations

from dataclasses import dataclass

from .async_tools import BackgroundAuthorizationError


class ModelAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class ModelCallContext:
    user_id: str
    project_id: str
    resource_ids: tuple[str, ...]
    allow_external_model: bool
    token_budget: int


class ModelToolAuthorizer:
    """Business guard for model calls; identity and project scope are server-side."""

    @staticmethod
    def authorize(
        context: ModelCallContext,
        *,
        current_user_id: str,
        current_project_id: str,
        resources_authorized: bool,
    ) -> None:
        if current_user_id != context.user_id:
            raise ModelAuthorizationError("identity_mismatch")
        if current_project_id != context.project_id:
            raise ModelAuthorizationError("wrong_project")
        if not resources_authorized:
            raise ModelAuthorizationError("resource_access_denied")
        if context.token_budget <= 0:
            raise ModelAuthorizationError("invalid_token_budget")
        if not context.allow_external_model:
            raise ModelAuthorizationError("external_model_policy_denied")

    @staticmethod
    def require_private_result_recipient(
        *, current_user_id: str, recipient_id: str
    ) -> None:
        if current_user_id != recipient_id:
            raise BackgroundAuthorizationError("recipient_authorization_failed")
