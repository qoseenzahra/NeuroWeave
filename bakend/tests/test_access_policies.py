from dataclasses import dataclass

import pytest

from app.access.contracts import (
    Identity, ProjectMembership, ProjectRole, ResourceAction, ResourceOwner,
    ResourceRef, ResourceType, SharingScope,
)
from app.access.service import AuthorizationDenied, AuthorizationService


@dataclass
class FakeIdentityReader:
    identity: Identity
    memberships: dict[str, ProjectMembership]

    def current_identity(self):
        return self.identity

    def project_membership(self, project_id):
        return self.memberships.get(project_id)


def ref(scope=SharingScope.PRIVATE, creator="u1", manager="u1", project="p1"):
    return ResourceRef(
        ResourceType.PIPELINE, "r1",
        ResourceOwner(creator, manager, project, scope),
    )


def svc(user, role=ProjectRole.MEMBER, enabled=True):
    return AuthorizationService(FakeIdentityReader(
        Identity(user, enabled),
        {"p1": ProjectMembership("p1", user, role)},
    ))


def test_private_resource_is_invisible_to_other_user():
    with pytest.raises(AuthorizationDenied):
        svc("u2").require(ref(), ResourceAction.READ)


def test_owner_can_update_private_resource():
    svc("u1").require(ref(), ResourceAction.UPDATE)


def test_project_admin_can_manage_project_resource():
    svc("u2", ProjectRole.ADMINISTRATOR).require(
        ref(SharingScope.PROJECT, creator="u1", manager="u1"),
        ResourceAction.UPDATE,
    )


def test_project_member_can_read_shared_resource_but_not_modify():
    service = svc("u2", ProjectRole.MEMBER)
    service.require(
        ref(SharingScope.PROJECT, creator="u1", manager="u1"),
        ResourceAction.READ,
    )
    with pytest.raises(AuthorizationDenied):
        service.require(
            ref(SharingScope.PROJECT, creator="u1", manager="u1"),
            ResourceAction.UPDATE,
        )


def test_wrong_project_is_denied():
    service = AuthorizationService(FakeIdentityReader(
        Identity("u2"),
        {"p2": ProjectMembership("p2", "u2", ProjectRole.ADMINISTRATOR)},
    ))
    with pytest.raises(AuthorizationDenied):
        service.require(
            ref(SharingScope.PROJECT, creator="u1", manager="u1", project="p1"),
            ResourceAction.READ,
        )


def test_disabled_identity_is_denied():
    with pytest.raises(AuthorizationDenied):
        svc("u1", enabled=False).require(ref(), ResourceAction.READ)


def test_filtering_happens_before_count():
    service = svc("u1")
    resources = [
        ref(creator="u1", manager="u1"),
        ref(creator="u2", manager="u2"),
    ]
    visible = service.filter_visible(resources, ResourceAction.READ)
    assert len(visible) == 1


def test_owner_cannot_take_over_own_resource():
    with pytest.raises(AuthorizationDenied):
        svc("u1").require(ref(), ResourceAction.TAKEOVER)


def test_shared_pipeline_member_can_submit_own_task():
    svc("u2").require(
        ref(SharingScope.PROJECT, creator="u1", manager="u1"),
        ResourceAction.SUBMIT,
    )



def test_former_creator_loses_management_rights_after_handover():
    former_creator = svc("u1")
    handed_over = ref(
        SharingScope.PROJECT, creator="u1", manager="u2", project="p1"
    )
    # Historical attribution remains intact, but no longer grants owner powers.
    former_creator.require(handed_over, ResourceAction.READ)
    with pytest.raises(AuthorizationDenied):
        former_creator.require(handed_over, ResourceAction.UPDATE)
    with pytest.raises(AuthorizationDenied):
        former_creator.require(handed_over, ResourceAction.DELETE)
    svc("u2").require(handed_over, ResourceAction.UPDATE)
