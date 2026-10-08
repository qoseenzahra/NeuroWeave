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
        if membership is None or not membership.active:
            raise BackgroundAuthorizationError("membership_revoked")
        if resource is not None:
            if resource.owner.permission_revision != operation.permission_revision:
                raise BackgroundAuthorizationError("resource_permission_revoked")
            if resource_authorized is False:
                raise BackgroundAuthorizationError("resource_access_revoked")

    @staticmethod
    def recipient_may_receive(*, current_user_id: str, recipient_id: str) -> None:
        if current_user_id != recipient_id:
            raise BackgroundAuthorizationError("recipient_authorization_failed")
