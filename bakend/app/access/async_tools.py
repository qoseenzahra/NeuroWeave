from __future__ import annotations

from dataclasses import dataclass

from .contracts import IdentityReader


class BackgroundAuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class PendingOperation:
    operation_id: str
    user_id: str
    project_id: str
    permission_revision: int


class BackgroundOperationGuard:
    """Re-checks identity at execution time; queued work never trusts stale UI state."""

    def __init__(self, identity_reader: IdentityReader):
        self.identity_reader = identity_reader

    def require_current(self, operation: PendingOperation) -> None:
        identity = self.identity_reader.current_identity()
        if not identity.enabled or identity.user_id != operation.user_id:
            raise BackgroundAuthorizationError("stale_or_revoked_identity")

        membership = self.identity_reader.project_membership(operation.project_id)
        if membership is None or not membership.active:
            raise BackgroundAuthorizationError("membership_revoked")

    @staticmethod
    def recipient_may_receive(*, current_user_id: str, recipient_id: str) -> None:
        if current_user_id != recipient_id:
            raise BackgroundAuthorizationError("recipient_authorization_failed")
