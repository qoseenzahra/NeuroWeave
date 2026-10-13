from __future__ import annotations

from dataclasses import dataclass

from .contracts import (
    AuthorizationDenied, Identity, IdentityReader, PlatformRole, ProjectMembership, ProjectRole,
)


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

    A's reader raises ``IdentityUnavailable`` instead of returning ``None``;
    the adapter turns that into B's fail-closed values (an unauthenticated
    identity, or no membership).

    A's contract only reads the *current* actor's project access. Looking up
    another user's membership (needed by resource handover) uses the optional
    ``membership_lookup(user_id, project_id, connection=...)`` callable that
    A's project service can supply; without it handover fails closed.
    """

    def __init__(self, reader, *, membership_lookup=None):
        self.reader = reader
        self.membership_lookup = membership_lookup

    @staticmethod
    def _identity(actor) -> Identity:
        if actor is None or not actor.user_id:
            return Identity(user_id="", enabled=False)
        return Identity(
            user_id=actor.user_id,
            enabled=True,
            platform_role=PlatformRole(actor.platform_role.value),
            identity_revision=actor.identity_revision,
        )

    @staticmethod
    def _membership(access) -> ProjectMembership | None:
        from ..identity.contracts import ProjectStatus

        if access is None:
            return None
        return ProjectMembership(
            project_id=access.project_id,
            user_id=access.user_id,
            role=ProjectRole(access.project_role.value),
            active=True,
            archived=access.project_status is ProjectStatus.ARCHIVED,
            membership_revision=access.membership_revision,
            project_revision=access.project_revision,
        )

    def _actor(self, connection):
        from ..identity.contracts import IdentityUnavailable

        try:
            return self.reader.current_identity(connection=connection)
        except IdentityUnavailable:
            return None

    def current_identity(self, *, connection=None) -> Identity:
        return self._identity(self._actor(connection))

    def project_membership(self, project_id: str, *, connection=None) -> ProjectMembership | None:
        from ..identity.contracts import IdentityUnavailable

        actor = self._actor(connection)
        if actor is None or not project_id:
            return None
        try:
            access = self.reader.project_access(actor, project_id, connection=connection)
        except IdentityUnavailable:
            return None
        membership = self._membership(access)
        if membership is None or membership.user_id != actor.user_id:
            return None
        return membership

    def membership_of(self, user_id: str, project_id: str, *, connection=None) -> ProjectMembership | None:
        if not user_id or not project_id:
            return None
        actor = self._actor(connection)
        if actor is not None and actor.user_id == user_id:
            return self.project_membership(project_id, connection=connection)
        if self.membership_lookup is None:
            raise AuthorizationDenied("membership_lookup_unavailable")
        membership = self._membership(self.membership_lookup(user_id, project_id, connection=connection))
        if membership is None or membership.user_id != user_id or membership.project_id != project_id:
            return None
        return membership
