"""Resource dependency graph used by sharing and handover (brief B6).

* Sharing a task with the project requires every resource it depends on
  (dataset, output directory, historical runs' tasks) to be shared with the
  same project already.
* Unsharing a dataset or output that a project-shared task still uses is
  refused, so project members never lose access to the inputs of a task they
  can see.
* Handing a resource over requires the new manager to be able to read each
  dependency (shared with the project or already managed by them).

Only database relationships are read; no files are touched.
"""

from __future__ import annotations

import json

from .contracts import ResourceType


def _workflow(store, workflow_id: str):
    try:
        return store.get_workflow(workflow_id)
    except Exception:  # noqa: BLE001 - corrupt payloads are not dependencies
        return None


def task_dependencies(store, workflow_id: str) -> list[tuple[ResourceType, str]]:
    workflow = _workflow(store, workflow_id)
    if workflow is None:
        return []
    found: list[tuple[ResourceType, str]] = []
    if workflow.dataset_id:
        found.append((ResourceType.DATASET, workflow.dataset_id))
    if workflow.workspace_id:
        found.append((ResourceType.OUTPUT, workflow.workspace_id))
    for step in workflow.steps:
        for binding in step.input_bindings.values():
            history = getattr(binding, "history", None)
            if history is None or not history.run_id:
                continue
            run = store.get_run(history.run_id)
            if run is not None and run.workflow_id != workflow_id:
                found.append((ResourceType.TASK, run.workflow_id))
    seen: set[tuple[ResourceType, str]] = set()
    return [item for item in found if not (item in seen or seen.add(item))]


def dependent_tasks(store, resource_type: ResourceType, resource_id: str) -> list[tuple[ResourceType, str]]:
    """Tasks that use ``resource_id`` (dataset, output or another task's runs)."""
    with store._connect() as db:
        rows = db.execute("SELECT workflow_id, dataset_id, payload_json FROM workflows").fetchall()
    found = []
    for row in rows:
        if row["workflow_id"] == resource_id and resource_type is ResourceType.TASK:
            continue
        if resource_type is ResourceType.DATASET and row["dataset_id"] == resource_id:
            found.append((ResourceType.TASK, row["workflow_id"]))
            continue
        try:
            payload = json.loads(row["payload_json"])
        except ValueError:
            continue
        if resource_type is ResourceType.OUTPUT and payload.get("workspace_id") == resource_id:
            found.append((ResourceType.TASK, row["workflow_id"]))
        elif resource_type in (ResourceType.DATASET, ResourceType.TASK):
            if resource_type is ResourceType.TASK and any(
                dep == (ResourceType.TASK, resource_id)
                for dep in task_dependencies(store, row["workflow_id"])
            ):
                found.append((ResourceType.TASK, row["workflow_id"]))
    return found


def install(resource_access, store) -> None:
    resource_access.dependencies[ResourceType.TASK] = lambda task_id: task_dependencies(store, task_id)
    for rtype in (ResourceType.DATASET, ResourceType.OUTPUT, ResourceType.TASK):
        resource_access.dependents[rtype] = (
            lambda resource_id, _type=rtype: dependent_tasks(store, _type, resource_id)
        )
