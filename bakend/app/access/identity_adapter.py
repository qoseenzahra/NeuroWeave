from __future__ import annotations

from dataclasses import dataclass

from .contracts import Identity, IdentityReader, ProjectMembership


@dataclass(frozen=True)
class UnauthenticatedIdentityReader(IdentityReader):
    """Safe production default until Developer A wires the real session reader."""

    def current_identity(self, **_kwargs) -> Identity:
        return Identity(user_id="", enabled=False)

    def project_membership(self, project_id: str, **_kwargs) -> ProjectMembership | None:
        return None


class TestIdentityReader(IdentityReader):
    """Test-only identity double. Never use this in production assembly."""

    def __init__(
        self,
        identity: Identity,
        memberships: dict[str, ProjectMembership] | None = None,
    ):
        self.identity = identity
        self.memberships = memberships or {}

    def current_identity(self, **_kwargs) -> Identity:
        return self.identity

    def project_membership(self, project_id: str, **_kwargs) -> ProjectMembership | None:
        return self.memberships.get(project_id)


class ContractIdentityReader(IdentityReader):
    """Production adapter over Developer A's ``identity.contracts.IdentityReader``.

    Every call reads A's live state (no caching): a disabled account, revoked
    session, removed membership, role change or archived project is visible
    to the very next authorization check. ``connection`` is passed through so
    a check can run inside the business transaction it protects.
    """

    def __init__(self, reader):
        self.reader = reader

    @staticmethod
    def _identity(actor) -> Identity:
        from .contracts import PlatformRole

        if actor is None or not actor.user_id:
            return Identity(user_id="", enabled=False)
        return Identity(
            user_id=actor.user_id,
            enabled=actor.active,
            platform_role=PlatformRole(actor.platform_role.value),
            identity_revision=actor.identity_revision,
        )

    @staticmethod
    def _membership(access) -> ProjectMembership | None:
        from ..identity.contracts import ProjectState
        from .contracts import ProjectRole

        if access is None:
            return None
        return ProjectMembership(
            project_id=access.project_id,
            user_id=access.user_id,
            role=ProjectRole(access.role.value),
            active=True,
            archived=access.project_state is ProjectState.ARCHIVED,
            membership_revision=access.membership_revision,
            project_revision=access.project_revision,
        )

    def current_identity(self, *, connection=None) -> Identity:
        return self._identity(self.reader.current_actor(connection=connection))

    def project_membership(self, project_id: str, *, connection=None) -> ProjectMembership | None:
        identity = self.current_identity(connection=connection)
        if not identity.authenticated or not project_id:
            return None
        membership = self._membership(self.reader.project_access(project_id, connection=connection))
        if membership is None or membership.user_id != identity.user_id:
            return None
        return membership

    def membership_of(self, user_id: str, project_id: str, *, connection=None) -> ProjectMembership | None:
        return self._membership(self.reader.project_access_for(user_id, project_id, connection=connection))
