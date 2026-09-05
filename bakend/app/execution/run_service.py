from __future__ import annotations

import os
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock
from typing import Any
from uuid import uuid4

from ..capability_registry import CapabilityRegistry
from ..local_store import LocalStore
from ..run_models import RunArtifact, RunStep, WorkflowRun
from ..workflow_models import MethodOption, Workflow, WorkflowStep
from .base import ExecutionCancelled, RunnerContext
from .recipe_compiler import ExecutionUnit, RecipeCompilationError, RecipeCompiler
from .runner_registry import RunnerRegistry


class RunConflict(RuntimeError):
    pass


class RunService:
    """Durable background execution of immutable, confirmed workflow snapshots."""

    def __init__(
        self,
        store: LocalStore,
        capability_registry: CapabilityRegistry,
        runner_registry: RunnerRegistry,
        output_root: Path,
    ) -> None:
        self.store = store
        self.capability_registry = capability_registry
        self.runner_registry = runner_registry
        self.output_root = output_root.resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.recipe_compiler = RecipeCompiler(capability_registry)
        max_workers = max(1, min(int(os.getenv("LOCALFLOW_RUN_WORKERS", "2")), 16))
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="localflow-run",
        )
        self._lock = RLock()
        self._cancel_events: dict[str, Event] = {}
        self._futures: dict[str, Future[None]] = {}
        self.store.fail_incomplete_runs(
            self._now(),
            "backend_restarted",
            "后端重启时任务仍处于运行状态；请确认输出后重新运行。",
        )

    @property
    def enabled(self) -> bool:
        return bool(self.runner_registry.available_ids())

    def create(self, workflow_id: str, expected_revision: int) -> WorkflowRun:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(workflow_id)
        if workflow.revision != expected_revision:
            raise RunConflict(
                f"流程版本已变化：请求 R{expected_revision}，当前为 R{workflow.revision}"
            )
        if workflow.status != "confirmed":
            raise RunConflict("只有已经最终确认的流程才能开始运行")
        if workflow.dry_run_report is None or not workflow.dry_run_report.valid:
            raise RunConflict("流程尚未通过 Dry-run")
        if not workflow.dry_run_report.execution_enabled:
            raise RunConflict("当前流程包含尚未接入实际执行器的方法")

        active = self.store.active_run_for_workflow(workflow_id)
        if active is not None:
            raise RunConflict(f"该流程已有活动任务：{active.run_id}")

        try:
            resolved = self.recipe_compiler.compile(workflow)
        except RecipeCompilationError as exc:
            raise RunConflict(str(exc)) from exc
        for unit in resolved:
            step, method = unit.step, unit.method
            if method.execution_mode != "runner":
                raise RunConflict(f"步骤 {step.title} 仍是规划型方法，不能执行")
            if self.runner_registry.get(method.runner_id) is None:
                raise RunConflict(f"步骤 {step.title} 的 runner 尚未注册：{method.runner_id}")

        now = self._now()
        run_id = f"run_{uuid4().hex[:12]}"
        output_directory = self._safe_run_directory(run_id)
        run = WorkflowRun(
            run_id=run_id,
            workflow_id=workflow.workflow_id,
            workflow_revision=workflow.revision,
            status="queued",
            progress=0.0,
            output_directory=str(output_directory),
            plan_snapshot=workflow.model_dump(mode="json"),
            steps=[
                RunStep(
                    step_id=step.id,
                    title=step.title,
                    runner_id=method.runner_id,
                    method_id=method.id,
                )
                for unit in resolved
                for step, method in [(unit.step, unit.method)]
            ],
            created_at=now,
            updated_at=now,
        )
        self.store.save_run(
            run,
            event_type="run_queued",
            event_message="任务已进入本地执行队列",
        )
        cancel_event = Event()
        with self._lock:
            self._cancel_events[run_id] = cancel_event
            self._futures[run_id] = self._executor.submit(
                self._execute,
                run_id,
                workflow,
                resolved,
                cancel_event,
            )
        return self.get(run_id)

    def get(self, run_id: str) -> WorkflowRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return run

    def list(self, workflow_id: str | None = None, limit: int = 50) -> list[WorkflowRun]:
        return self.store.list_runs(workflow_id=workflow_id, limit=limit)

    def events(self, run_id: str, after_event_id: int = 0) -> list[dict[str, Any]]:
        if self.store.get_run(run_id) is None:
            raise KeyError(run_id)
        return self.store.run_events(run_id, after_event_id=after_event_id)

    def cancel(self, run_id: str) -> WorkflowRun:
        with self._lock:
            run = self.get(run_id)
            if run.status not in {"queued", "running", "cancel_requested"}:
                raise RunConflict("该任务已经结束，不能取消")
            event = self._cancel_events.get(run_id)
            if event is not None:
                event.set()
            run.status = "cancel_requested"
            run.cancellation_requested = True
            run.updated_at = self._now()
            self.store.save_run(
                run,
                event_type="cancellation_requested",
                event_message="已请求取消任务，正在等待当前安全检查点",
                level="warning",
            )
        return run

    def shutdown(self) -> None:
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _execute(
        self,
        run_id: str,
        workflow: Workflow,
        resolved: list[ExecutionUnit],
        cancel_event: Event,
    ) -> None:
        run = self.get(run_id)
        try:
            run.status = "running"
            run.started_at = self._now()
            run.updated_at = run.started_at
            self.store.save_run(
                run,
                event_type="run_started",
                event_message="本地 Worker 已开始执行",
            )
            step_total = max(len(resolved), 1)
            for step_index, unit in enumerate(resolved):
                workflow_step, method = unit.step, unit.method
                if cancel_event.is_set():
                    raise ExecutionCancelled("任务在步骤开始前被取消")
                step_run = run.steps[step_index]
                step_run.status = "running"
                step_run.started_at = self._now()
                step_run.message = "正在执行"
                run.current_step_id = step_run.step_id
                run.updated_at = step_run.started_at
                self.store.save_run(
                    run,
                    event_type="step_started",
                    event_message=f"开始执行：{step_run.title}",
                    step_id=step_run.step_id,
                )

                runner = self.runner_registry.get(method.runner_id)
                if runner is None:
                    raise RuntimeError(f"未注册 runner：{method.runner_id}")
                step_directory = self._safe_step_directory(run_id, unit.workspace_key)

                def log(message: str, progress: float | None, level: str) -> None:
                    if cancel_event.is_set():
                        raise ExecutionCancelled("任务已由用户取消")
                    if progress is not None:
                        step_run.progress = max(0.0, min(float(progress), 100.0))
                        run.progress = (
                            (step_index + step_run.progress / 100.0) / step_total * 100.0
                        )
                    step_run.message = message
                    run.updated_at = self._now()
                    self.store.save_run(run)
                    self.store.append_run_event(
                        run_id,
                        event_type="runner_log",
                        message=message,
                        level=level,
                        progress=run.progress,
                        step_id=step_run.step_id,
                    )

                runtime_step = self._resolve_runtime_bindings(workflow_step, run)
                context = RunnerContext(
                    run_id=run_id,
                    workflow=workflow,
                    step=runtime_step,
                    method=method,
                    output_directory=step_directory,
                    cancel_event=cancel_event,
                    log=log,
                )
                problems = runner.preflight(context)
                if problems:
                    raise RuntimeError("；".join(problems))
                result = runner.run(context)
                if cancel_event.is_set():
                    raise ExecutionCancelled("任务在步骤完成时被用户取消")
                step_run.status = "succeeded"
                step_run.progress = 100.0
                step_run.message = result.message
                step_run.finished_at = self._now()
                self._annotate_output_slots(method, result.artifacts)
                step_run.artifacts = result.artifacts
                run.artifacts.extend(result.artifacts)
                run.progress = (step_index + 1) / step_total * 100.0
                run.updated_at = step_run.finished_at
                self.store.save_run(
                    run,
                    event_type="step_succeeded",
                    event_message=result.message,
                    step_id=step_run.step_id,
                    event_payload={
                        "artifact_ids": [artifact.artifact_id for artifact in result.artifacts]
                    },
                )

            run.status = "succeeded"
            run.progress = 100.0
            run.current_step_id = None
            run.finished_at = self._now()
            run.updated_at = run.finished_at
            self.store.save_run(
                run,
                event_type="run_succeeded",
                event_message=f"任务完成，共生成 {len(run.artifacts)} 个制品",
            )
        except ExecutionCancelled as exc:
            self._finish_cancelled(run, str(exc))
        except Exception as exc:  # noqa: BLE001 - persist runner failures as structured state
            active_step = next(
                (step for step in run.steps if step.status == "running"),
                None,
            )
            if active_step is not None:
                active_step.status = "failed"
                active_step.error_code = "runner_failed"
                active_step.error_message = str(exc)
                active_step.message = "执行失败"
                active_step.finished_at = self._now()
            run.status = "failed"
            run.error_code = "runner_failed"
            run.error_message = str(exc)
            run.finished_at = self._now()
            run.updated_at = run.finished_at
            self.store.save_run(
                run,
                event_type="run_failed",
                event_message=str(exc),
                level="error",
            )
        finally:
            with self._lock:
                self._cancel_events.pop(run_id, None)
                self._futures.pop(run_id, None)

    def _finish_cancelled(self, run: WorkflowRun, message: str) -> None:
        active_step = next((step for step in run.steps if step.status == "running"), None)
        if active_step is not None:
            active_step.status = "cancelled"
            active_step.message = message
            active_step.finished_at = self._now()
        run.status = "cancelled"
        run.cancellation_requested = True
        run.current_step_id = None
        run.error_code = "cancelled"
        run.error_message = message
        run.finished_at = self._now()
        run.updated_at = run.finished_at
        self.store.save_run(
            run,
            event_type="run_cancelled",
            event_message=message,
            level="warning",
        )

    @staticmethod
    def _resolve_runtime_bindings(step: WorkflowStep, run: WorkflowRun) -> WorkflowStep:
        resolved = step.model_copy(deep=True)
        completed = {item.step_id: item for item in run.steps if item.status == "succeeded"}
        for slot_id, binding in list(resolved.input_bindings.items()):
            if binding.source != "upstream_output":
                continue
            producer = completed.get(binding.upstream_step_id or "")
            if producer is None:
                raise RuntimeError(
                    f"输入 {slot_id} 的上游步骤尚未完成：{binding.upstream_step_id}"
                )
            candidates = [
                artifact
                for artifact in producer.artifacts
                if artifact.artifact_type == binding.artifact_type
            ]
            exact = [
                artifact
                for artifact in candidates
                if artifact.metadata.get("output_slot_id") == binding.output_slot_id
            ]
            artifact = next(iter(exact or candidates), None)
            if artifact is None:
                raise RuntimeError(
                    f"上游步骤 {producer.title} 没有生成输入 {slot_id} 所需的"
                    f" {binding.artifact_type} 制品"
                )
            resolved.input_bindings[slot_id] = binding.model_copy(
                deep=True,
                update={
                    "source": "existing_path",
                    "label": artifact.label,
                    "absolute_path": artifact.absolute_path,
                    "binding_mode": "single",
                    "status": "validated",
                    "messages": [f"已绑定运行制品：{artifact.artifact_id}"],
                },
            )
        return resolved

    @staticmethod
    def _annotate_output_slots(
        method: MethodOption,
        artifacts: list[RunArtifact],
    ) -> None:
        remaining = list(method.output_slots)
        for artifact in artifacts:
            matching = next(
                (slot for slot in remaining if slot.type == artifact.artifact_type),
                None,
            )
            if matching is None:
                continue
            artifact.metadata.setdefault("output_slot_id", matching.id)
            remaining.remove(matching)

    def _safe_run_directory(self, run_id: str) -> Path:
        candidate = (self.output_root / run_id).resolve()
        candidate.relative_to(self.output_root)
        return candidate

    def _safe_step_directory(self, run_id: str, step_id: str) -> Path:
        safe_step = "".join(char if char.isalnum() or char in "-_" else "_" for char in step_id)
        candidate = (self._safe_run_directory(run_id) / safe_step).resolve()
        candidate.relative_to(self.output_root)
        return candidate

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
