from dataclasses import dataclass

import pytest

from app.access.async_tools import (
    BackgroundAuthorizationError, BackgroundOperationGuard, PendingOperation,
)
from app.access.contracts import Identity, ProjectMembership, ProjectRole


@dataclass
class Reader:
    identity: Identity
    member: bool = True

    def current_identity(self):
        return self.identity

    def project_membership(self, project_id):
        if not self.member:
            return None
        return ProjectMembership(project_id, self.identity.user_id, ProjectRole.MEMBER)


def test_background_operation_rechecks_current_identity():
    guard = BackgroundOperationGuard(Reader(Identity("u1")))
    guard.require_current(PendingOperation("op1", "u1", "p1", 1))


def test_account_switch_cannot_execute_old_operation():
    guard = BackgroundOperationGuard(Reader(Identity("u2")))
    with pytest.raises(BackgroundAuthorizationError, match="stale_or_revoked_identity"):
        guard.require_current(PendingOperation("op1", "u1", "p1", 1))


def test_revoked_membership_blocks_pending_operation():
    guard = BackgroundOperationGuard(Reader(Identity("u1"), member=False))
    with pytest.raises(BackgroundAuthorizationError, match="membership_revoked"):
        guard.require_current(PendingOperation("op1", "u1", "p1", 1))
