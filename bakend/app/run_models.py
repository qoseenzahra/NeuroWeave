from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


RunStatus = Literal[
    "queued",
    "running",
    "cancel_requested",
    "cancelled",
    "succeeded",
    "failed",
]

RunStepStatus = Literal["queued", "running", "cancelled", "succeeded", "failed"]


class RunArtifact(BaseModel):
    artifact_id: str
    step_id: str
    artifact_type: str
    label: str
    absolute_path: str
    relative_path: str
    media_type: str = "application/octet-stream"
    size_bytes: int = 0
    sha256: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class RunStep(BaseModel):
    step_id: str
    title: str
    runner_id: str
    method_id: str
    status: RunStepStatus = "queued"
    progress: float = 0.0
    message: str = "等待执行"
    artifacts: list[RunArtifact] = Field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    started_at: str | None = None
    finished_at: str | None = None
    scheduler: dict[str, Any] = Field(default_factory=dict)


class RunExecutionOptions(BaseModel):
    backend: Literal["local", "slurm"] = "local"
    partition: str = Field(default="all", pattern=r"^[A-Za-z0-9_-]{1,64}$")
    cpus: int = Field(default=4, ge=1, le=64)
    memory_gb: int = Field(default=8, ge=1, le=256)
    gpus: int = Field(default=0, ge=0, le=1)
    time_minutes: int = Field(default=60, ge=1, le=1440)


class WorkflowRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_revision: int
    status: RunStatus = "queued"
    progress: float = 0.0
    current_step_id: str | None = None
    output_directory: str
    plan_snapshot: dict[str, Any] = Field(default_factory=dict)
    steps: list[RunStep] = Field(default_factory=list)
    artifacts: list[RunArtifact] = Field(default_factory=list)
    error_code: str = ""
    error_message: str = ""
    cancellation_requested: bool = False
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None
    updated_at: str
    execution: RunExecutionOptions = Field(default_factory=RunExecutionOptions)


class RunCreateRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    execution: RunExecutionOptions = Field(default_factory=RunExecutionOptions)


class RunEvent(BaseModel):
    event_id: int
    event_type: str
    level: Literal["info", "warning", "error"] = "info"
    message: str = ""
    progress: float | None = None
    step_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
