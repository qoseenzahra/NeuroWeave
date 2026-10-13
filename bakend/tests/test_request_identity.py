"""The production identity adapter is live, request-scoped and fail-closed."""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.access.contracts import Identity, ProjectMembership, ProjectRole
from app.access.request_context import (
    PROJECT_HEADER,
    InvalidProjectScope,
    RequestIdentityReader,
    install_request_context,
    parse_project_header,
    request_scope,
    requested_project,
)


class Authority:
    """Stands in for A's identity service: cookie → session → live identity."""

    def __init__(self):
        self.sessions = {"cookie-alice": "s-alice"}
        self.users = {"s-alice": Identity("alice")}
        self.members = {("alice", "p1"): ProjectMembership("p1", "alice", ProjectRole.MEMBER)}

    def resolve_session(self, request):
        return self.sessions.get(request.headers.get("cookie", ""))

    def identity_for_session(self, session):
        return self.users.get(session)

    def membership_for(self, user_id, project_id):
        return self.members.get((user_id, project_id))


def test_client_supplied_identity_is_never_trusted():
    authority = Authority()
    reader = RequestIdentityReader(authority)
    app = FastAPI()
    install_request_context(app, lambda: reader)

    @app.get("/whoami")
    def whoami():
        identity = reader.current_identity()
        return {"user": identity.user_id, "project": requested_project(),
                "member": bool(reader.project_membership("p1"))}

    with TestClient(app) as client:
        assert client.get("/whoami", headers={"x-user-id": "alice"}).json() == {
            "user": "", "project": None, "member": False}
        assert client.get("/whoami", headers={"cookie": "cookie-alice", PROJECT_HEADER: "p1"}).json() == {
            "user": "alice", "project": "p1", "member": True}
        assert client.get("/whoami", headers={PROJECT_HEADER: "../etc"}).status_code == 400


def test_revocation_is_seen_by_work_started_before_it():
    authority = Authority()
    reader = RequestIdentityReader(authority)

    async def background():
        await asyncio.sleep(0)
        return reader.current_identity()

    async def scenario():
        with request_scope(session="s-alice", project_id="p1"):
            task = asyncio.create_task(background())
        # Session revoked by A after the request finished, before the work ran.
        authority.users.pop("s-alice")
        return await task

    identity = asyncio.run(scenario())
    assert not identity.authenticated


def test_membership_for_another_user_is_ignored():
    authority = Authority()
    authority.members[("alice", "p2")] = ProjectMembership("p2", "mallory", ProjectRole.MANAGER)
    reader = RequestIdentityReader(authority)
    with request_scope(session="s-alice"):
        assert reader.project_membership("p2") is None


@pytest.mark.parametrize("value,expected", [(None, None), ("", None), ("personal", None), ("lab-1", "lab-1")])
def test_project_header_parsing(value, expected):
    assert parse_project_header(value) == expected


def test_project_header_rejects_invalid_values():
    with pytest.raises(InvalidProjectScope):
        parse_project_header("a b")
