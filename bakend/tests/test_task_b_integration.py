"""End-to-end Task B checks through the real application (issues 01–13).

Two users (alice, bob), two projects and both project roles come from the
shared test identity factory; production assembly has no identity bypass.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.access.contracts import PlatformRole
from app.access.directory_grants import ALL_MEMBERS
from app.application import create_app
from app.bootstrap import build_services
from app.models import ChatResponse
from app.settings import Settings
from identity_factories import ADMIN, MEMBER, grant, sign_in

ROOT = Path(__file__).resolve().parents[2]
PROJECT = "X-NeuroWeave-Project"


@pytest.fixture
def world(tmp_path, monkeypatch):
    data = tmp_path / "data"
    (data / "study-a" / "sub-01").mkdir(parents=True)
    (data / "study-a" / "notes.txt").write_text("study notes")
    (data / "study-b").mkdir()
    out = tmp_path / "out"
    (out / "alice").mkdir(parents=True)
    (out / "alice" / "report.txt").write_text("alice private report")
    (out / "alice" / ".env").write_text("SECRET=1")
    (out / "bob").mkdir()
    monkeypatch.setenv("WORKSPACE_ALLOWED_ROOTS", str(tmp_path))
    monkeypatch.setenv("WORKSPACE_DEFAULT_ROOT", str(tmp_path))
    monkeypatch.setenv("LOCALFLOW_DATA_ROOTS", str(data))
    monkeypatch.setenv("LOCALFLOW_EXECUTION_ENABLED", "false")
    monkeypatch.setenv("LOCALFLOW_LLM_BASE_URL", "")
    settings = Settings(ROOT, ROOT / "bakend", ROOT / "skills", tmp_path / "runtime/api.db", tmp_path / "outputs", ())
    services = build_services(settings)
    app = create_app(services)
    reader = sign_in(services, "alice")
    reader.add_member("alice", "p1", ADMIN).add_member("bob", "p1", MEMBER).add_member("bob", "p2", ADMIN)
    with TestClient(app) as client:
        yield type("World", (), dict(
            client=client, services=services, reader=reader, data=data, out=out, tmp=tmp_path,
        ))


def as_user(world, user_id, **kwargs):
    world.reader.become(user_id, **kwargs)
    return world.client


def register_output(world, user, root, project=None):
    grant(world.services, root, "write", user_id=user, project_id=project or "")
    headers = {PROJECT: project} if project else {}
    response = as_user(world, user).post(
        "/api/output-directories", json={"name": f"{user} output", "root_path": str(root)}, headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


# --------------------------------------------------------------------- 01 / 02
def test_anonymous_callers_cannot_read_sensitive_files_or_modify_outputs(world):
    workspace = register_output(world, "alice", world.out / "alice")
    world.reader.sign_out()
    client = world.client
    sensitive = client.post("/api/fs/read-sensitive", json={"workspace_id": workspace["id"], "path": ".env"})
    assert sensitive.status_code == 401
    assert client.post("/api/fs/operations/anything/confirm", json={"confirmed": True}).status_code == 401
    assert client.post("/api/output-directories", json={"name": "x", "root_path": str(world.out)}).status_code == 401
    assert client.post("/api/fs/mkdir", json={"root_path": str(world.out), "path": "new"}).status_code == 401
    assert client.post("/api/fs/delete", json={"workspace_id": workspace["id"], "path": "report.txt"}).status_code == 401
    assert client.get("/api/fs/roots").status_code == 401
    assert (world.out / "alice" / "report.txt").exists()


def test_sensitive_read_proposal_is_bound_to_its_initiator(world):
    workspace = register_output(world, "alice", world.out / "alice")
    alice = as_user(world, "alice")
    proposal = alice.post("/api/fs/read-sensitive", json={"workspace_id": workspace["id"], "path": ".env"})
    assert proposal.status_code == 200, proposal.text
    operation_id = proposal.json()["id"]
    bob = as_user(world, "bob")
    # Bob can neither see nor confirm Alice's proposal, nor reach her output.
    assert bob.get(f"/api/fs/operations/{operation_id}").status_code == 404
    assert bob.post(f"/api/fs/operations/{operation_id}/confirm", json={"confirmed": True}).status_code == 404
    assert bob.get("/api/fs/list", params={"workspace_id": workspace["id"]}).status_code == 404
    assert bob.post("/api/fs/read-sensitive", json={"workspace_id": workspace["id"], "path": ".env"}).status_code == 404
    confirmed = as_user(world, "alice").post(f"/api/fs/operations/{operation_id}/confirm", json={"confirmed": True})
    assert confirmed.status_code == 200
    assert confirmed.json()["result"]["text"] == "SECRET=1"


def test_new_user_without_grants_does_not_inherit_global_roots(world):
    bob = as_user(world, "bob")
    assert bob.get("/api/fs/roots").json()["roots"] == []
    assert bob.get("/api/fs/list", params={"root_path": str(world.tmp)}).status_code == 403
    assert bob.get("/api/datasets/roots").json()["roots"] == []
    denied = bob.post("/api/output-directories", json={"name": "b", "root_path": str(world.out / "bob")})
    assert denied.status_code == 403
    assert bob.post("/api/fs/mkdir", json={"root_path": str(world.out), "path": "x"}).status_code == 403


def test_output_registration_rejects_duplicate_and_nested_directories(world):
    register_output(world, "alice", world.out / "alice")
    grant(world.services, world.out, "write", user_id="bob")
    bob = as_user(world, "bob")
    for root in (world.out / "alice", world.out, world.out / "alice" / "nested"):
        if not root.exists():
            root.mkdir()
        response = bob.post("/api/output-directories", json={"name": "dup", "root_path": str(root)})
        assert response.status_code == 409, (root, response.text)


def test_write_grant_revocation_invalidates_pending_confirmation(world):
    workspace = register_output(world, "alice", world.out / "alice")
    alice = as_user(world, "alice")
    proposal = alice.post("/api/fs/delete", json={"workspace_id": workspace["id"], "path": "report.txt"})
    assert proposal.status_code == 200, proposal.text
    grants = world.services.directory_access.grants.list("", "alice")
    world.services.directory_access.grants.revoke(grants[0]["grant_id"])
    response = alice.post(f"/api/fs/operations/{proposal.json()['id']}/confirm", json={"confirmed": True})
    assert response.status_code == 403
    assert "grant_revoked_or_changed" in response.text
    assert (world.out / "alice" / "report.txt").exists()


def test_disabled_account_cannot_confirm_its_old_proposal(world):
    workspace = register_output(world, "alice", world.out / "alice")
    alice = as_user(world, "alice")
    proposal = alice.post("/api/fs/delete", json={"workspace_id": workspace["id"], "path": "report.txt"})
    world.reader.become("alice", enabled=False)
    response = world.client.post(f"/api/fs/operations/{proposal.json()['id']}/confirm", json={"confirmed": True})
    assert response.status_code == 401
    assert (world.out / "alice" / "report.txt").exists()


def test_project_removal_invalidates_project_proposal(world):
    root = world.out / "bob"
    workspace = register_output(world, "bob", root, project="p1")
    (root / "result.txt").write_text("r")
    bob = as_user(world, "bob")
    proposal = bob.post("/api/fs/delete", json={"workspace_id": workspace["id"], "path": "result.txt"},
                        headers={PROJECT: "p1"})
    assert proposal.status_code == 200, proposal.text
    world.reader.remove_member("bob", "p1")
    response = bob.post(f"/api/fs/operations/{proposal.json()['id']}/confirm", json={"confirmed": True},
                        headers={PROJECT: "p1"})
    assert response.status_code in {403, 404}
    assert (root / "result.txt").exists()


def test_ancestor_browsing_only_reveals_the_path_to_granted_subtrees(world):
    grant(world.services, world.data / "study-a", "read", user_id="bob")
    bob = as_user(world, "bob")
    roots = bob.get("/api/datasets/roots").json()["roots"]
    assert len(roots) == 1
    listing = bob.get("/api/datasets/directories", params={"root_id": roots[0]["root_id"]}).json()
    assert [entry["name"] for entry in listing["directories"]] == ["study-a"]
    assert listing["files"] == []
    inside = bob.get("/api/datasets/directories", params={"root_id": roots[0]["root_id"], "relative_path": "study-a"})
    assert inside.status_code == 200 and inside.json()["files"][0]["name"] == "notes.txt"
    outside = bob.get("/api/datasets/directories", params={"root_id": roots[0]["root_id"], "relative_path": "study-b"})
    assert outside.status_code == 403


# -------------------------------------------------------------------------- 04
def test_private_chat_results_are_not_exposed_or_replayable(world, monkeypatch):
    async def reply(request):
        _, conversation_id = world.services.conversation_service.begin_turn(request)
        return ChatResponse(content="alice private answer", provider_used="t", model_used="t", mode="demo",
                            selected_skills=[], conversation_id=conversation_id)

    monkeypatch.setattr(world.services.chat_turns, "handler", reply)
    alice = as_user(world, "alice")
    body = {"message": "private question", "client_turn_id": "turn_alice_private_0001"}
    answer = alice.post("/api/chat", json=body)
    assert answer.status_code == 200, answer.text
    assert alice.get("/api/chat/turns/turn_alice_private_0001").json()["result"]["content"] == "alice private answer"
    bob = as_user(world, "bob")
    assert bob.get("/api/chat/turns/turn_alice_private_0001").status_code == 404
    replay = bob.post("/api/chat/turns", json=body)
    assert replay.status_code == 409
    assert "alice private answer" not in replay.text
    assert bob.post("/api/chat/turns/turn_alice_private_0001/retry").status_code == 404
    assert bob.post("/api/chat/turns/turn_alice_private_0001/cancel").status_code == 404
    world.reader.sign_out()
    assert world.client.get("/api/chat/turns/turn_alice_private_0001").status_code == 401


def test_tool_events_are_private_to_the_turn_owner(world):
    world.services.workspace_service.event("turn_alice_events_0001", {"tool": "list", "status": "ok"})
    with world.services.local_store._connect() as db:
        db.execute(
            "INSERT INTO chat_turns(id,fingerprint,conversation_id,status,message,request_json,updated_at,owner_id)"
            " VALUES('turn_alice_events_0001','f','c','succeeded','m','{}','now','alice')"
        )
    assert as_user(world, "alice").get("/api/workspace-tool-events", params={"turn_id": "turn_alice_events_0001"}).json()
    assert as_user(world, "bob").get("/api/workspace-tool-events", params={"turn_id": "turn_alice_events_0001"}).json() == []


# -------------------------------------------------------------------------- 05
@pytest.mark.parametrize("method,path", [
    ("get", "/api/datasets"), ("get", "/api/datasets/roots"), ("get", "/api/workflows"),
    ("get", "/api/workflow-index"), ("get", "/api/runs"), ("get", "/api/output-directories"),
    ("get", "/api/library"), ("get", "/api/library/drafts"), ("get", "/api/skills"),
    ("get", "/api/operations/op_1"), ("get", "/api/maintenance/storage"),
    ("post", "/api/workflows/draft"), ("post", "/api/runs/run_1/cancel"),
    ("get", "/api/access/scope"),
])
def test_business_endpoints_reject_anonymous_requests(world, method, path):
    world.reader.sign_out()
    response = getattr(world.client, method)(path, **({"json": {"message": "x"}} if method == "post" else {}))
    assert response.status_code == 401, (path, response.status_code, response.text)


def test_liveness_stays_anonymous(world):
    world.reader.sign_out()
    assert world.client.get("/api/health?include_runtime=false").status_code == 200


def test_datasets_are_private_and_filtered(world):
    grant(world.services, world.data, "read", user_id="alice")
    alice = as_user(world, "alice")
    root_id = alice.get("/api/datasets/roots").json()["roots"][0]["root_id"]
    created = alice.post("/api/datasets/register", json={"root_id": root_id, "relative_path": "study-a"})
    assert created.status_code == 200, created.text
    dataset_id = created.json()["dataset_id"]
    listed = alice.get("/api/datasets").json()["datasets"]
    assert [d["dataset_id"] for d in listed] == [dataset_id]
    assert "update" in listed[0]["allowed_actions"]
    grant(world.services, world.data, "read", user_id="bob")
    bob = as_user(world, "bob")
    assert bob.get("/api/datasets").json()["datasets"] == []
    assert bob.get(f"/api/datasets/{dataset_id}").status_code == 404
    assert bob.get(f"/api/datasets/{dataset_id}/files/list").status_code == 404
    assert bob.post(f"/api/datasets/{dataset_id}/inspect").status_code == 404
    # Re-registering the same physical directory cannot adopt Alice's dataset.
    again = bob.post("/api/datasets/register", json={"root_id": root_id, "relative_path": "study-a"})
    assert again.status_code == 409


def test_operations_belong_to_their_initiator(world):
    grant(world.services, world.data, "read", user_id="alice")
    alice = as_user(world, "alice")
    root_id = alice.get("/api/datasets/roots").json()["roots"][0]["root_id"]
    job = alice.post("/api/datasets/register-jobs", json={"root_id": root_id, "relative_path": "study-a"})
    assert job.status_code == 202, job.text
    operation_id = job.json()["operation_id"]
    for _ in range(200):
        record = alice.get(f"/api/operations/{operation_id}").json()
        if record["status"] not in {"queued", "running"}:
            break
        threading.Event().wait(0.02)
    assert record["status"] == "succeeded", record
    # The background registration ran as Alice and recorded her ownership.
    dataset_id = record["result"]["dataset_id"]
    policy = world.services.resource_access.policy("dataset", dataset_id)
    assert policy.creator_id == "alice"
    assert as_user(world, "bob").get(f"/api/operations/{operation_id}").status_code == 404


def save_task(world, user, workflow_id, project=None, **extra):
    from app.workflow_models import Workflow

    world.reader.become(user)
    from app.access.request_context import request_scope

    workflow = Workflow(
        workflow_id=workflow_id, template_id="t", title=f"task {workflow_id}", summary="", original_request="x",
        status="awaiting_method_choice", steps=[], created_at="2026-10-01T00:00:00+00:00",
        updated_at=extra.pop("updated_at", "2026-10-01T00:00:00+00:00"), **extra,
    )
    with request_scope(project_id=project):
        world.services.local_store.save_workflow(workflow, event_type="workflow_created")
    return workflow


def test_tasks_and_runs_are_isolated(world):
    save_task(world, "alice", "wf_alice")
    alice = as_user(world, "alice")
    assert alice.get("/api/workflows/wf_alice").status_code == 200
    bob = as_user(world, "bob")
    assert bob.get("/api/workflows/wf_alice").status_code == 404
    assert bob.post("/api/workflows/wf_alice/lock", json={"expected_revision": 1}).status_code == 404
    assert bob.get("/api/workflows/wf_alice/execution-draft").status_code == 404
    assert bob.get("/api/workflow-index").json()["items"] == []
    assert bob.get("/api/runs", params={"workflow_id": "wf_alice"}).status_code == 404


# -------------------------------------------------------------------------- 11
def test_authorized_tasks_are_not_truncated_by_pagination(world):
    save_task(world, "alice", "wf_alice_old", updated_at="2020-01-01T00:00:00+00:00")
    for index in range(40):
        save_task(world, "bob", f"wf_bob_{index:02d}", updated_at=f"2026-10-{1 + index % 9:02d}T00:00:00+00:00")
    alice = as_user(world, "alice")
    page = alice.get("/api/workflow-index", params={"limit": 5}).json()
    assert [item["workflow_id"] for item in page["items"]] == ["wf_alice_old"]
    assert page["has_more"] is False
    assert page["items"][0]["allowed_actions"]
    assert [w["workflow_id"] for w in alice.get("/api/workflows", params={"limit": 5}).json()["workflows"]] == ["wf_alice_old"]


def test_my_tasks_and_project_tasks_views(world):
    save_task(world, "alice", "wf_alice_p1", project="p1")
    save_task(world, "bob", "wf_bob_p1", project="p1")
    as_user(world, "bob")
    from app.access.contracts import SharingScope
    from app.access.request_context import request_scope

    with request_scope(project_id="p1"):
        world.services.resource_access.share("task", "wf_bob_p1", SharingScope.PROJECT, expected_revision=0)
    alice = as_user(world, "alice")
    headers = {PROJECT: "p1"}
    project_view = alice.get("/api/workflow-index", params={"view": "project"}, headers=headers).json()["items"]
    assert {item["workflow_id"] for item in project_view} == {"wf_alice_p1", "wf_bob_p1"}
    mine = alice.get("/api/workflow-index", params={"view": "mine"}, headers=headers).json()["items"]
    assert [item["workflow_id"] for item in mine] == ["wf_alice_p1"]
    # Personal scope does not show project tasks.
    assert alice.get("/api/workflow-index").json()["items"] == []


def test_research_member_cannot_manage_another_users_shared_task(world):
    from app.access.contracts import SharingScope
    from app.access.request_context import request_scope

    save_task(world, "alice", "wf_shared", project="p1")
    as_user(world, "alice")
    with request_scope(project_id="p1"):
        world.services.resource_access.share("task", "wf_shared", SharingScope.PROJECT, expected_revision=0)
    bob = as_user(world, "bob")
    headers = {PROJECT: "p1"}
    assert bob.get("/api/workflows/wf_shared", headers=headers).status_code == 200
    assert bob.post("/api/workflows/wf_shared/lock", json={"expected_revision": 1}, headers=headers).status_code == 403
    assert bob.put("/api/workflows/wf_shared/execution-draft", headers=headers, json={
        "expected_revision": 1, "expected_draft_revision": 0, "execution": {}}).status_code == 403
    assert bob.post("/api/workflows/wf_shared/runs", headers=headers, json={"expected_revision": 1}).status_code == 403
    actions = bob.get("/api/access/resources/task/wf_shared", headers=headers).json()["allowed_actions"]
    assert set(actions) == {"read", "export"}


# -------------------------------------------------------------------------- 12
def test_handover_moves_management_and_former_creator_loses_it(world):
    from app.access.request_context import request_scope

    save_task(world, "alice", "wf_handover", project="p1")
    alice = as_user(world, "alice")
    headers = {PROJECT: "p1"}
    handed = alice.post("/api/access/resources/task/wf_handover/handover", headers=headers,
                        json={"new_manager_id": "bob", "expected_revision": 0})
    assert handed.status_code == 200, handed.text
    assert handed.json()["creator_id"] == "alice" and handed.json()["manager_id"] == "bob"
    # Alice (still project administrator, but the task is private) loses access.
    assert alice.post("/api/workflows/wf_handover/lock", json={"expected_revision": 1}, headers=headers).status_code == 404
    with request_scope(project_id="p1"):
        assert world.services.resource_access.allowed_actions("task", "wf_handover") == []
    bob = as_user(world, "bob")
    assert bob.get("/api/workflows/wf_handover", headers=headers).status_code == 200
    stale = bob.post("/api/access/resources/task/wf_handover/share", headers=headers,
                     json={"scope": "project", "expected_revision": 0})
    assert stale.status_code == 409


def test_platform_takeover_requires_admin_reason_and_is_audited(world):
    save_task(world, "alice", "wf_private")
    bob = as_user(world, "bob")
    assert bob.post("/api/access/resources/task/wf_private/takeover",
                    json={"reason": "compliance review", "expected_revision": 0}).status_code == 403
    admin = as_user(world, "root-admin", platform_role=PlatformRole.ADMIN)
    # A platform role alone does not grant read access to a private resource.
    assert admin.get("/api/workflows/wf_private").status_code == 404
    assert admin.post("/api/access/resources/task/wf_private/takeover",
                      json={"reason": "short", "expected_revision": 0}).status_code == 422
    taken = admin.post("/api/access/resources/task/wf_private/takeover",
                       json={"reason": "account closed; data retention", "expected_revision": 0})
    assert taken.status_code == 200 and taken.json()["manager_id"] == "root-admin"
    events = world.services.business_audit.events("task", "wf_private")
    assert any(e["event"] == "resource.takeover" and "retention" in e["reason"] for e in events)


def test_sharing_checks_dependencies(world):
    from app.access.contracts import ResourceType

    save_task(world, "alice", "wf_dep", project="p1")
    world.services.resource_access.dependencies[ResourceType.TASK] = lambda _id: [(ResourceType.DATASET, "ds_private")]
    alice = as_user(world, "alice")
    response = alice.post("/api/access/resources/task/wf_dep/share", headers={PROJECT: "p1"},
                          json={"scope": "project", "expected_revision": 0})
    assert response.status_code == 409 and "dependency_not_shared" in response.text


# -------------------------------------------------------------------------- 09
def test_concurrent_submissions_cannot_exceed_durable_quota(world):
    from app.access.execution_control import ExecutionControl, QuotaExceeded, QuotaPolicy
    from app.run_models import RunExecutionOptions

    control = world.services.execution_control
    control.set_quota("user:alice", QuotaPolicy(2, 8, 32, 0), updated_by="admin")
    # A second control object stands in for a second API process sharing the DB.
    other_process = ExecutionControl(world.services.local_store)
    results, errors = [], []
    barrier = threading.Barrier(6)

    def submit(index):
        barrier.wait()
        try:
            target = control if index % 2 else other_process
            results.append(target.reserve(
                workflow_id=f"wf_{index}", submitter_id="alice", project_id=None,
                idempotency_key=f"k{index}", execution=RunExecutionOptions(), frozen_scope={},
            ))
        except QuotaExceeded as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=submit, args=(i,)) for i in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(results) == 2 and len(errors) == 4
    assert control.usage(submitter_id="alice") == 2


def test_multi_sample_units_and_per_unit_limits(world):
    from app.access.execution_control import QuotaExceeded, QuotaPolicy, execution_units
    from app.run_models import RunExecutionOptions

    options = RunExecutionOptions(backend="slurm", sample_mode="per_sample", nodes=[
        {"node": "n1", "parallel_samples": 3, "cpus": 2}, {"node": "n2", "parallel_samples": 2, "cpus": 2},
    ])
    assert len(execution_units(options)) == 5
    control = world.services.execution_control
    control.set_quota("user:bob", QuotaPolicy(4, 8, 32, 0), updated_by="admin")
    with pytest.raises(QuotaExceeded, match="user_concurrency_quota_exceeded"):
        control.reserve(workflow_id="wf", submitter_id="bob", project_id=None, idempotency_key="a",
                        execution=options, frozen_scope={})
    big = RunExecutionOptions(cpus=16)
    with pytest.raises(QuotaExceeded, match="per_unit_cpu"):
        control.reserve(workflow_id="wf", submitter_id="bob", project_id=None, idempotency_key="b",
                        execution=big, frozen_scope={})


def test_idempotent_reservation_and_release_on_terminal_run(world):
    from app.run_models import RunExecutionOptions, WorkflowRun

    save_task(world, "alice", "wf_i")
    control = world.services.execution_control
    first = control.reserve(workflow_id="wf_i", submitter_id="alice", project_id=None, idempotency_key="same",
                            execution=RunExecutionOptions(), frozen_scope={"workflow_id": "wf_i"})
    again = control.reserve(workflow_id="wf_i", submitter_id="alice", project_id=None, idempotency_key="same",
                            execution=RunExecutionOptions(), frozen_scope={})
    assert again["replayed"] and again["reservation_id"] == first["reservation_id"]
    assert control.usage(submitter_id="alice") == 1
    run = WorkflowRun(run_id="run_i", workflow_id="wf_i", workflow_revision=1, status="succeeded",
                      output_directory="/tmp/x", created_at="2026", updated_at="2026")
    world.services.local_store.save_run(run)
    control.bind_run(first["reservation_id"], "run_i")
    assert control.usage(submitter_id="alice") == 0


def test_run_submission_freezes_scope_and_blocks_other_users(world, monkeypatch):
    from app.run_models import WorkflowRun

    workspace = register_output(world, "alice", world.out / "alice")
    save_task(world, "alice", "wf_run", workspace_id=workspace["id"],
              workspace_root_path=workspace["root_path"])
    created = {}

    def fake_create(workflow_id, expected_revision, execution, *, on_created=None):
        run = WorkflowRun(run_id="run_frozen", workflow_id=workflow_id, workflow_revision=1, status="queued",
                          output_directory=str(world.out / "alice" / "outputs"), created_at="2026", updated_at="2026",
                          execution=execution)
        world.services.local_store.save_run(run)
        # The real service binds the grant before starting the worker.
        on_created(run.run_id)
        created["bound_before_start"] = world.services.execution_control.for_run(run.run_id) is not None
        created["run"] = run
        return run

    monkeypatch.setattr(world.services.run_service, "create", fake_create)
    alice = as_user(world, "alice")
    headers = {"Idempotency-Key": "submit-once"}
    response = alice.post("/api/workflows/wf_run/runs", json={"expected_revision": 1}, headers=headers)
    assert response.status_code == 200, response.text
    assert created["bound_before_start"]
    replay = alice.post("/api/workflows/wf_run/runs", json={"expected_revision": 1}, headers=headers)
    assert replay.status_code == 200 and replay.json()["run_id"] == "run_frozen"
    record = alice.get("/api/runs/run_frozen/authorization").json()
    assert record["submitter_id"] == "alice"
    assert record["frozen_scope"]["output_workspace_id"] == workspace["id"]
    assert record["frozen_scope"]["output_grant"]["scope"] == "write"
    assert record["units"] == 1
    bob = as_user(world, "bob")
    assert bob.get("/api/runs/run_frozen").status_code == 404
    assert bob.post("/api/runs/run_frozen/cancel").status_code == 404
    assert bob.post("/api/runs/run_frozen/retry", json={}).status_code == 404


def test_submission_requires_output_write_grant(world, monkeypatch):
    workspace = register_output(world, "alice", world.out / "alice")
    save_task(world, "alice", "wf_nogrant", workspace_id=workspace["id"], workspace_root_path=workspace["root_path"])
    for item in world.services.directory_access.grants.list("", "alice"):
        world.services.directory_access.grants.revoke(item["grant_id"])
    monkeypatch.setattr(world.services.run_service, "create", lambda *a, **k: pytest.fail("must not run"))
    response = as_user(world, "alice").post("/api/workflows/wf_nogrant/runs", json={"expected_revision": 1})
    assert response.status_code == 403 and "output_write_denied" in response.text


# --------------------------------------------------------------------- B5 / 08
def test_user_pipelines_and_drafts_are_private(world):
    alice = as_user(world, "alice")
    draft = alice.put("/api/library/drafts/draft_alice_1", json={"expected_revision": 0, "editor": {"name": "a", "description": "", "steps": []}})
    assert draft.status_code == 200, draft.text
    assert [d["id"] for d in alice.get("/api/library/drafts").json()["items"]] == ["draft_alice_1"]
    bob = as_user(world, "bob")
    assert bob.get("/api/library/drafts").json()["items"] == []
    overwrite = bob.put("/api/library/drafts/draft_alice_1", json={"expected_revision": 1, "editor": {"name": "b", "description": "", "steps": []}})
    assert overwrite.status_code == 404
    assert bob.post("/api/library/drafts/draft_alice_1/restore", json={"expected_revision": 1}).status_code == 404


def test_conversations_follow_project_scope(world):
    alice = as_user(world, "alice")
    personal = alice.post("/api/conversations").json()["conversation_id"]
    project = alice.post("/api/conversations", headers={PROJECT: "p1"}).json()["conversation_id"]
    listed = [c["conversation_id"] for c in alice.get("/api/conversations").json()["conversations"]]
    assert listed == [personal]
    listed = [c["conversation_id"] for c in alice.get("/api/conversations", headers={PROJECT: "p1"}).json()["conversations"]]
    assert listed == [project]
    # A project the user is not a member of is rejected, not silently widened.
    assert alice.post("/api/conversations", headers={PROJECT: "p2"}).status_code == 403
    assert alice.get("/api/chat/scope", headers={PROJECT: "p1"}).json() == {"userId": "alice", "projectId": "p1"}


def test_business_audit_records_events_without_file_contents(world):
    workspace = register_output(world, "alice", world.out / "alice")
    alice = as_user(world, "alice")
    proposal = alice.post("/api/fs/read-sensitive", json={"workspace_id": workspace["id"], "path": ".env"}).json()
    alice.post(f"/api/fs/operations/{proposal['id']}/confirm", json={"confirmed": True})
    with world.services.local_store._connect() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM business_audit_events")]
    events = {row["event"] for row in rows}
    assert {"resource.created", "file.read-sensitive.succeeded"} <= events
    assert all("SECRET" not in json.dumps(row) for row in rows)


# -------------------------------------------------------------------------- 13
def test_ownership_tool_is_dry_run_by_default_and_applies_atomically(world, tmp_path):
    from app.workflow_models import Workflow

    store = world.services.local_store
    store.ownership_recorder, recorder = None, store.ownership_recorder
    try:
        legacy = Workflow(workflow_id="wf_legacy", template_id="t", title="legacy", summary="", original_request="x",
                          status="awaiting_method_choice", steps=[], created_at="2025", updated_at="2025")
        store.save_workflow(legacy, event_type="workflow_created")
    finally:
        store.ownership_recorder = recorder
    script = ROOT / "scripts" / "task_b_assign_ownership.py"
    database = str(store.database_path)
    report = subprocess.run([sys.executable, str(ROOT / "scripts" / "task_b_resource_scope_report.py"), database],
                            capture_output=True, text=True, check=True)
    assert {"resource_type": "task", "resource_id": "wf_legacy", "status": "unassigned"} in json.loads(report.stdout)["resources"]
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"assignments": [{
        "resource_type": "task", "resource_id": "wf_legacy", "creator_id": "alice",
        "project_id": "p1", "scope": "project"}]}))
    dry = subprocess.run([sys.executable, str(script), database, str(mapping)], capture_output=True, text=True)
    assert dry.returncode == 0 and json.loads(dry.stdout)["dry_run"] is True
    assert store.resource_policies.get_policy("task", "wf_legacy") is None
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"assignments": [
        {"resource_type": "task", "resource_id": "wf_legacy", "creator_id": "alice"},
        {"resource_type": "task", "resource_id": "missing", "creator_id": "alice"}]}))
    rejected = subprocess.run([sys.executable, str(script), database, str(bad), "--apply"], capture_output=True, text=True)
    assert rejected.returncode == 1
    assert store.resource_policies.get_policy("task", "wf_legacy") is None
    applied = subprocess.run([sys.executable, str(script), database, str(mapping), "--apply"], capture_output=True, text=True)
    assert applied.returncode == 0, applied.stdout
    policy = store.resource_policies.get_policy("task", "wf_legacy")
    assert policy.manager_id == "alice" and policy.project_id == "p1" and policy.scope.value == "project"


def test_records_without_ownership_stay_invisible(world):
    from app.workflow_models import Workflow

    store = world.services.local_store
    store.ownership_recorder, recorder = None, store.ownership_recorder
    try:
        store.save_workflow(Workflow(workflow_id="wf_orphan", template_id="t", title="o", summary="",
                                     original_request="x", status="awaiting_method_choice", steps=[],
                                     created_at="2025", updated_at="2025"), event_type="workflow_created")
    finally:
        store.ownership_recorder = recorder
    for user in ("alice", "bob"):
        client = as_user(world, user)
        assert client.get("/api/workflows/wf_orphan").status_code == 404
        assert client.get("/api/workflow-index").json()["items"] == []


def test_directory_grant_administration(world):
    project_admin = as_user(world, "alice")
    # Project administrators delegate only inside a platform-granted project root.
    denied = project_admin.post("/api/access/directory-grants", headers={PROJECT: "p1"},
                                json={"project_id": "p1", "user_id": "bob", "root": str(world.data), "scope": "read"})
    assert denied.status_code == 403
    grant(world.services, world.data, "read", user_id=ALL_MEMBERS, project_id="p1")
    allowed = project_admin.post("/api/access/directory-grants", headers={PROJECT: "p1"},
                                 json={"project_id": "p1", "user_id": "bob", "root": str(world.data / "study-a"), "scope": "read"})
    assert allowed.status_code == 200, allowed.text
    member = as_user(world, "bob")
    assert member.get("/api/access/directory-grants", params={"project_id": "p1"}, headers={PROJECT: "p1"}).status_code == 403
    mine = member.get("/api/access/directory-grants/mine", headers={PROJECT: "p1"}).json()["items"]
    assert {Path(item["root"]) for item in mine} == {world.data.resolve(), (world.data / "study-a").resolve()}
    assert member.put("/api/access/quotas/user:bob", json={
        "max_concurrent_units": 99, "max_cpus_per_unit": 8, "max_memory_gb_per_unit": 8, "max_gpus_per_unit": 0,
    }).status_code == 403
    assert member.get("/api/access/quotas/mine").json()["user"]["max_concurrent_units"] >= 1


def test_report_database_stays_unchanged(world):
    store = world.services.local_store
    database = Path(store.database_path)
    before = sqlite3.connect(database).execute("SELECT count(*) FROM sqlite_master").fetchone()
    subprocess.run([sys.executable, str(ROOT / "scripts" / "task_b_resource_scope_report.py"), str(database)],
                   capture_output=True, text=True, check=True)
    after = sqlite3.connect(database).execute("SELECT count(*) FROM sqlite_master").fetchone()
    assert before == after


# ------------------------------------------------------------------- B5 models
def test_external_model_file_text_policy_and_usage_records(world, monkeypatch):
    from app.access.model_governance import WITHHELD, is_external_endpoint
    from app.access.request_context import request_scope

    assert is_external_endpoint("https://api.deepseek.com/v1")
    assert not is_external_endpoint("http://127.0.0.1:8000/v1")
    assert not is_external_endpoint("http://10.1.2.3/v1")
    governance = world.services.model_governance
    as_user(world, "alice")
    file_result = {"path": "/data/notes.txt", "text": "patient notes"}
    with request_scope(project_id="p1"):
        assert governance.redact_tool_result(file_result, "https://api.deepseek.com")["text"] == "patient notes"
        governance.set_policy("project:p1", False)
        withheld = governance.redact_tool_result(file_result, "https://api.deepseek.com")
        assert withheld["text"] == WITHHELD and withheld["withheld_by_policy"]
        # A local model may still read the file.
        assert governance.redact_tool_result(file_result, "http://localhost:11434")["text"] == "patient notes"
    # A research member cannot change the project policy.
    with request_scope(project_id="p1"):
        as_user(world, "bob")
        with pytest.raises(PermissionError):
            governance.set_policy("project:p1", True)

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}],
                    "usage": {"prompt_tokens": 7, "completion_tokens": 3, "total_tokens": 10}}

    class Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **k):
            return Response()

    import asyncio

    import app.chat_service as chat_module

    monkeypatch.setattr(chat_module.httpx, "AsyncClient", Client)
    chat = world.services.chat_service
    monkeypatch.setattr(chat, "base_url", "https://api.deepseek.com")
    monkeypatch.setattr(chat, "model", "deepseek-chat")
    as_user(world, "alice")
    with request_scope(project_id="p1"):
        assert asyncio.run(chat.complete([{"role": "user", "content": "hi"}])) == "ok"
    alice = world.client
    usage = alice.get("/api/access/model-usage/mine", headers={PROJECT: "p1"}).json()
    assert usage["user"]["calls"] == 1 and usage["user"]["total_tokens"] == 10
    assert usage["project"]["total_tokens"] == 10
    assert as_user(world, "bob").get("/api/access/model-usage/mine").json()["user"]["calls"] == 0
    with world.services.local_store._connect() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM business_audit_events WHERE event LIKE 'model.%'")]
    assert {"model.call", "model.file_text.withheld", "model.policy.updated"} <= {r["event"] for r in rows}
    assert all("patient notes" not in json.dumps(r) and "hi" != r.get("reason") for r in rows)


def test_model_policy_api_permissions(world):
    alice = as_user(world, "alice")
    assert alice.get("/api/access/model-policy").json()["subject"] == "personal:alice"
    assert alice.put("/api/access/model-policy/personal:alice", json={"allow_external_file_text": False}).status_code == 200
    assert alice.get("/api/access/model-policy").json()["allow_external_file_text"] is False
    assert alice.put("/api/access/model-policy/personal:bob", json={"allow_external_file_text": True}).status_code == 403
    assert alice.put("/api/access/model-policy/default", json={"allow_external_file_text": True}).status_code == 403
    member = as_user(world, "bob")
    assert member.put("/api/access/model-policy/project:p1", headers={PROJECT: "p1"},
                      json={"allow_external_file_text": False}).status_code == 403


# ------------------------------------------------------------------- §5 cleanup
def test_cleanup_removes_only_unassigned_unused_records(world, tmp_path):
    from app.run_models import WorkflowRun
    from app.workflow_models import Workflow

    store = world.services.local_store
    store.ownership_recorder, recorder = None, store.ownership_recorder
    try:
        for workflow_id in ("wf_obsolete", "wf_with_results"):
            store.save_workflow(Workflow(workflow_id=workflow_id, template_id="t", title=workflow_id, summary="",
                                         original_request="x", status="awaiting_method_choice", steps=[],
                                         created_at="2025", updated_at="2025"), event_type="workflow_created")
        store.save_run(WorkflowRun(run_id="run_kept", workflow_id="wf_with_results", workflow_revision=1,
                                   status="succeeded", output_directory=str(tmp_path), created_at="2025", updated_at="2025"))
    finally:
        store.ownership_recorder = recorder
    save_task(world, "alice", "wf_owned")
    script = ROOT / "scripts" / "task_b_cleanup_records.py"
    database = str(store.database_path)

    def run(items, *flags):
        path = tmp_path / "cleanup.json"
        path.write_text(json.dumps({"remove": [{"resource_type": "task", "resource_id": i} for i in items]}))
        return subprocess.run([sys.executable, str(script), database, str(path), *flags], capture_output=True, text=True)

    assert "has run records" in run(["wf_with_results"]).stdout
    assert "has an owner" in run(["wf_owned"]).stdout
    dry = run(["wf_obsolete"])
    assert dry.returncode == 0 and json.loads(dry.stdout)["dry_run"]
    assert store.get_workflow("wf_obsolete") is not None
    # A list with one blocked entry removes nothing at all.
    assert run(["wf_obsolete", "wf_with_results"], "--apply").returncode == 1
    assert store.get_workflow("wf_obsolete") is not None
    applied = run(["wf_obsolete"], "--apply")
    assert applied.returncode == 0, applied.stdout
    assert store.get_workflow("wf_obsolete") is None
    assert store.get_workflow("wf_with_results") is not None and store.get_workflow("wf_owned") is not None
    assert tmp_path.exists()
