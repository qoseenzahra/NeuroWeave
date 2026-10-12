"""Workflows HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query

from ..access.contracts import ResourceAction
from ..application_services import ApplicationServices
from ..models import ChatRequest
from ..task_contract import PlanNotMatched
from ..workflow_models import (
    MethodSelectionRequest,
    Workflow,
    WorkflowDatasetRequest,
    WorkflowDraftRequest,
    WorkflowMutationRequest,
)
from ..workflow_service import RevisionConflict
from .errors import revision_http_error
from .guards import TASK, access, require_inputs, require_task, visible_tasks

READ, UPDATE = ResourceAction.READ, ResourceAction.UPDATE


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/api/workflows/draft", response_model=Workflow)
    async def draft_workflow(request: WorkflowDraftRequest) -> Workflow:
        payload = request.model_dump()
        require_inputs(
            services,
            dataset_id=payload.get("dataset_id"),
            workspace_id=payload.get("workspace_id"),
            conversation_id=payload.get("conversation_id"),
        )
        try:
            workflow, _content = await services.workflow_service.draft(
                services.chat_coordinator.resolve_context(
                    ChatRequest(**request.model_dump())
                )
            )
            return workflow
        except PlanNotMatched as exc:
            raise HTTPException(
                status_code=422,
                detail={
                    "status": "candidate_mismatch",
                    "message": str(exc),
                    "diagnostics": exc.diagnostics,
                },
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"模型服务请求失败（HTTP {exc.response.status_code}）",
            ) from exc
        except (
            httpx.RequestError,
            RuntimeError,
            KeyError,
            IndexError,
            TypeError,
        ) as exc:
            raise HTTPException(status_code=502, detail=f"无法生成流程：{exc}") from exc

    @router.get("/api/workflow-index")
    def workflow_index(
        offset: int = Query(0, ge=0),
        limit: int = Query(30, ge=1, le=100),
        q: str = Query("", max_length=200),
        source: Literal["", "pipeline", "conversation"] = "",
        status: Literal["", "draft", "active", "succeeded", "failed", "cancelled"] = "",
        view: Literal["", "mine", "project"] = "",
    ):
        # Filter by permission (and "My tasks / Project tasks") before paging.
        result = services.local_store.workflow_index(
            offset=offset, limit=limit, query=q, source=source, status=status,
            visible_ids=visible_tasks(services, view),
        )
        result["items"] = [
            access(services).annotate(TASK, item["workflow_id"], item) for item in result["items"]
        ]
        return result

    @router.get("/api/workflows/{workflow_id}", response_model=Workflow)
    def get_workflow(workflow_id: str) -> Workflow:
        require_task(services, workflow_id, READ)
        try:
            return services.workflow_service.get(workflow_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc

    @router.get("/api/workflows")
    def list_workflows(limit: int = 50) -> dict[str, list[Workflow]]:
        return {"workflows": services.workflow_service.list(limit, visible_ids=visible_tasks(services))}

    @router.get("/api/workflows/{workflow_id}/events")
    def workflow_events(workflow_id: str) -> dict[str, Any]:
        require_task(services, workflow_id, READ)
        try:
            return {"events": services.workflow_service.events(workflow_id)}
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc

    @router.patch(
        "/api/workflows/{workflow_id}/steps/{step_id}/method", response_model=Workflow
    )
    def select_workflow_method(
        workflow_id: str,
        step_id: str,
        request: MethodSelectionRequest,
    ) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            return services.workflow_service.select_method(
                workflow_id,
                step_id,
                request.method_id,
                request.expected_revision,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/workflows/{workflow_id}/lock", response_model=Workflow)
    def lock_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            return services.workflow_service.lock_chain(
                workflow_id, request.expected_revision
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.patch("/api/workflows/{workflow_id}/dataset", response_model=Workflow)
    def change_workflow_dataset(
        workflow_id: str, request: WorkflowDatasetRequest
    ) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        require_inputs(services, dataset_id=request.dataset_id)
        try:
            return services.workflow_service.change_dataset(
                workflow_id,
                request.dataset_id,
                request.expected_revision,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Workflow or dataset not found"
            ) from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/workflows/{workflow_id}/unlock", response_model=Workflow)
    def unlock_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            return services.workflow_service.unlock_chain(
                workflow_id, request.expected_revision
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/api/workflows/{workflow_id}/steps/{step_id}/remove", response_model=Workflow
    )
    def remove_workflow_step(
        workflow_id: str, step_id: str, request: WorkflowMutationRequest
    ) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            return services.workflow_service.remove_step(
                workflow_id, step_id, request.expected_revision
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Workflow or step not found"
            ) from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/workflows/{workflow_id}/replan", response_model=Workflow)
    async def replan_workflow(
        workflow_id: str, request: WorkflowMutationRequest
    ) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            workflow, _content = await services.workflow_service.replan(
                workflow_id,
                request.expected_revision,
            )
            return workflow
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post(
        "/api/workflows/{workflow_id}/complete-dependencies", response_model=Workflow
    )
    async def complete_workflow_dependencies(
        workflow_id: str,
        request: WorkflowMutationRequest,
    ) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            return await services.workflow_service.complete_dependencies(
                workflow_id,
                request.expected_revision,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
