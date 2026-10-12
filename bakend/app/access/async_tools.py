from __future__ import annotations

from dataclasses import dataclass

from .contracts import IdentityReader, ResourceRef


class BackgroundAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class PendingOperation:
    operation_id: str
    user_id: str
    project_id: str
    permission_revision: int
    resource_id: str | None = None


class BackgroundOperationGuard:
    """Re-check identity, membership and target permission at execution time."""

    def __init__(self, identity_reader: IdentityReader):
        self.identity_reader = identity_reader

    def require_current(
        self,
        operation: PendingOperation,
        *,
        resource: ResourceRef | None = None,
        resource_authorized: bool | None = None,
    ) -> None:
        identity = self.identity_reader.current_identity()
        if not identity.enabled or identity.user_id != operation.user_id:
            raise BackgroundAuthorizationError("stale_or_revoked_identity")
        membership = self.identity_reader.project_membership(operation.project_id)
        if (
            membership is None
            or not membership.active
            or membership.project_id != operation.project_id
            or membership.user_id != identity.user_id
        ):
            raise BackgroundAuthorizationError("membership_revoked")

        # An explicit denial is authoritative even when the caller omitted
        # the resource object; omission must never turn a denial into approval.
        if resource_authorized is False:
            raise BackgroundAuthorizationError("resource_access_revoked")

        if operation.resource_id is not None:
            if resource is None:
                raise BackgroundAuthorizationError("resource_context_required")
            if resource.resource_id != operation.resource_id:
                raise BackgroundAuthorizationError("resource_target_mismatch")
            if resource.owner.project_id != operation.project_id:
                raise BackgroundAuthorizationError("wrong_project")
            if resource.owner.permission_revision != operation.permission_revision:
                raise BackgroundAuthorizationError("resource_permission_revoked")
            if resource_authorized is not True:
                raise BackgroundAuthorizationError("resource_access_revoked")
        elif resource is not None and resource_authorized is not True:
            raise BackgroundAuthorizationError("resource_access_revoked")

    @staticmethod
    def recipient_may_receive(*, current_user_id: str, recipient_id: str) -> None:
        if current_user_id != recipient_id:
            raise BackgroundAuthorizationError("recipient_authorization_failed")
