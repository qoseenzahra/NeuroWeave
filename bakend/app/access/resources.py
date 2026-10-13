"""Shared resource ownership, visibility and management for business modules.

Every business entry point goes through :class:`ResourceAccess`:

* creation records the trusted actor (never a client-supplied id) as creator and
  management owner, inside the caller's transaction when one is passed;
* ``require`` treats unknown *and* invisible objects as nonexistent
  (``ResourceNotFound``) and raises ``AuthorizationDenied`` only for visible
  objects whose action is not permitted;
* ``visible_ids`` is computed from the durable policy table before any SQL
  pagination or counting, so authorized rows are never truncated away;
* sharing, handover and platform takeover bump the permission revision, which
  invalidates pending proposals, background operations and execution grants.

Records without an ownership row are never visible (fail closed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from .contracts import (
    AuthorizationDenied,
    Identity,
    PlatformRole,
    ResourceAction,
    ResourceNotFound,
    ResourceOwner,
    ResourceRef,
    ResourceType,
    SharingScope,
)
from .request_context import administrative_reason, requested_project
from .resource_store import ResourceScope, StoredResourcePolicy
from .service import AuthorizationService

_UNSET = object()

# Resources whose permissions are inherited from a parent and that therefore
# never carry their own ownership row.
INHERITED = {
    ResourceType.RUN: ResourceType.TASK,
    ResourceType.HISTORICAL_RESULT: ResourceType.RUN,
    ResourceType.MESSAGE: ResourceType.CONVERSATION,
}


@dataclass(frozen=True)
class ResourceView:
    resource_type: str
    resource_id: str
    creator_id: str
    manager_id: str
    project_id: str | None
    scope: str
    permission_revision: int
    allowed_actions: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "creator_id": self.creator_id,
            "manager_id": self.manager_id,
            "project_id": self.project_id,
            "scope": self.scope,
            "permission_revision": self.permission_revision,
            "allowed_actions": list(self.allowed_actions),
        }


class ResourceAccess:
    def __init__(self, store, authorization: AuthorizationService):
        self.store = store
        self.authorization = authorization
        self.dependencies: dict[ResourceType, Callable[[str], list[tuple[ResourceType, str]]]] = {}

    # ------------------------------------------------------------------ identity
    @property
    def identity_reader(self):
        return self.authorization.identity_reader

    def actor(self) -> Identity:
        return self.authorization.require_authenticated()

    def current_project(self) -> str | None:
        """Requested project scope, validated against live membership."""
        project_id = requested_project()
        if project_id is None:
            return None
        membership = self.identity_reader.project_membership(project_id)
        if membership is None or not membership.active or membership.project_id != project_id:
            raise AuthorizationDenied("project_membership_required")
        return project_id

    def current_membership(self):
        project_id = requested_project()
        if project_id is None:
            return None
        self.current_project()
        return self.identity_reader.project_membership(project_id)

    def require_writable_project(self) -> str | None:
        """New resources and new work cannot be created in an archived project."""
        project_id = self.current_project()
        membership = self.current_membership()
        if membership is not None and membership.archived:
            raise AuthorizationDenied("project_archived")
        return project_id

    def _audit(self, event, *, resource_type, resource_id, action, reason, project_id=None,
               summary=None, connection=None):
        audit = self.authorization.audit
        if audit is None:
            return
        identity = self.identity_reader.current_identity()
        kwargs = dict(
            user_id=identity.user_id, project_id=project_id,
            resource_type=resource_type, resource_id=resource_id,
            action=action, reason=reason,
        )
        extended = {}
        if summary is not None:
            extended["summary"] = summary
        if connection is not None:
            extended["connection"] = connection
        if extended:
            try:
                audit.record(event, **kwargs, **extended)
                return
            except TypeError:
                # A's common sink may not accept B's optional extensions.
                pass
        audit.record(event, **kwargs)

    # ------------------------------------------------------------------ policies
    @staticmethod
    def _type(resource_type: ResourceType | str) -> ResourceType:
        return resource_type if isinstance(resource_type, ResourceType) else ResourceType(resource_type)

    def policy(self, resource_type, resource_id: str) -> StoredResourcePolicy | None:
        return self.store.resource_policies.get_policy(self._type(resource_type).value, resource_id)

    def ref(self, resource_type, resource_id: str) -> ResourceRef:
        rtype = self._type(resource_type)
        policy = self.policy(rtype, resource_id)
        if policy is None:
            raise ResourceNotFound(resource_id)
        return self._ref_from_policy(rtype, policy)

    @staticmethod
    def _ref_from_policy(rtype: ResourceType, policy: StoredResourcePolicy) -> ResourceRef:
        return ResourceRef(
            resource_type=rtype,
            resource_id=policy.resource_id,
            owner=ResourceOwner(
                creator_id=policy.creator_id,
                manager_id=policy.manager_id,
                project_id=policy.project_id,
                scope=SharingScope(policy.scope.value),
                permission_revision=policy.permission_revision,
            ),
        )

    def record_creation(
        self,
        resource_type,
        resource_id: str,
        *,
        connection=None,
        project_id=_UNSET,
        scope: SharingScope = SharingScope.PRIVATE,
    ) -> StoredResourcePolicy:
        """Assign ownership of a newly created resource to the trusted actor."""
        rtype = self._type(resource_type)
        identity = self.actor()
        project = self.require_writable_project() if project_id is _UNSET else project_id
        if scope is SharingScope.PROJECT and project is None:
            raise AuthorizationDenied("project_scope_requires_project")
        policy = StoredResourcePolicy(
            resource_type=rtype.value,
            resource_id=resource_id,
            creator_id=identity.user_id,
            manager_id=identity.user_id,
            project_id=project,
            scope=ResourceScope(scope.value),
            permission_revision=0,
        )
        sql = (
            "INSERT INTO resource_policies"
            "(resource_type,resource_id,creator_id,manager_id,project_id,scope,permission_revision)"
            " VALUES(?,?,?,?,?,?,?)"
        )
        values = (
            policy.resource_type, policy.resource_id, policy.creator_id,
            policy.manager_id, policy.project_id, policy.scope.value, 0,
        )
        def write(db):
            existing = db.execute(
                "SELECT manager_id FROM resource_policies WHERE resource_type=? AND resource_id=?",
                (policy.resource_type, policy.resource_id),
            ).fetchone()
            if existing is not None:
                # An identifier that already carries someone's policy can never
                # be re-created (and thereby adopted) by another actor.
                if existing["manager_id"] != identity.user_id:
                    raise AuthorizationDenied("resource_identifier_unavailable")
                return
            db.execute(sql, values)

        if connection is not None:
            write(connection)
            self._audit(
                "resource.created", resource_type=rtype.value, resource_id=resource_id,
                action="create", reason="owner_assigned", project_id=project, connection=connection,
            )
        else:
            with self.store._connect() as db:
                write(db)
                self._audit(
                    "resource.created", resource_type=rtype.value, resource_id=resource_id,
                    action="create", reason="owner_assigned", project_id=project, connection=db,
                )
        return policy

    def ensure_creation(self, resource_type, resource_id: str, *, connection=None) -> None:
        """Assign ownership if absent; used by store hooks on first insert."""
        if self.policy(resource_type, resource_id) is None:
            self.record_creation(resource_type, resource_id, connection=connection)

    # ---------------------------------------------------------------- decisions
    def decide(self, resource_type, resource_id: str, action: ResourceAction):
        try:
            ref = self.ref(resource_type, resource_id)
        except ResourceNotFound:
            return None
        return self.authorization.evaluate(ref, action)

    def can(self, resource_type, resource_id: str, action: ResourceAction) -> bool:
        decision = self.decide(resource_type, resource_id, action)
        return bool(decision and decision.allowed)

    def require(self, resource_type, resource_id: str, action: ResourceAction) -> ResourceRef:
        """Authorize ``action``; invisible objects are reported as nonexistent."""
        rtype = self._type(resource_type)
        self.actor()
        ref = self.ref(rtype, resource_id)
        if not self.authorization.evaluate(ref, ResourceAction.READ).allowed:
            self._audit(
                "authorization.check", resource_type=rtype.value, resource_id=resource_id,
                action=action.value, reason="denied:not_visible", project_id=ref.owner.project_id,
            )
            raise ResourceNotFound(resource_id)
        decision = self.authorization.check(ref, action)
        if not decision.allowed:
            raise AuthorizationDenied(decision.reason)
        self._require_administrative_reason(ref, action, decision)
        return ref

    def _require_administrative_reason(self, ref: ResourceRef, action: ResourceAction, decision) -> None:
        """Managing another member's shared resource needs a recorded reason (§7)."""
        if action in {ResourceAction.READ, ResourceAction.EXPORT}:
            return
        identity = self.identity_reader.current_identity()
        if decision.reason != "project_administrator" or identity.user_id == ref.owner.manager_id:
            return
        reason = administrative_reason()
        if not reason or len(reason) < 4:
            raise AuthorizationDenied("administrative_reason_required")
        self._audit(
            "resource.administrative_action", resource_type=ref.resource_type.value,
            resource_id=ref.resource_id, action=action.value, reason=reason,
            project_id=ref.owner.project_id, summary={"manager_id": ref.owner.manager_id},
        )

    def visible_ids(
        self, resource_type, action: ResourceAction = ResourceAction.READ, *, current_scope: bool = True
    ) -> set[str]:
        """Authorized ids, by default limited to the current personal/project scope.

        List views, searches and counts use this set *before* pagination.
        """
        rtype = self._type(resource_type)
        identity = self.identity_reader.current_identity()
        if not identity.authenticated:
            return set()
        project = requested_project()
        scope_sql, scope_args = "", ()
        if current_scope:
            scope_sql = " AND project_id IS ?"
            scope_args = (project,)
        with self.store._connect() as db:
            rows = db.execute(
                "SELECT resource_id,creator_id,manager_id,project_id,scope,permission_revision "
                "FROM resource_policies WHERE resource_type=? AND (manager_id=? OR scope='project')"
                + scope_sql,
                (rtype.value, identity.user_id, *scope_args),
            ).fetchall()
        visible: set[str] = set()
        for row in rows:
            policy = StoredResourcePolicy(
                resource_type=rtype.value, resource_id=row["resource_id"],
                creator_id=row["creator_id"], manager_id=row["manager_id"],
                project_id=row["project_id"], scope=ResourceScope(row["scope"]),
                permission_revision=row["permission_revision"],
            )
            ref = self._ref_from_policy(rtype, policy)
            if self.authorization.evaluate(ref, action).allowed:
                visible.add(policy.resource_id)
        return visible

    def filter_items(self, resource_type, items: Iterable, key: Callable[[object], str]) -> list:
        visible = self.visible_ids(resource_type)
        return [item for item in items if key(item) in visible]

    def allowed_actions(self, resource_type, resource_id: str) -> list[str]:
        try:
            ref = self.ref(resource_type, resource_id)
        except ResourceNotFound:
            return []
        return sorted(self.authorization.actions(ref))

    def view(self, resource_type, resource_id: str) -> ResourceView:
        rtype = self._type(resource_type)
        policy = self.policy(rtype, resource_id)
        if policy is None:
            raise ResourceNotFound(resource_id)
        return ResourceView(
            resource_type=rtype.value, resource_id=resource_id,
            creator_id=policy.creator_id, manager_id=policy.manager_id,
            project_id=policy.project_id, scope=policy.scope.value,
            permission_revision=policy.permission_revision,
            allowed_actions=tuple(self.allowed_actions(rtype, resource_id)),
        )

    def annotate(self, resource_type, resource_id: str, payload: dict) -> dict:
        """Attach UI-only metadata; the server still rechecks every operation."""
        try:
            view = self.view(resource_type, resource_id)
        except ResourceNotFound:
            return {**payload, "allowed_actions": []}
        return {
            **payload,
            "allowed_actions": list(view.allowed_actions),
            "access": {
                "creator_id": view.creator_id,
                "manager_id": view.manager_id,
                "project_id": view.project_id,
                "scope": view.scope,
                "permission_revision": view.permission_revision,
            },
        }

    # --------------------------------------------------------------- management
    def _update_policy(self, resource_type: ResourceType, resource_id: str, expected_revision: int, **changes) -> StoredResourcePolicy:
        assignments = ", ".join(f"{column}=?" for column in changes)
        with self.store._lock, self.store._connect() as db:
            cursor = db.execute(
                f"UPDATE resource_policies SET {assignments}, permission_revision=permission_revision+1 "
                "WHERE resource_type=? AND resource_id=? AND permission_revision=?",
                (*changes.values(), resource_type.value, resource_id, expected_revision),
            )
            if cursor.rowcount != 1:
                raise ValueError("permission_revision_changed")
        policy = self.policy(resource_type, resource_id)
        assert policy is not None
        return policy

    def _check_dependencies(self, rtype: ResourceType, resource_id: str, target_scope: SharingScope, project_id: str | None):
        if target_scope is not SharingScope.PROJECT:
            return
        for dep_type, dep_id in self.dependencies.get(rtype, lambda _id: [])(resource_id):
            policy = self.policy(dep_type, dep_id)
            if policy is None or policy.scope is not ResourceScope.PROJECT or policy.project_id != project_id:
                raise ValueError(f"dependency_not_shared:{dep_type.value}:{dep_id}")

    def share(self, resource_type, resource_id: str, scope: SharingScope, *, expected_revision: int) -> ResourceView:
        rtype = self._type(resource_type)
        ref = self.require(rtype, resource_id, ResourceAction.SHARE)
        if scope is SharingScope.PROJECT and ref.owner.project_id is None:
            raise ValueError("personal_resource_cannot_be_project_shared")
        self._check_dependencies(rtype, resource_id, scope, ref.owner.project_id)
        self._update_policy(rtype, resource_id, expected_revision, scope=scope.value)
        self._audit(
            "resource.shared" if scope is SharingScope.PROJECT else "resource.unshared",
            resource_type=rtype.value, resource_id=resource_id, action="share",
            reason=scope.value, project_id=ref.owner.project_id,
        )
        return self.view(rtype, resource_id)

    def handover(self, resource_type, resource_id: str, new_manager_id: str, *, expected_revision: int) -> ResourceView:
        rtype = self._type(resource_type)
        ref = self.require(rtype, resource_id, ResourceAction.HANDOVER)
        if not new_manager_id:
            raise ValueError("recipient_required")
        project_id = ref.owner.project_id
        if project_id is None:
            raise ValueError("handover_requires_project_resource")
        lookup = getattr(self.identity_reader, "membership_of", None)
        if not callable(lookup):
            raise AuthorizationDenied("membership_lookup_unavailable")
        membership = lookup(new_manager_id, project_id)
        if membership is None or not membership.active or membership.project_id != project_id:
            raise AuthorizationDenied("recipient_not_project_member")
        # The historical creator keeps attribution only; management moves.
        self._update_policy(rtype, resource_id, expected_revision, manager_id=new_manager_id)
        self._audit(
            "resource.handover", resource_type=rtype.value, resource_id=resource_id,
            action="handover", reason=f"to:{new_manager_id}", project_id=project_id,
        )
        return self.view(rtype, resource_id)

    def takeover(self, resource_type, resource_id: str, *, reason: str, expected_revision: int) -> ResourceView:
        """Explicit, audited platform takeover of a private resource."""
        rtype = self._type(resource_type)
        identity = self.actor()
        if identity.platform_role is not PlatformRole.ADMIN:
            raise AuthorizationDenied("platform_administrator_required")
        if len((reason or "").strip()) < 8:
            raise ValueError("takeover_reason_required")
        policy = self.policy(rtype, resource_id)
        if policy is None:
            raise ResourceNotFound(resource_id)
        self._update_policy(rtype, resource_id, expected_revision, manager_id=identity.user_id)
        self._audit(
            "resource.takeover", resource_type=rtype.value, resource_id=resource_id,
            action="takeover", reason=reason.strip()[:500], project_id=policy.project_id,
            summary={"previous_manager": policy.manager_id},
        )
        return self.view(rtype, resource_id)
