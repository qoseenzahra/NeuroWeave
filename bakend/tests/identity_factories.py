"""Test-only identity and grant factories for Task B (never used in production).

They stand in for A's identity service: two users, two projects and both
project roles. Production assembly fails closed without A's reader.
"""

from __future__ import annotations

from pathlib import Path

from app.access.contracts import Identity, PlatformRole, ProjectMembership, ProjectRole
from app.access.directory_grants import ALL_MEMBERS, DirectoryGrantStore  # noqa: F401
from app.access.filesystem import GrantScope
from app.access.identity_adapter import TestIdentityReader
from app.access.service import AuthorizationService

ADMIN = ProjectRole.ADMINISTRATOR
MEMBER = ProjectRole.MEMBER


class IdentityDouble(TestIdentityReader):
    """Switchable current user with a shared membership directory."""

    def __init__(self, user_id: str = "test-user", *, directory=None, platform_role=PlatformRole.USER,
                 enabled: bool = True):
        self.directory: dict[tuple[str, str], ProjectMembership] = directory if directory is not None else {}
        super().__init__(Identity(user_id, enabled=enabled, platform_role=platform_role), {})
        self._refresh()

    def _refresh(self):
        self.memberships = {
            project: membership for (user, project), membership in self.directory.items()
            if user == self.identity.user_id
        }

    def become(self, user_id: str, *, platform_role=PlatformRole.USER, enabled: bool = True,
               identity_revision: int = 0):
        self.identity = Identity(user_id, enabled=enabled, platform_role=platform_role,
                                 identity_revision=identity_revision)
        self._refresh()
        return self

    def sign_out(self):
        self.identity = Identity("", enabled=False)
        self._refresh()
        return self

    def add_member(self, user_id: str, project_id: str, role: ProjectRole = MEMBER, active: bool = True,
                   *, archived: bool = False, membership_revision: int = 0):
        self.directory[(user_id, project_id)] = ProjectMembership(
            project_id, user_id, role, active, archived=archived, membership_revision=membership_revision,
        )
        self._refresh()
        return self

    def remove_member(self, user_id: str, project_id: str):
        self.directory.pop((user_id, project_id), None)
        self._refresh()
        return self

    def membership_of(self, user_id: str, project_id: str):
        return self.directory.get((user_id, project_id))


def sign_in(services, user_id: str = "test-user", **kwargs) -> IdentityDouble:
    reader = IdentityDouble(user_id, **kwargs)
    services.authorization_service.identity_reader = reader
    return reader


def grant(services_or_store, root, scope: str = "write", *, user_id: str = "test-user",
          project_id: str = "", created_by: str = "test-admin") -> dict:
    """Directory grant; ``user_id=ALL_MEMBERS`` grants every member of a project."""
    store = getattr(services_or_store, "local_store", services_or_store)
    return DirectoryGrantStore(store).create(
        user_id=user_id, project_id=project_id, root=Path(root).resolve(),
        scope=GrantScope(scope), created_by=created_by,
    )


def authorization(user_id: str = "test-user") -> AuthorizationService:
    return AuthorizationService(IdentityDouble(user_id))


def wire_access(store, user_id: str = "test-user", *, reader: IdentityDouble | None = None):
    """Real ResourceAccess over a test identity, with creation ownership hooks."""
    from app.access.resources import ResourceAccess

    reader = reader or IdentityDouble(user_id)
    access = ResourceAccess(store, AuthorizationService(reader))
    store.ownership_recorder = (
        lambda resource_type, resource_id, connection: access.record_creation(
            resource_type, resource_id, connection=connection
        )
    )
    return access


def library_app(library, *args, access=None, **kwargs):
    """FastAPI app with the library router wired to a test identity."""
    from fastapi import FastAPI

    from app.application import install_access_error_handlers
    from app.library_routes import library_router

    access = access or wire_access(library.store)
    library.access = access
    app = FastAPI()
    install_access_error_handlers(app)
    app.include_router(library_router(library, *args, access=access, **kwargs))
    return app
