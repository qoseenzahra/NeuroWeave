import threading

import pytest

from app.access.contracts import ProjectMembership, ProjectRole
from app.access.execution import (
    ExecutionAuthorizationError, ExecutionAuthorizer, ExecutionQuota, ExecutionRequest,
)


def request(user="u1", units=2):
    return ExecutionRequest(
        submitter_id=user, project_id="p1",
        input_resource_ids=("dataset-1",), output_resource_id="output-1",
        permission_revision=4, execution_units=units, max_execution_units=4,
    )


def member(user="u1", role=ProjectRole.MEMBER):
    return ProjectMembership("p1", user, role)


def test_submission_freezes_authorization_scope():
    grant = ExecutionAuthorizer.authorize_submission(
        request(), current_user_id="u1", current_project_id="p1",
        membership=member(), can_read_inputs=True, can_write_output=True,
        quota=ExecutionQuota(4),
    )
    assert grant.submitter_id == "u1"
    assert grant.permission_revision == 4
    assert grant.execution_units == 2


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"current_user_id": "u2"}, "submitter_identity_mismatch"),
        ({"current_project_id": "p2"}, "wrong_project"),
        ({"membership": None}, "project_membership_required"),
        ({"can_read_inputs": False}, "input_access_denied"),
        ({"can_write_output": False}, "output_write_denied"),
    ],
)
def test_submission_rechecks_identity_scope(kwargs, expected):
    base = dict(
        current_user_id="u1", current_project_id="p1", membership=member(),
        can_read_inputs=True, can_write_output=True, quota=ExecutionQuota(4),
    )
    base.update(kwargs)
    with pytest.raises(ExecutionAuthorizationError, match=expected):
        ExecutionAuthorizer.authorize_submission(request(), **base)


def test_atomic_quota_reservation_blocks_simultaneous_overrun():
    quota = ExecutionQuota(1)
    results = []

    def submit():
        try:
            ExecutionAuthorizer.authorize_submission(
                request(units=1), current_user_id="u1", current_project_id="p1",
                membership=member(), can_read_inputs=True, can_write_output=True,
                quota=quota,
            )
            results.append("accepted")
        except ExecutionAuthorizationError:
            results.append("rejected")

    threads = [threading.Thread(target=submit) for _ in range(2)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert sorted(results) == ["accepted", "rejected"]


def test_member_cannot_cancel_another_users_execution():
    grant = ExecutionAuthorizer.authorize_submission(
        request(), current_user_id="u1", current_project_id="p1",
        membership=member(), can_read_inputs=True, can_write_output=True,
        quota=ExecutionQuota(4),
    )
    with pytest.raises(ExecutionAuthorizationError, match="task_management_denied"):
        ExecutionAuthorizer.require_retry_or_cancel(
            current_user_id="u2", current_project_id="p1",
            membership=member("u2"), grant=grant, action="cancel",
            target_is_project_shared=False,
        )


def test_project_admin_can_manage_shared_execution():
    grant = ExecutionAuthorizer.authorize_submission(
        request(), current_user_id="u1", current_project_id="p1",
        membership=member(), can_read_inputs=True, can_write_output=True,
        quota=ExecutionQuota(4),
    )
    ExecutionAuthorizer.require_retry_or_cancel(
        current_user_id="u2", current_project_id="p1",
        membership=member("u2", ProjectRole.ADMINISTRATOR),
        grant=grant, action="cancel", target_is_project_shared=True,
    )
