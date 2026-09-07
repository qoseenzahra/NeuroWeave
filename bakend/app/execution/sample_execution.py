"""Durable sample lanes with bounded concurrency on each selected node."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event

from .base import ExecutionCancelled, ExecutionDetached, RunnerContext
from .sample_plan import workflow_for_unit
from .slurm_backend import TERMINAL_STATES


def execute_samples(service, run, workflow, units, cancel_event):
    stop_submissions = Event()
    detached = Event()
    lanes = {}
    limits = {allocation.node: allocation.parallel_samples for allocation in run.execution.nodes}
    sample_lanes = {}
    for index, unit in enumerate(units):
        node = unit.execution.node
        assigned = sample_lanes.setdefault(node, {})
        # Keep the whole sample in one stable lane, including during recovery.
        # Splitting by step would allow downstream work to overtake its inputs.
        if unit.sample_id not in assigned:
            assigned[unit.sample_id] = len(assigned) % limits.get(node, 1)
        lanes.setdefault((node, assigned[unit.sample_id]), []).append((index, unit))

    def update_progress():
        run.progress = sum(step.progress for step in run.steps) / max(1, len(run.steps))
        run.current_step_id = next((step.step_id for step in run.steps if step.status == "running"), None)
        run.updated_at = service._now()

    def lane(items):
        failed_samples = {step.sample_id for step in run.steps if step.status == "failed"}
        for index, unit in items:
            step = run.steps[index]
            if step.status in {"succeeded", "failed", "cancelled"}:
                continue
            if service._detach_event.is_set() or stop_submissions.is_set():
                detached.set()
                return
            if (cancel_event.is_set() and not step.scheduler) or unit.sample_id in failed_samples:
                with service._lock:
                    step.status = "cancelled"
                    step.message = "已取消" if cancel_event.is_set() else "该样本上游失败，未执行此步骤"
                    step.finished_at = service._now()
                    update_progress()
                    service._save_run(run)
                continue
            try:
                with service._lock:
                    step.status = "running"
                    step.started_at = step.started_at or service._now()
                    step.message = "提交或恢复 Slurm 作业"
                    update_progress()
                    service._save_run(run, event_type="step_started", step_id=step.step_id,
                                      event_message=f"开始样本 {unit.sample_label}：{step.title}")
                    runtime_step = service._resolve_runtime_bindings(unit.step, run)

                def log(message, progress, level):
                    with service._lock:
                        if progress is not None:
                            step.progress = max(0.0, min(float(progress), 100.0))
                        step.message = message
                        update_progress()
                        service._save_run(run)
                        service.store.append_run_event(
                            run.run_id, event_type="runner_log", step_id=step.step_id,
                            message=message, level=level, progress=run.progress,
                        )

                def on_job(state):
                    with service._lock:
                        step.scheduler = state
                        update_progress()
                        service._save_run(
                            run, event_type="slurm_job_state", step_id=step.step_id,
                            event_message=f"Slurm {state.get('job_id', '')}: {state.get('state', '')}",
                            event_payload=state,
                        )

                context = RunnerContext(
                    run_id=run.run_id, workflow=workflow_for_unit(workflow, unit),
                    step=runtime_step, method=unit.method,
                    output_directory=service._safe_step_directory(run.run_id, unit.workspace_key, "slurm"),
                    cancel_event=cancel_event, log=log, detach_event=service._detach_event,
                )
                result = service.slurm_backend.execute(
                    context, unit.execution.model_dump(), step.scheduler or None, on_job,
                )
                with service._lock:
                    service._annotate_output_slots(unit.method, result.artifacts)
                    step.artifacts = result.artifacts
                    run.artifacts.extend(result.artifacts)
                    step.status = "succeeded"
                    step.progress = 100.0
                    step.message = result.message
                    step.finished_at = service._now()
                    update_progress()
                    service._save_run(run, event_type="step_succeeded", step_id=step.step_id,
                                      event_message=result.message)
            except ExecutionDetached as exc:
                with service._lock:
                    step.message = str(exc)
                    service._save_run(run, event_type="slurm_monitor_detached",
                                      step_id=step.step_id, event_message=str(exc))
                detached.set()
                stop_submissions.set()
                return
            except Exception as exc:
                with service._lock:
                    uncertain = (step.scheduler and step.scheduler.get("state") not in
                                 TERMINAL_STATES | {"SUBMISSION_FAILED"})
                    if uncertain:
                        step.message = "监控中断，保留作业记录等待恢复"
                        step.scheduler["reason"] = "monitoring_unavailable"
                        detached.set()
                        stop_submissions.set()
                    else:
                        step.status = "cancelled" if isinstance(exc, ExecutionCancelled) else "failed"
                        step.error_code = "cancelled" if isinstance(exc, ExecutionCancelled) else "runner_failed"
                        step.error_message = str(exc)
                        step.message = str(exc)
                        step.finished_at = service._now()
                        failed_samples.add(unit.sample_id)
                    update_progress()
                    service._save_run(run, event_type="step_interrupted", step_id=step.step_id,
                                      event_message=str(exc), level="warning" if uncertain else "error")
                if uncertain:
                    return

    try:
        with service._lock:
            run.status = "cancel_requested" if cancel_event.is_set() else "running"
            run.started_at = run.started_at or service._now()
            service._save_run(run, event_type="run_started", event_message="按样本分配到所选节点执行")
        with ThreadPoolExecutor(max_workers=len(lanes), thread_name_prefix="neuroweave-sample") as pool:
            futures = [pool.submit(lane, items) for items in lanes.values()]
            for future in futures:
                future.result()
        with service._lock:
            if detached.is_set():
                return  # Never release a workflow with a potentially live remote job.
            if cancel_event.is_set():
                run.status = "cancelled"
                run.cancellation_requested = True
                run.error_code = "cancelled"
                run.error_message = "样本任务已取消"
            elif any(step.status == "failed" for step in run.steps):
                run.status = "failed"
                run.error_code = "sample_failed"
                run.error_message = "部分样本执行失败，请查看各样本步骤和日志"
            else:
                run.status = "succeeded"
                run.progress = 100.0
            run.finished_at = service._now()
            run.updated_at = run.finished_at
            run.current_step_id = None
            service._save_run(run, event_type="run_" + run.status,
                              event_message=run.error_message or "所有样本运行完成")
    except Exception as exc:
        # Persistence/monitoring faults leave the run active and recoverable.
        service.store.append_run_event(run.run_id, event_type="slurm_monitor_detached",
                                       message=str(exc), level="error")
    finally:
        with service._lock:
            service._cancel_events.pop(run.run_id, None)
            service._futures.pop(run.run_id, None)
