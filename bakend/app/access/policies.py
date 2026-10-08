from __future__ import annotations

from .contracts import (
    AuthorizationContext,
    AuthorizationDecision,
    ProjectRole,
    ResourceAction,
    SharingScope,
)


ADMIN_ACTIONS = frozenset(ResourceAction)
OWNER_ACTIONS = frozenset({
    ResourceAction.READ, ResourceAction.UPDATE, ResourceAction.DELETE,
    ResourceAction.RESTORE, ResourceAction.PUBLISH, ResourceAction.SHARE,
    ResourceAction.HANDOVER, ResourceAction.SUBMIT, ResourceAction.RETRY,
    ResourceAction.CANCEL, ResourceAction.CONFIRM, ResourceAction.EXPORT,
})


def decide(ctx: AuthorizationContext, action: ResourceAction) -> AuthorizationDecision:
    identity = ctx.identity
    resource = ctx.resource

    if not identity.enabled:
        return AuthorizationDecision(False, "account_disabled")
    if resource is None:
        return AuthorizationDecision(False, "resource_context_required")

    owner = resource.owner
    membership = ctx.membership

    if owner.project_id is not None:
        if membership is None or not membership.active:
            return AuthorizationDecision(False, "project_membership_required")
        if membership.project_id != owner.project_id:
            return AuthorizationDecision(False, "wrong_project")

    is_owner = identity.user_id in {owner.creator_id, owner.manager_id}
    in_project_scope = (
        owner.scope is SharingScope.PROJECT
        and membership is not None
        and membership.active
        and membership.project_id == owner.project_id
    )

    if owner.scope is SharingScope.PRIVATE and not is_owner:
        return AuthorizationDecision(False, "private_resource")

    if membership and membership.role is ProjectRole.ADMINISTRATOR and in_project_scope:
        return AuthorizationDecision(True, "project_administrator", ADMIN_ACTIONS)

    if is_owner:
        return AuthorizationDecision(True, "resource_owner", OWNER_ACTIONS)

    if in_project_scope and action in {ResourceAction.READ, ResourceAction.EXPORT}:
        return AuthorizationDecision(
            True, "project_member_read",
            frozenset({ResourceAction.READ, ResourceAction.EXPORT}),
        )

    return AuthorizationDecision(False, "action_not_permitted")


def allowed_actions(ctx: AuthorizationContext) -> frozenset[ResourceAction]:
    return frozenset(action for action in ResourceAction if decide(ctx, action).allowed)
