from __future__ import annotations

from .contracts import (
    AuditSink, AuthorizationContext, AuthorizationDecision,
    AuthorizationDenied, Identity, IdentityReader, ResourceAction, ResourceRef,
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

    def require_authenticated(self) -> Identity:
        identity = self.identity_reader.current_identity()
        if not identity.enabled:
            raise AuthorizationDenied("account_disabled")
        if not identity.user_id:
            raise AuthorizationDenied("authentication_required")
        return identity

    def context_for(self, resource: ResourceRef) -> AuthorizationContext:
        identity = self.identity_reader.current_identity()
        membership = (
            self.identity_reader.project_membership(resource.owner.project_id)
            if resource.owner.project_id and identity.user_id else None
        )
        if membership is not None and membership.user_id != identity.user_id:
            # A membership row for somebody else must never authorize this actor.
            membership = None
        return AuthorizationContext(identity, membership, resource)

    def evaluate(self, resource: ResourceRef, action: ResourceAction) -> AuthorizationDecision:
        """Side-effect free decision used for list filtering and allowed_actions."""
        identity = self.identity_reader.current_identity()
        if not identity.enabled or not identity.user_id:
            return AuthorizationDecision(False, "authentication_required")
        return decide(self.context_for(resource), action)

    def check(self, resource: ResourceRef, action: ResourceAction) -> AuthorizationDecision:
        self.require_authenticated()
        ctx = self.context_for(resource)
        decision = decide(ctx, action)
        # Denials and every non-read decision are business audit events. Reads
        # that succeed are high-volume list traffic and are not individually logged.
        if self.audit and (not decision.allowed or action is not ResourceAction.READ):
            self.audit.record(
                "authorization.check",
                user_id=ctx.identity.user_id,
                project_id=resource.owner.project_id,
                resource_type=resource.resource_type.value,
                resource_id=resource.resource_id,
                action=action.value,
                reason=decision.reason if decision.allowed else f"denied:{decision.reason}",
            )
        return decision

    def require(self, resource: ResourceRef, action: ResourceAction) -> None:
        decision = self.check(resource, action)
        if not decision.allowed:
            raise AuthorizationDenied(decision.reason)

    def actions(self, resource: ResourceRef) -> set[str]:
        identity = self.identity_reader.current_identity()
        if not identity.enabled or not identity.user_id:
            return set()
        return {action.value for action in allowed_actions(self.context_for(resource))}

    def filter_visible(self, resources: list[ResourceRef], action: ResourceAction) -> list[ResourceRef]:
        # Authorization filtering occurs before pagination/counting.
        return [r for r in resources if self.evaluate(r, action).allowed]
