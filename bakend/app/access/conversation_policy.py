from __future__ import annotations

from .contracts import ResourceOwner, ResourceRef, ResourceType, SharingScope
from .resource_store import ResourcePolicyStore, StoredResourcePolicy


class ConversationAuthorization:
    """Bridge durable conversation ownership into the shared Task B policy."""

    def __init__(self, store: ResourcePolicyStore):
        self.store = store

    def resource(self, conversation_id: str) -> ResourceRef:
        policy = self.store.get_policy("conversation", conversation_id)
        if policy is None:
            raise KeyError(conversation_id)
        return ResourceRef(
            resource_type=ResourceType.CONVERSATION,
            resource_id=conversation_id,
            owner=ResourceOwner(
                creator_id=policy.creator_id,
                manager_id=policy.manager_id,
                project_id=policy.project_id,
                scope=SharingScope(policy.scope.value),
                permission_revision=policy.permission_revision,
            ),
        )

    def save_owner(
        self,
        conversation_id: str,
        user_id: str,
        project_id: str | None = None,
        scope: SharingScope = SharingScope.PRIVATE,
    ) -> None:
        self.store.put_policy(
            StoredResourcePolicy(
                resource_type="conversation",
                resource_id=conversation_id,
                creator_id=user_id,
                manager_id=user_id,
                project_id=project_id,
                scope=scope.value,
                permission_revision=0,
            )
        )
