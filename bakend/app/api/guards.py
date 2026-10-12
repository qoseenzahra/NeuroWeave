"""Small shared authorization helpers for business routers.

Routers call these at the top of every handler so the rule protecting each
entry point is explicit. Runs and historical results inherit their task.
"""

from __future__ import annotations

from ..access.contracts import AuthorizationDenied, ResourceAction, ResourceNotFound, ResourceType
from ..application_services import ApplicationServices

TASK = ResourceType.TASK


def access(services: ApplicationServices):
    if services.resource_access is None:
        raise AuthorizationDenied("authentication_required")
    return services.resource_access


def require_task(services: ApplicationServices, workflow_id: str, action: ResourceAction):
    return access(services).require(TASK, workflow_id, action)


def run_task_id(services: ApplicationServices, run_id: str) -> str:
    with services.local_store._connect() as db:
        row = db.execute("SELECT workflow_id FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        raise ResourceNotFound(run_id)
    return row["workflow_id"]


def require_run(services: ApplicationServices, run_id: str, action: ResourceAction):
    return require_task(services, run_task_id(services, run_id), action)


def visible_tasks(services: ApplicationServices, view: str = "") -> set[str]:
    """Authorized task ids, optionally narrowed to "mine" or "project" views."""
    resource_access = access(services)
    visible = resource_access.visible_ids(TASK)
    if view not in {"mine", "project"}:
        return visible
    identity = resource_access.actor()
    project = resource_access.current_project()
    narrowed = set()
    for task_id in visible:
        policy = resource_access.policy(TASK, task_id)
        if policy is None:
            continue
        if view == "mine" and policy.manager_id == identity.user_id:
            narrowed.add(task_id)
        elif view == "project" and project is not None and policy.project_id == project:
            narrowed.add(task_id)
    return narrowed


def require_inputs(services: ApplicationServices, *, dataset_id=None, workspace_id=None, conversation_id=None):
    resource_access = access(services)
    if dataset_id:
        resource_access.require(ResourceType.DATASET, dataset_id, ResourceAction.READ)
    if workspace_id:
        resource_access.require(ResourceType.OUTPUT, workspace_id, ResourceAction.READ)
    if conversation_id:
        resource_access.require(ResourceType.CONVERSATION, conversation_id, ResourceAction.UPDATE)
