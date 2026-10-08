import pytest

from app.access.model_tools import ModelAuthorizationError, ModelCallContext, ModelToolAuthorizer


def ctx():
    return ModelCallContext(
        user_id="u1", project_id="p1",
        resource_ids=("dataset-1",), allow_external_model=True, token_budget=1000,
    )


def test_model_call_requires_current_identity_and_project():
    ModelToolAuthorizer.authorize(
        ctx(), current_user_id="u1", current_project_id="p1",
        resources_authorized=True,
    )


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"current_user_id": "u2"}, "identity_mismatch"),
        ({"current_project_id": "p2"}, "wrong_project"),
        ({"resources_authorized": False}, "resource_access_denied"),
    ],
)
def test_model_call_rejects_invalid_scope(kwargs, expected):
    base = dict(current_user_id="u1", current_project_id="p1", resources_authorized=True)
    base.update(kwargs)
    with pytest.raises(ModelAuthorizationError, match=expected):
        ModelToolAuthorizer.authorize(ctx(), **base)


def test_external_model_policy_must_be_enabled():
    c = ModelCallContext("u1", "p1", ("d1",), False, 100)
    with pytest.raises(ModelAuthorizationError, match="external_model_policy_denied"):
        ModelToolAuthorizer.authorize(
            c, current_user_id="u1", current_project_id="p1",
            resources_authorized=True,
        )


def test_private_result_recipient_is_rechecked():
    with pytest.raises(PermissionError, match="recipient_authorization_failed"):
        ModelToolAuthorizer.require_private_result_recipient(
            current_user_id="u2", recipient_id="u1"
        )
