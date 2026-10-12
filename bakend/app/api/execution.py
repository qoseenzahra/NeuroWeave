"""Execution HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Query

from ..access.contracts import AuthorizationDenied, ResourceAction, ResourceType
from ..access.filesystem import GrantScope
from ..application_services import ApplicationServices
from ..execution import RunConflict
from ..run_models import (
    ExecutionDraftRequest,
    RunCreateRequest,
    RunRetryRequest,
    WorkflowRun,
)
from ..workflow_models import (
    Workflow,
    WorkflowConfirmRequest,
    WorkflowMutationRequest,
)
from ..workflow_service import RevisionConflict
from .errors import revision_http_error, submit_operation
from .guards import access, require_run, require_task, run_task_id, visible_tasks

READ, UPDATE = ResourceAction.READ, ResourceAction.UPDATE


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    def execution_scope(workflow_id: str, workflow, action: ResourceAction) -> dict:
        """Check current identity, role, inputs, historical artifacts and output.

        Returns the scope frozen into the accepted run. Nothing here is taken
        from the client except the requested project, which is membership-checked.
        """
        resource_access = access(services)
        ref = require_task(services, workflow_id, action)
        identity = resource_access.actor()
        project_id = resource_access.current_project()
        if ref.owner.project_id != project_id:
            # Removed membership, archival or a switched scope blocks new work.
            raise AuthorizationDenied("wrong_project")
        if workflow.dataset_id:
            resource_access.require(ResourceType.DATASET, workflow.dataset_id, READ)
        history_runs = sorted({
            binding.history.run_id
            for step in workflow.steps
            for binding in step.input_bindings.values()
            if binding.history is not None
        })
        for run_id in history_runs:
            require_run(services, run_id, READ)
        if not workflow.workspace_id or not workflow.workspace_root_path:
            raise ValueError("请先选择服务器输出目录，再提交运行")
        output_ref = resource_access.require(ResourceType.OUTPUT, workflow.workspace_id, UPDATE)
        try:
            grant = services.directory_access.grant_token(Path(workflow.workspace_root_path), GrantScope.WRITE)
        except PermissionError as exc:
            raise AuthorizationDenied("output_write_denied") from exc
        return {
            "submitter_id": identity.user_id,
            "project_id": project_id,
            "workflow_id": workflow_id,
            "workflow_revision": workflow.revision,
            "task_permission_revision": ref.owner.permission_revision,
            "dataset_id": workflow.dataset_id,
            "historical_run_ids": history_runs,
            "output_workspace_id": workflow.workspace_id,
            "output_root": workflow.workspace_root_path,
            "output_permission_revision": output_ref.owner.permission_revision,
            "output_grant": grant,
        }

    def reserve(workflow_id: str, scope: dict, execution, idempotency_key: str | None) -> dict:
        key = (idempotency_key or "").strip()[:200] or ("auto:" + uuid4().hex)
        return services.execution_control.reserve(
            workflow_id=workflow_id,
            submitter_id=scope["submitter_id"],
            project_id=scope["project_id"],
            idempotency_key=key,
            execution=execution,
            frozen_scope=scope,
        )

    def replayed(reservation: dict) -> WorkflowRun:
        if not reservation.get("run_id"):
            raise HTTPException(409, "The same submission is still being accepted")
        require_run(services, reservation["run_id"], READ)
        return services.run_service.get(reservation["run_id"])

    def audit_run(event: str, run_id: str, scope: dict, action: str) -> None:
        access(services)._audit(
            event, resource_type="run", resource_id=run_id, action=action,
            reason="accepted", project_id=scope.get("project_id"),
            summary={"workflow_id": scope.get("workflow_id"), "units": scope.get("units")},
        )

    @router.post("/api/workflows/{workflow_id}/dry-run-jobs", status_code=202)
    def dry_run_job(
        workflow_id: str, request: WorkflowMutationRequest
    ) -> dict[str, Any]:
        require_task(services, workflow_id, UPDATE)
        return submit_operation(
            services.operation_service,
            "workflow_dry_run",
            f"{workflow_id}:{request.expected_revision}",
            lambda: services.workflow_service.dry_run(
                workflow_id, request.expected_revision
            ),
            owner_id=access(services).actor().user_id,
        )

    @router.post("/api/workflows/{workflow_id}/dry-run", response_model=Workflow)
    def dry_run_workflow(
        workflow_id: str, request: WorkflowMutationRequest
    ) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            return services.workflow_service.dry_run(
                workflow_id, request.expected_revision
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/workflows/{workflow_id}/confirm", response_model=Workflow)
    def confirm_workflow(workflow_id: str, request: WorkflowConfirmRequest) -> Workflow:
        require_task(services, workflow_id, UPDATE)
        try:
            return services.workflow_service.confirm(
                workflow_id, request.expected_revision, request.acknowledge_quality
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except RevisionConflict as exc:
            raise revision_http_error(exc) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.get("/api/workflows/{workflow_id}/execution-draft")
    def get_execution_draft(workflow_id: str) -> dict[str, Any]:
        require_task(services, workflow_id, READ)
        if services.local_store.get_workflow(workflow_id) is None:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return services.local_store.execution_draft(workflow_id)

    @router.put("/api/workflows/{workflow_id}/execution-draft")
    def put_execution_draft(
        workflow_id: str, request: ExecutionDraftRequest
    ) -> dict[str, Any]:
        # Background autosave is a modification like any other save.
        require_task(services, workflow_id, UPDATE)
        try:
            return services.local_store.save_execution_draft(
                workflow_id,
                request.expected_revision,
                request.expected_draft_revision,
                request.execution,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/workflows/{workflow_id}/runs", response_model=WorkflowRun)
    def start_workflow_run(
        workflow_id: str,
        request: RunCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> WorkflowRun:
        require_task(services, workflow_id, ResourceAction.SUBMIT)
        try:
            workflow = services.workflow_service.get(workflow_id)
            scope = execution_scope(workflow_id, workflow, ResourceAction.SUBMIT)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        try:
            reservation = reserve(workflow_id, scope, request.execution, idempotency_key)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if reservation["replayed"]:
            return replayed(reservation)
        try:
            # New submissions must have an explicit output selection. Existing runs
            # and retries keep the immutable output snapshot saved with their run.
            with (
                services.run_service.mutation_lock,
                services.workflow_service.mutation_lock,
            ):
                workflow = services.workflow_service.get(workflow_id)
                if workflow.revision != scope["workflow_revision"]:
                    raise ValueError("流程版本已变化，请刷新后重新提交")
                if not workflow.workspace_id or not workflow.workspace_root_path:
                    raise ValueError("请先选择服务器输出目录，再提交运行")
                selected = services.workspace_service.get(workflow.workspace_id)
                if (
                    Path(selected.root_path).resolve()
                    != Path(workflow.workspace_root_path).resolve()
                ):
                    raise ValueError("输出目录已变化，请重新选择并检查流程")
                services.workspace_service.validate_output_directory(
                    Path(selected.root_path)
                )
                run = services.run_service.create(
                    workflow_id, request.expected_revision, request.execution
                )
        except KeyError as exc:
            services.execution_control.release(reservation["reservation_id"])
            raise HTTPException(status_code=404, detail="Workflow not found") from exc
        except (RunConflict, ValueError, OSError) as exc:
            services.execution_control.release(reservation["reservation_id"])
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except BaseException:
            services.execution_control.release(reservation["reservation_id"])
            raise
        services.execution_control.bind_run(reservation["reservation_id"], run.run_id)
        audit_run("run.submitted", run.run_id, {**scope, "units": reservation.get("units")}, "submit")
        return run

    @router.get("/api/runs")
    def list_runs(
        workflow_id: str | None = None,
        limit: int = 50,
        summary: bool = False,
        offset: int = Query(0, ge=0),
        view: str = Query("", pattern="^(|mine|project)$"),
    ) -> dict[str, Any]:
        if workflow_id:
            require_task(services, workflow_id, READ)
        # Runs inherit task permission; the filter is applied before paging.
        return {
            "runs": services.local_store.list_runs(
                workflow_id=workflow_id, limit=limit, summary=summary, offset=offset,
                visible_task_ids=visible_tasks(services, view),
            )
        }

    @router.get("/api/execution/backends")
    def execution_backends() -> dict[str, Any]:
        return services.run_service.execution_backends()

    @router.get("/api/runs/{run_id}", response_model=WorkflowRun)
    def get_run(run_id: str) -> WorkflowRun:
        require_run(services, run_id, READ)
        try:
            return services.run_service.get(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @router.get("/api/runs/{run_id}/events")
    def run_events(
        run_id: str,
        after_event_id: int = 0,
        before_event_id: int | None = Query(None, ge=1),
        tail: bool = False,
        limit: int = Query(1000, ge=1, le=1000),
    ) -> dict[str, Any]:
        require_run(services, run_id, READ)
        try:
            return services.local_store.run_event_page(
                run_id,
                after_event_id=after_event_id,
                before_event_id=before_event_id,
                tail=tail,
                limit=limit,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @router.get("/api/runs/{run_id}/monitor")
    def monitor_run(run_id: str, after_revision: int = -1) -> dict[str, Any]:
        require_run(services, run_id, READ)
        try:
            return services.local_store.monitor_run(run_id, after_revision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc

    @router.post("/api/runs/{run_id}/cancel", response_model=WorkflowRun)
    def cancel_run(run_id: str) -> WorkflowRun:
        # Research members cannot cancel somebody else's task; project
        # administrators may, for project-shared tasks only.
        require_run(services, run_id, ResourceAction.CANCEL)
        try:
            run = services.run_service.cancel(run_id)
            actor = access(services).actor().user_id
            services.execution_control.record_cancellation(run_id, actor)
            access(services)._audit(
                "run.cancel_requested", resource_type="run", resource_id=run_id,
                action="cancel", reason="requested", project_id=access(services).current_project(),
            )
            return run
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/runs/{run_id}/retry", response_model=WorkflowRun)
    def retry_run(
        run_id: str,
        request: RunRetryRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> WorkflowRun:
        workflow_id = run_task_id(services, run_id)
        require_task(services, workflow_id, ResourceAction.RETRY)
        try:
            original = services.run_service.get(run_id)
            # A retry re-executes the original snapshot, so its inputs and output
            # are rechecked against the *current* identity and grants.
            workflow = Workflow.model_validate(original.plan_snapshot)
            scope = execution_scope(workflow_id, workflow, ResourceAction.RETRY)
            scope = {**scope, "retry_of": run_id, "workflow_revision": original.workflow_revision}
            reservation = reserve(workflow_id, scope, original.execution, idempotency_key)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        if reservation["replayed"]:
            return replayed(reservation)
        try:
            run = services.run_service.retry(
                run_id, request.step_ids, request.sample_ids
            )
        except KeyError as exc:
            services.execution_control.release(reservation["reservation_id"])
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except (RunConflict, ValueError, OSError) as exc:
            services.execution_control.release(reservation["reservation_id"])
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except BaseException:
            services.execution_control.release(reservation["reservation_id"])
            raise
        services.execution_control.bind_run(reservation["reservation_id"], run.run_id)
        audit_run("run.retried", run.run_id, {**scope, "units": reservation.get("units")}, "retry")
        return run

    @router.get("/api/runs/{run_id}/authorization")
    def run_authorization(run_id: str) -> dict[str, Any]:
        """Submitter, cancellation actor and the frozen execution scope."""
        require_run(services, run_id, READ)
        record = services.execution_control.for_run(run_id)
        if record is None:
            return {"run_id": run_id, "recorded": False}
        return {"recorded": True, **record}

    @router.post("/api/runs/{run_id}/recover-freesurfer")
    def recover_freesurfer_run(
        run_id: str,
        request: RunCreateRequest,
        dry_run: bool = True,
    ) -> dict[str, Any]:
        require_run(services, run_id, READ if dry_run else ResourceAction.RETRY)
        try:
            return services.run_service.recover_freesurfer(
                run_id, request.expected_revision, dry_run=dry_run
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @router.post("/api/runs/{run_id}/resume-monitoring", response_model=WorkflowRun)
    def resume_slurm_monitoring(run_id: str) -> WorkflowRun:
        require_run(services, run_id, UPDATE)
        try:
            return services.run_service.resume_slurm_monitoring(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except RunConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return router
