from dataclasses import dataclass

import pytest

from app.access.async_tools import (
    BackgroundAuthorizationError, BackgroundOperationGuard, PendingOperation,
)
from app.access.contracts import (
    Identity, ProjectMembership, ProjectRole, ResourceOwner, ResourceRef,
    ResourceType, SharingScope,
)


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



def _resource(resource_id="dataset-1"):
    return ResourceRef(
        ResourceType.DATASET,
        resource_id,
        ResourceOwner("u1", "u1", "p1", SharingScope.PROJECT, permission_revision=4),
    )


def test_resource_bound_background_operation_requires_target_and_positive_auth():
    guard = BackgroundOperationGuard(Reader(Identity("u1")))
    operation = PendingOperation("op1", "u1", "p1", 4, resource_id="dataset-1")
    with pytest.raises(BackgroundAuthorizationError, match="resource_context_required"):
        guard.require_current(operation)
    with pytest.raises(BackgroundAuthorizationError, match="resource_access_revoked"):
        guard.require_current(operation, resource=_resource(), resource_authorized=False)
    with pytest.raises(BackgroundAuthorizationError, match="resource_target_mismatch"):
        guard.require_current(operation, resource=_resource("dataset-2"), resource_authorized=True)
    guard.require_current(operation, resource=_resource(), resource_authorized=True)
