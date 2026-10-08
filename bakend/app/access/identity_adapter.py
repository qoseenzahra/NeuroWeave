from __future__ import annotations

from dataclasses import dataclass

from .contracts import Identity, IdentityReader, ProjectMembership


@dataclass(frozen=True)
class UnauthenticatedIdentityReader(IdentityReader):
    """Safe production default until Developer A wires the real session reader."""

    def current_identity(self) -> Identity:
        return Identity(user_id="", enabled=False)

    def project_membership(self, project_id: str) -> ProjectMembership | None:
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

    def current_identity(self) -> Identity:
        return self.identity

    def project_membership(self, project_id: str) -> ProjectMembership | None:
        return self.memberships.get(project_id)
