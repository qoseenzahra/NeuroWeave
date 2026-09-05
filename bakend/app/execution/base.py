from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable, Protocol

from ..run_models import RunArtifact
from ..workflow_models import MethodOption, Workflow, WorkflowStep


class ExecutionCancelled(RuntimeError):
    pass


LogCallback = Callable[[str, float | None, str], None]


@dataclass(frozen=True)
class RunnerContext:
    run_id: str
    workflow: Workflow
    step: WorkflowStep
    method: MethodOption
    output_directory: Path
    cancel_event: Event
    log: LogCallback

    def raise_if_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise ExecutionCancelled("任务已由用户取消")


@dataclass(frozen=True)
class RunnerResult:
    artifacts: list[RunArtifact]
    message: str


class TrustedRunner(Protocol):
    runner_id: str
    label: str

    def runtime_status(self) -> dict[str, Any]: ...

    def preflight(self, context: RunnerContext) -> list[str]: ...

    def run(self, context: RunnerContext) -> RunnerResult: ...
