from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .dataset_models import (
    DatasetPathPreview,
    DatasetRecord,
    SamplePathCoverage,
    SamplePathMatch,
)


WorkflowStatus = Literal[
    "awaiting_method_choice",
    "awaiting_input_binding",
    "chain_ready",
    "awaiting_parameter_review",
    "awaiting_dry_run",
    "ready",
    "confirmed",
]


class ParameterOption(BaseModel):
    value: Any
    label: str
    description: str = ""


class ParameterSpec(BaseModel):
    id: str
    argument: str
    label: str
    description: str = ""
    type: Literal["string", "integer", "number", "boolean"]
    control: Literal["auto", "select", "number", "text", "switch"] = "auto"
    level: Literal["basic", "advanced"] = "basic"
    group: str = "常用参数"
    unit: str = ""
    required: bool = True
    default: Any = None
    options: list[ParameterOption] = Field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    placeholder: str = ""
    visible_when: dict[str, list[Any]] = Field(default_factory=dict)


class InputSlotSpec(BaseModel):
    id: str
    type: str
    label: str
    description: str = ""
    required: bool = True
    required_when: dict[str, list[Any]] = Field(default_factory=dict)
    cardinality: Literal["one", "many"] = "one"
    binding: Literal["file", "folder", "file_bundle", "artifact"] = "artifact"
    formats: list[str] = Field(default_factory=list)
    companions: list[str] = Field(default_factory=list)
    source_options: list[Literal["dataset", "existing_path", "upstream_output"]] = Field(
        default_factory=lambda: ["dataset", "existing_path", "upstream_output"]
    )
    validation: list[str] = Field(default_factory=list)


class OutputSlotSpec(BaseModel):
    id: str
    type: str
    label: str
    description: str = ""
    format: str = ""
    primary: bool = False
    path_template: str = ""
    generated_when: dict[str, list[Any]] = Field(default_factory=dict)


class InputBinding(BaseModel):
    slot_id: str
    artifact_type: str
    source: Literal["dataset", "existing_path", "upstream_output"]
    label: str = ""
    root_id: str | None = None
    relative_path: str | None = None
    absolute_path: str | None = None
    upstream_step_id: str | None = None
    output_slot_id: str | None = None
    binding_mode: Literal["single", "per_sample", "dataset"] = "single"
    dataset_id: str | None = None
    path_template: str = ""
    variables: list[str] = Field(default_factory=list)
    coverage: SamplePathCoverage | None = None
    sample_matches: list[SamplePathMatch] = Field(default_factory=list)
    status: Literal["validated", "selected", "planned"] = "selected"
    messages: list[str] = Field(default_factory=list)


class MethodSourceReference(BaseModel):
    path: str
    label: str = ""
    kind: Literal["skill", "script", "command"] = "skill"
    line_start: int | None = None
    line_end: int | None = None


class CommandReference(BaseModel):
    command: str
    language: str = "bash"
    source_path: str
    line_start: int | None = None
    kind: Literal["operation", "setup", "environment", "example"] = "example"
    executable: bool = False


class RecipeInputBindingSpec(BaseModel):
    source: Literal["workflow_input", "step_output"]
    slot_id: str | None = None
    step_id: str | None = None
    output_slot_id: str | None = None


class RecipeOutputBindingSpec(BaseModel):
    step_id: str
    output_slot_id: str


class ExecutionRecipeStepSpec(BaseModel):
    id: str
    title: str
    capability: str
    method_id: str
    fixed_parameters: dict[str, Any] = Field(default_factory=dict)
    input_bindings: dict[str, RecipeInputBindingSpec] = Field(default_factory=dict)
    workspace: str = "default"


class ExecutionRecipeSpec(BaseModel):
    recipe_id: str
    label: str
    operation_value: str
    interface_capability: str
    interface_method_id: str
    exposed_parameters: list[str] = Field(default_factory=list)
    input_slots: list[InputSlotSpec] = Field(default_factory=list)
    output_slots: list[OutputSlotSpec] = Field(default_factory=list)
    steps: list[ExecutionRecipeStepSpec]
    output_bindings: dict[str, RecipeOutputBindingSpec] = Field(default_factory=dict)


class MethodOption(BaseModel):
    id: str
    skill_id: str
    label: str
    description: str
    runner_id: str
    execution_mode: Literal["planning", "runner"] = "runner"
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    requires_features: list[str] = Field(default_factory=list)
    compatible: bool = True
    blocked_reasons: list[str] = Field(default_factory=list)
    recommended: bool = False
    recommendation_reason: str = ""
    parameters: list[ParameterSpec] = Field(default_factory=list)
    input_slots: list[InputSlotSpec] = Field(default_factory=list)
    output_slots: list[OutputSlotSpec] = Field(default_factory=list)
    structure_level: Literal["profile", "evidence", "reviewed"] = "reviewed"
    source_references: list[MethodSourceReference] = Field(default_factory=list)
    command_references: list[CommandReference] = Field(default_factory=list)
    delegate_skill_ids: list[str] = Field(default_factory=list)
    execution_recipe: ExecutionRecipeSpec | None = None
    included_capabilities: list[str] = Field(default_factory=list)


class WorkflowStep(BaseModel):
    id: str
    order: int
    title: str
    description: str
    capability: str
    origin: Literal["requested", "dependency"] = "requested"
    selection: Literal["auto", "user"] = "user"
    depends_on: list[str] = Field(default_factory=list)
    status: Literal[
        "configured",
        "needs_method",
        "method_selected",
        "parameters_ready",
        "parameters_reviewed",
        "confirmed",
    ]
    method_options: list[MethodOption] = Field(default_factory=list)
    selected_method_id: str | None = None
    selected_parameters: dict[str, Any] = Field(default_factory=dict)
    input_bindings: dict[str, InputBinding] = Field(default_factory=dict)
    manual_input_types: list[str] = Field(default_factory=list)
    missing_required_inputs: list[str] = Field(default_factory=list)
    command_preview: str | None = None


class DryRunCommand(BaseModel):
    step_id: str
    runner_id: str
    command_preview: str
    execution_mode: Literal["planning", "runner"] = "runner"
    valid: bool = True
    messages: list[str] = Field(default_factory=list)


class DryRunReport(BaseModel):
    valid: bool
    execution_enabled: bool = False
    dataset_path_validated: bool = False
    commands: list[DryRunCommand] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    checked_at: str


class Workflow(BaseModel):
    workflow_id: str
    template_id: str
    revision: int = 1
    title: str
    summary: str
    original_request: str
    status: WorkflowStatus
    dataset_id: str | None = None
    dataset: DatasetRecord | None = None
    planner_source: str = "model"
    execution_mode: Literal["planning", "runner", "mixed"] = "runner"
    plan_kind: Literal["atomic", "composite"] = "composite"
    requested_capabilities: list[str] = Field(default_factory=list)
    excluded_capabilities: list[str] = Field(default_factory=list)
    input_capabilities: list[str] = Field(default_factory=list)
    dependency_policy: Literal["target_only", "complete"] = "target_only"
    steps: list[WorkflowStep]
    warnings: list[str] = Field(default_factory=list)
    can_lock: bool = False
    can_unlock: bool = False
    can_review_parameters: bool = False
    can_dry_run: bool = False
    can_confirm: bool = False
    locked_at: str | None = None
    parameters_reviewed_at: str | None = None
    dry_run_report: DryRunReport | None = None
    confirmed_at: str | None = None
    created_at: str
    updated_at: str


class WorkflowDraftRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    selected_skills: list[str] = Field(default_factory=list)
    dataset_id: str | None = None
    language: str = "zh-CN"


class WorkflowMutationRequest(BaseModel):
    expected_revision: int = Field(ge=1)


class MethodSelectionRequest(WorkflowMutationRequest):
    method_id: str = Field(min_length=1, max_length=200)


class ParameterUpdateRequest(WorkflowMutationRequest):
    parameters: dict[str, Any]


class InputBindingRequest(WorkflowMutationRequest):
    root_id: str = Field(min_length=1, max_length=100)
    relative_path: str = Field(default="", max_length=4_000)


class InputPreviewRequest(BaseModel):
    root_id: str = Field(min_length=1, max_length=100)
    relative_path: str = Field(default="", max_length=4_000)


class InputPreviewResponse(DatasetPathPreview):
    pass
