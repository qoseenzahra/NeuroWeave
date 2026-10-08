import pytest

from app.access.contracts import ProjectRole
from app.access.execution import (
    ExecutionAuthorizationError, ExecutionAuthorizer, ExecutionRequest,
)


def request(user="u1", units=2):
    return ExecutionRequest(
        submitter_id=user,
        project_id="p1",
        input_resource_ids=("dataset-1",),
        output_resource_id="output-1",
        permission_revision=4,
        execution_units=units,
        max_execution_units=4,
    )


def test_submission_freezes_authorization_scope():
    grant = ExecutionAuthorizer.authorize_submission(
        request(), current_user_id="u1", current_project_id="p1",
        role=ProjectRole.MEMBER, can_read_inputs=True, can_write_output=True,
        reserved_units=0, quota_units=4,
    )
    assert grant.submitter_id == "u1"
    assert grant.permission_revision == 4
    assert grant.execution_units == 2


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"current_user_id": "u2"}, "submitter_identity_mismatch"),
        ({"current_project_id": "p2"}, "wrong_project"),
        ({"can_read_inputs": False}, "input_access_denied"),
        ({"can_write_output": False}, "output_write_denied"),
        ({"reserved_units": 3}, "concurrency_quota_exceeded"),
    ],
)
def test_submission_rechecks_identity_scope_and_quota(kwargs, expected):
    base = dict(
        current_user_id="u1", current_project_id="p1",
        role=ProjectRole.MEMBER, can_read_inputs=True, can_write_output=True,
        reserved_units=0, quota_units=4,
    )
    base.update(kwargs)
    with pytest.raises(ExecutionAuthorizationError, match=expected):
        ExecutionAuthorizer.authorize_submission(request(), **base)


def test_member_cannot_cancel_another_users_execution():
    grant = ExecutionAuthorizer.authorize_submission(
        request(), current_user_id="u1", current_project_id="p1",
        role=ProjectRole.MEMBER, can_read_inputs=True, can_write_output=True,
        reserved_units=0, quota_units=4,
    )
    with pytest.raises(ExecutionAuthorizationError, match="task_management_denied"):
        ExecutionAuthorizer.require_retry_or_cancel(
            current_user_id="u2", grant=grant,
            role=ProjectRole.MEMBER, action="cancel",
        )


def test_project_admin_can_manage_another_users_execution():
    grant = ExecutionAuthorizer.authorize_submission(
        request(), current_user_id="u1", current_project_id="p1",
        role=ProjectRole.MEMBER, can_read_inputs=True, can_write_output=True,
        reserved_units=0, quota_units=4,
    )
    ExecutionAuthorizer.require_retry_or_cancel(
        current_user_id="u2", grant=grant,
        role=ProjectRole.ADMINISTRATOR, action="cancel",
    )
