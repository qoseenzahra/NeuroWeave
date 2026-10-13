"""Task B review round: revocation, disabled accounts, dependencies, Task A
contract, execution hardening. Drives the real application with the shared
test identity double; production assembly has no identity bypass."""

from __future__ import annotations

import threading
import pytest

from app.access.contracts import AuthorizationDenied
from app.access.directory_grants import DirectoryGrantStore
from app.access.request_context import request_scope
from identity_factories import ADMIN, grant
from test_task_b_integration import PROJECT, as_user, register_output, save_task, world  # noqa: F401


def _register_dataset(world, user, project=None):
    client = as_user(world, user)
    headers = {PROJECT: project} if project else {}
    root_id = client.get("/api/datasets/roots", headers=headers).json()["roots"][0]["root_id"]
    created = client.post("/api/datasets/register", headers=headers,
                          json={"root_id": root_id, "relative_path": "study-a"})
    assert created.status_code == 200, created.text
    return created.json()["dataset_id"]


def _share(world, user, rtype, rid, project, scope="project"):
    revision = world.services.resource_access.policy(rtype, rid).permission_revision
    return as_user(world, user).post(
        f"/api/access/resources/{rtype}/{rid}/share", headers={PROJECT: project},
        json={"scope": scope, "expected_revision": revision},
    )


# ------------------------------------------------------------ 1. revocation
def test_revoked_read_grant_blocks_dataset_file_access(world):
    created = grant(world.services, world.data, "read", user_id="alice")
    dataset_id = _register_dataset(world, "alice")
    alice = as_user(world, "alice")
    assert alice.get(f"/api/datasets/{dataset_id}/files/list").status_code == 200
    DirectoryGrantStore(world.services.local_store).revoke(created["grant_id"])
    # Ownership alone is not enough: the live directory grant is required.
    assert alice.get(f"/api/datasets/{dataset_id}/files/list").status_code in {403, 404}


def test_revoked_write_grant_blocks_output_file_reads(world):
    created = grant(world.services, world.out / "alice", "write", user_id="alice")
    alice = as_user(world, "alice")
    workspace = alice.post("/api/output-directories",
                           json={"name": "alice output", "root_path": str(world.out / "alice")}).json()
    params = {"workspace_id": workspace["id"], "path": "report.txt"}
    assert alice.get("/api/fs/read-text", params=params).status_code == 200
    DirectoryGrantStore(world.services.local_store).revoke(created["grant_id"])
    # The registered output record alone no longer gives file access.
    assert alice.get("/api/fs/read-text", params=params).status_code in {403, 404}
    assert alice.get("/api/fs/list", params={"workspace_id": workspace["id"]}).status_code in {403, 404}


# ------------------------------------------- 2. disabled accounts / background
def test_background_guard_rejects_disabled_or_switched_actor(world):
    as_user(world, "alice")
    guard = world.services.resource_access.background_guard()
    guard()
    world.reader.become("alice", enabled=False)
    with pytest.raises(AuthorizationDenied):
        guard()
    world.reader.become("bob")
    with pytest.raises(AuthorizationDenied):
        guard()


def test_operation_fails_closed_when_permission_is_lost(world):
    from app.operation_context import checkpoint

    as_user(world, "alice")
    allowed = {"value": True}

    def authorize():
        if not allowed["value"]:
            raise AuthorizationDenied("account_disabled")

    gate = threading.Event()

    def action():
        gate.wait(5)
        checkpoint(commit=True)
        return {"committed": True}

    job = world.services.operation_service.submit("t", "k2", action, owner_id="alice", authorize=authorize)
    allowed["value"] = False
    gate.set()
    for _ in range(300):
        record = world.services.operation_service.get(job["operation_id"])
        if record["status"] not in {"queued", "running"}:
            break
        threading.Event().wait(0.02)
    assert record["status"] == "failed"
    assert record["error"]["code"] == "permission_revoked"
    assert record["result"] is None


# --------------------------------------------------------- 3. dependencies
def test_sharing_a_task_requires_its_real_dataset_to_be_shared(world):
    grant(world.services, world.data, "read", user_id="alice", project_id="p1")
    dataset_id = _register_dataset(world, "alice", project="p1")
    save_task(world, "alice", "wf_real_dep", project="p1", dataset_id=dataset_id)
    refused = _share(world, "alice", "task", "wf_real_dep", "p1")
    assert refused.status_code == 409 and "dependency_not_shared:dataset" in refused.text
    assert _share(world, "alice", "dataset", dataset_id, "p1").status_code == 200
    assert _share(world, "alice", "task", "wf_real_dep", "p1").status_code == 200
    # Unsharing the dataset while a shared task uses it is refused.
    unshare = _share(world, "alice", "dataset", dataset_id, "p1", scope="private")
    assert unshare.status_code == 409 and "resource_in_use_by_shared" in unshare.text


def test_handover_requires_recipient_access_to_dependencies(world):
    grant(world.services, world.data, "read", user_id="alice", project_id="p1")
    dataset_id = _register_dataset(world, "alice", project="p1")
    save_task(world, "alice", "wf_handover_dep", project="p1", dataset_id=dataset_id)
    revision = world.services.resource_access.policy("task", "wf_handover_dep").permission_revision
    refused = as_user(world, "alice").post(
        "/api/access/resources/task/wf_handover_dep/handover", headers={PROJECT: "p1"},
        json={"new_manager_id": "bob", "expected_revision": revision},
    )
    assert refused.status_code == 409 and "dependency_not_accessible_to_recipient" in refused.text


# ------------------------------------------------- 4. Task A contract shapes
def test_contract_identity_reader_maps_task_a_types():
    from app.access.identity_adapter import ContractIdentityReader
    from app.identity.contracts import (
        AccountStatus, ActorContext, PlatformRole, ProjectAccess, ProjectRole, ProjectState,
    )

    class Reader:
        def current_actor(self, *, connection=None):
            return ActorContext("u1", PlatformRole.ADMIN, AccountStatus.ACTIVE, identity_revision=7)

        def project_access(self, project_id, *, connection=None):
            return ProjectAccess(project_id, "u1", ProjectRole.MANAGER, ProjectState.ARCHIVED, 3, 4)

        def project_access_for(self, user_id, project_id, *, connection=None):
            return None

    adapter = ContractIdentityReader(Reader())
    identity = adapter.current_identity()
    assert identity.user_id == "u1" and identity.enabled and identity.identity_revision == 7
    membership = adapter.project_membership("p9")
    assert membership.archived and membership.membership_revision == 3
    assert membership.role is ProjectRole.MANAGER
    assert adapter.membership_of("someone", "p9") is None


def test_archived_project_is_read_only(world):
    save_task(world, "alice", "wf_archived", project="p1")
    world.reader.add_member("alice", "p1", ADMIN, archived=True)
    alice = as_user(world, "alice")
    headers = {PROJECT: "p1"}
    assert alice.get("/api/workflows/wf_archived", headers=headers).status_code == 200
    locked = alice.post("/api/workflows/wf_archived/lock", json={"expected_revision": 1}, headers=headers)
    assert locked.status_code == 403
    with request_scope(project_id="p1"):
        with pytest.raises(AuthorizationDenied):
            world.services.resource_access.require_writable_project()


def test_project_administrator_needs_a_reason_to_manage_member_work(world):
    save_task(world, "bob", "wf_bob_shared", project="p1")
    assert _share(world, "bob", "task", "wf_bob_shared", "p1").status_code == 200
    alice = as_user(world, "alice")
    headers = {PROJECT: "p1"}
    denied = alice.post("/api/workflows/wf_bob_shared/lock", json={"expected_revision": 1}, headers=headers)
    assert denied.status_code == 403 and "administrative_reason_required" in denied.text
    allowed = alice.post("/api/workflows/wf_bob_shared/lock", json={"expected_revision": 1},
                         headers={**headers, "X-NeuroWeave-Reason": "member%20on%20leave"})
    assert allowed.status_code != 403, allowed.text
    events = world.services.business_audit.events("task", "wf_bob_shared")
    assert any(e["event"] == "resource.administrative_action" for e in events)


# ------------------------------------------------------------ 6. execution
def test_quota_time_limit_and_partitions_are_enforced(world):
    from app.access.execution_control import QuotaExceeded, QuotaPolicy
    from app.run_models import RunExecutionOptions

    control = world.services.execution_control
    control.set_quota("user:alice", QuotaPolicy(4, 8, 32, 0, None, 30, ("short",)), updated_by="admin")
    assert control.quota_for("user:alice").as_dict()["allowed_partitions"] == ["short"]
    args = dict(workflow_id="wf", submitter_id="alice", project_id=None, frozen_scope={})
    with pytest.raises(QuotaExceeded, match="time_limit"):
        control.reserve(idempotency_key="a", execution=RunExecutionOptions(time_minutes=60), **args)
    with pytest.raises(QuotaExceeded, match="partition"):
        control.reserve(idempotency_key="b", execution=RunExecutionOptions(
            backend="slurm", partition="long", time_minutes=10), **args)
    ok = control.reserve(idempotency_key="c", execution=RunExecutionOptions(time_minutes=10), **args)
    assert ok["replayed"] is False


def test_reservation_revalidates_identity_inside_the_transaction(world):
    from app.run_models import RunExecutionOptions

    control = world.services.execution_control

    def verify(connection):
        assert connection.in_transaction
        raise AuthorizationDenied("account_disabled_or_changed")

    with pytest.raises(AuthorizationDenied):
        control.reserve(workflow_id="wf", submitter_id="alice", project_id=None, idempotency_key="v",
                        execution=RunExecutionOptions(), frozen_scope={}, verify=verify)
    assert control.existing("alice", "v") is None
    assert control.usage(submitter_id="alice") == 0


def test_worker_refuses_runs_without_a_matching_frozen_grant(world):
    from app.run_models import RunExecutionOptions, WorkflowRun

    control = world.services.execution_control
    run = WorkflowRun(run_id="run_x", workflow_id="wf", workflow_revision=2, status="queued",
                      output_directory="/tmp/x", created_at="2026", updated_at="2026",
                      execution=RunExecutionOptions())
    with pytest.raises(AuthorizationDenied, match="execution_grant_missing"):
        control.require_launchable(run)
    reservation = control.reserve(workflow_id="wf", submitter_id="alice", project_id=None, idempotency_key="w",
                                  execution=RunExecutionOptions(),
                                  frozen_scope={"workflow_id": "wf", "workflow_revision": 1})
    control.bind_run(reservation["reservation_id"], "run_x")
    with pytest.raises(AuthorizationDenied, match="does_not_cover_plan"):
        control.require_launchable(run)
    with pytest.raises(AuthorizationDenied):
        control.bind_run(reservation["reservation_id"], "run_other")
    assert world.services.run_service.launch_guard == control.require_launchable
