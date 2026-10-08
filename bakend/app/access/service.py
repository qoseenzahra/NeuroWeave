from __future__ import annotations

from .contracts import (
    AuditSink, AuthorizationContext, AuthorizationDecision,
    AuthorizationDenied, IdentityReader, ResourceAction, ResourceRef,
)
from .policies import allowed_actions, decide


class AuthorizationService:
    """Single business authorization entry point.

    Identity and membership are read at each operation. No frontend user/role
    state and no long-lived authorization cache are trusted.
    """

    def __init__(self, identity_reader: IdentityReader, audit: AuditSink | None = None):
        self.identity_reader = identity_reader
        self.audit = audit

    def context_for(self, resource: ResourceRef) -> AuthorizationContext:
        identity = self.identity_reader.current_identity()
        membership = (
            self.identity_reader.project_membership(resource.owner.project_id)
            if resource.owner.project_id else None
        )
        return AuthorizationContext(identity, membership, resource)

    def check(self, resource: ResourceRef, action: ResourceAction) -> AuthorizationDecision:
        ctx = self.context_for(resource)
        decision = decide(ctx, action)
        if self.audit:
            self.audit.record(
                "authorization.check",
                user_id=ctx.identity.user_id,
                project_id=resource.owner.project_id,
                resource_type=resource.resource_type.value,
                resource_id=resource.resource_id,
                action=action.value,
                reason=decision.reason,
            )
        return decision

    def require(self, resource: ResourceRef, action: ResourceAction) -> None:
        decision = self.check(resource, action)
        if not decision.allowed:
            raise AuthorizationDenied(decision.reason)

    def actions(self, resource: ResourceRef) -> set[str]:
        return {action.value for action in allowed_actions(self.context_for(resource))}

    def filter_visible(self, resources: list[ResourceRef], action: ResourceAction) -> list[ResourceRef]:
        # Authorization filtering occurs before pagination/counting.
        return [r for r in resources if self.check(r, action).allowed]
