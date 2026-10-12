"""LOCAL DEMO ONLY - never deploy, never commit.

Starts NeuroWeave with Task B authorization and a pretend login so you can see
the permission rules in a browser before Developer A's real login exists.

Demo users (switch with the links below):
  alice  - project "lab" administrator
  bob    - project "lab" research member
  admin  - platform administrator

  http://127.0.0.1:5173/api/demo/login/alice
  http://127.0.0.1:5173/api/demo/login/bob
  http://127.0.0.1:5173/api/demo/logout

Demo folders are created in your home folder under "neuroweave-demo".
Run from the "bakend" folder:
  .venv/Scripts/python -m uvicorn demo_app:app --host 127.0.0.1 --port 8010
"""

from __future__ import annotations

import os
from pathlib import Path

DEMO = Path.home() / "neuroweave-demo"
for folder in ("data/study-a/sub-01", "data/study-b/sub-02", "outputs/alice", "outputs/bob", "outputs/lab", "runs"):
    (DEMO / folder).mkdir(parents=True, exist_ok=True)
for name, text in {
    "data/study-a/notes.txt": "Study A notes (alice can read this)",
    "data/study-b/notes.txt": "Study B notes (bob can read this)",
    "outputs/alice/alice-report.txt": "Alice's private result",
    "outputs/bob/bob-report.txt": "Bob's private result",
}.items():
    path = DEMO / name
    if not path.exists():
        path.write_text(text, encoding="utf-8")

os.environ.setdefault("LOCALFLOW_DATABASE_PATH", str(DEMO / "demo.db"))
os.environ.setdefault("LOCALFLOW_DATA_ROOTS", str(DEMO / "data"))
os.environ.setdefault("WORKSPACE_ALLOWED_ROOTS", str(DEMO))
os.environ.setdefault("WORKSPACE_DEFAULT_ROOT", str(DEMO))
os.environ.setdefault("LOCALFLOW_OUTPUT_ROOT", str(DEMO / "runs"))
os.environ.setdefault("LOCALFLOW_SLURM_ENABLED", "false")

from fastapi.responses import RedirectResponse  # noqa: E402

from app.access.contracts import Identity, PlatformRole, ProjectMembership, ProjectRole  # noqa: E402
from app.access.directory_grants import ALL_MEMBERS, DirectoryGrantStore  # noqa: E402
from app.access.filesystem import GrantScope  # noqa: E402
from app.access.request_context import RequestIdentityReader  # noqa: E402
from app.application import create_app  # noqa: E402
from app.bootstrap import build_services  # noqa: E402
from app.settings import Settings  # noqa: E402

COOKIE = "neuroweave_demo_user"
USERS = {
    "alice": Identity("alice"),
    "bob": Identity("bob"),
    "admin": Identity("admin", platform_role=PlatformRole.ADMIN),
}
MEMBERS = {
    ("alice", "lab"): ProjectMembership("lab", "alice", ProjectRole.ADMINISTRATOR),
    ("bob", "lab"): ProjectMembership("lab", "bob", ProjectRole.MEMBER),
}


class DemoAuthority:
    """Stand-in for Developer A's identity service (demo only)."""

    def resolve_session(self, request):
        return request.cookies.get(COOKIE)

    def identity_for_session(self, session):
        return USERS.get(session)

    def membership_for(self, user_id, project_id):
        return MEMBERS.get((user_id, project_id))


services = build_services(Settings.from_environment(), identity_reader=RequestIdentityReader(DemoAuthority()))

grants = DirectoryGrantStore(services.local_store)
for user_id, project_id, root, scope in [
    ("alice", "", DEMO / "data" / "study-a", GrantScope.READ),
    ("alice", "", DEMO / "outputs" / "alice", GrantScope.WRITE),
    ("bob", "", DEMO / "data" / "study-b", GrantScope.READ),
    ("bob", "", DEMO / "outputs" / "bob", GrantScope.WRITE),
    (ALL_MEMBERS, "lab", DEMO / "data", GrantScope.READ),
    (ALL_MEMBERS, "lab", DEMO / "outputs" / "lab", GrantScope.WRITE),
]:
    try:
        grants.create(user_id=user_id, project_id=project_id, root=root, scope=scope, created_by="demo")
    except ValueError:
        pass  # already granted on an earlier start

app = create_app(services)


@app.get("/api/demo/login/{user}")
def demo_login(user: str):
    response = RedirectResponse("/", status_code=302)
    if user in USERS:
        response.set_cookie(COOKIE, user, httponly=True, samesite="lax")
    return response


@app.get("/api/demo/logout")
def demo_logout():
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(COOKIE)
    return response
