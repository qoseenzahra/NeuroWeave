"""Workflow Inputs HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..access.contracts import AuthorizationDenied, ResourceAction, ResourceType
from ..access.filesystem import GrantScope
from ..application_services import ApplicationServices
from ..dataset_files import protect_datasets
from ..dataset_models import (
    DatasetPathPreview,
)
from ..historical_inputs import HistoricalSelectionRequest
from ..workflow_models import (
    InputBindingRequest,
    InputPreviewRequest,
    ParameterUpdateRequest,
    Workflow,
    WorkflowMutationRequest,
)
from ..workflow_service import RevisionConflict
from ..workflows import contracts
from ..workspace_models import WorkflowOutputRequest
from .errors import revision_http_error
from .guards import access, require_task


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    def require_input_path(root_id: str, relative_path: str) -> None:
        """Typed or selected input paths use the same live directory scope."""
        try:
            _root, candidate, _normalized = services.dataset_service.resolve_artifact_path(
                root_id, relative_path
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if services.directory_access is None:
            raise AuthorizationDenied("authentication_required")
        try:
            services.directory_access.require(candidate, GrantScope.READ)
        except PermissionError as exc:
            raise AuthorizationDenied(str(exc)) from exc

    @router.patch(
        "/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}",
        response_model=Workflow,
    )
    def bind_workflow_input(
        workflow_id: str,
        step_id: str,
        slot_id: str,
        request: InputBindingRequest,
    ) -> Workflow:
        require_task(services, workflow_id, ResourceAction.UPDATE)
        require_input_path(request.root_id, request.relative_path)
        try:
            return services.workflow_service.bind_input(
                workflow_id,
                step_id,
                slot_id,
                request.root_id,
                request.relative_path,
                request.expected_revision,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/preview",
        response_model=DatasetPathPreview,
    )
    def preview_workflow_input(
        workflow_id: str,
        step_id: str,
        slot_id: str,
        request: InputPreviewRequest,
    ) -> DatasetPathPreview:
        require_task(services, workflow_id, ResourceAction.READ)
        require_input_path(request.root_id, request.relative_path)
        try:
            return services.workflow_service.preview_input_mapping(
                workflow_id,
                step_id,
                slot_id,
                request.root_id,
                request.relative_path,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Workflow or dataset not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get("/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/history")
    def historical_input_candidates(
        workflow_id: str,
        step_id: str,
        slot_id: str,
        offset: int = Query(0, ge=0, le=1000000),
    ):
        require_task(services, workflow_id, ResourceAction.READ)
        try:
            return services.workflow_service.historical_input_candidates(
                workflow_id, step_id, slot_id, offset
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/history/preview"
    )
    def preview_historical_input(
        workflow_id: str,
        step_id: str,
        slot_id: str,
        request: HistoricalSelectionRequest,
    ):
        require_task(services, workflow_id, ResourceAction.READ)
        try:
            return services.workflow_service.preview_historical_input(
                workflow_id, step_id, slot_id, request
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Workflow or historical run not found"
            ) from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/history",
        response_model=Workflow,
    )
    def bind_historical_input(
        workflow_id: str,
        step_id: str,
        slot_id: str,
        request: HistoricalSelectionRequest,
    ):
        require_task(services, workflow_id, ResourceAction.UPDATE)
        try:
            return services.workflow_service.bind_historical_input(
                workflow_id, step_id, slot_id, request
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Workflow or historical run not found"
            ) from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.patch(
        "/api/workflows/{workflow_id}/steps/{step_id}/parameters",
        response_model=Workflow,
    )
    def update_workflow_parameters(
        workflow_id: str,
        step_id: str,
        request: ParameterUpdateRequest,
    ) -> Workflow:
        require_task(services, workflow_id, ResourceAction.UPDATE)
        try:
            return services.workflow_service.update_parameters(
                workflow_id,
                step_id,
                request.parameters,
                request.expected_revision,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.post(
        "/api/workflows/{workflow_id}/review-parameters", response_model=Workflow
    )
    def review_workflow_parameters(
        workflow_id: str,
        request: WorkflowMutationRequest,
    ) -> Workflow:
        require_task(services, workflow_id, ResourceAction.UPDATE)
        try:
            return services.workflow_service.review_parameters(
                workflow_id, request.expected_revision
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.patch("/api/workflows/{workflow_id}/output", response_model=Workflow)
    def set_workspace_output(workflow_id: str, request: WorkflowOutputRequest):
        require_task(services, workflow_id, ResourceAction.UPDATE)
        if request.workspace_id:
            # Selecting an output is a write intent: object permission now, and
            # the live write grant is rechecked again at run submission.
            access(services).require(ResourceType.OUTPUT, request.workspace_id, ResourceAction.UPDATE)
        if request.conversation_id:
            access(services).require(ResourceType.CONVERSATION, request.conversation_id, ResourceAction.UPDATE)
        try:
            with (
                services.run_service.mutation_lock,
                services.workflow_service.mutation_lock,
            ):
                if (
                    request.conversation_id
                    and not services.local_store.get_conversation(
                        request.conversation_id
                    )
                ):
                    raise ValueError("对话不存在")
                workflow = services.workflow_service.get(workflow_id)
                if workflow.revision != request.expected_revision:
                    raise ValueError("流程版本已变化，请刷新")
                if (
                    workflow.status == "confirmed"
                    or services.local_store.active_run_for_workflow(workflow_id)
                ):
                    raise ValueError("请先解锁流程；已有任务的输出目录不受后续修改影响")
                if "workspace_id" in request.model_fields_set:
                    selected = (
                        services.workspace_service.get(request.workspace_id)
                        if request.workspace_id
                        else None
                    )
                    workflow.workspace_id = selected.id if selected else None
                    workflow.workspace_root_path = (
                        selected.root_path if selected else None
                    )
                if workflow.workspace_root_path:
                    root = services.workspace_service.validate_output_directory(
                        Path(workflow.workspace_root_path)
                    )
                    output = services.workspace_service.paths.output_root(
                        str(root), request.relative_path
                    )
                    protect_datasets(services.local_store, output)
                    workflow.output_relative_path = str(output.relative_to(root))
                elif "workspace_id" in request.model_fields_set:
                    output = services.settings.output_root
                    workflow.output_relative_path = "outputs"
                else:
                    raise ValueError("请先选择输出目录")
                contracts.advance(workflow)
                workflow.dry_run_report = None
                services.workflow_service.state.refresh(workflow)
                services.local_store.save_workflow(
                    workflow,
                    event_type="workspace_output_changed",
                    event_payload={"path": str(output)},
                )
                if (
                    "workspace_id" in request.model_fields_set
                    and request.conversation_id
                ):
                    services.workspace_service.bind_conversation(
                        request.conversation_id, request.workspace_id
                    )
                return workflow
        except (ValueError, KeyError, OSError) as exc:
            raise HTTPException(409, str(exc)) from exc

    return router
