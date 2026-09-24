"""User scope is independent of file discovery and of the selected software.

These are planning constraints, not filesystem permissions. Generated intermediates
are distinguished from existing inputs so excluding an old FOD does not ban CSD.
"""
from __future__ import annotations

from typing import Literal, Annotated

from pydantic import BaseModel, ConfigDict, Field


class ArtifactConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_type: str = Field(min_length=1, max_length=100)
    # Exact relative paths or basenames mentioned by the user; never glob/shell.
    paths: list[str] = Field(default_factory=list, max_length=50)

    def matches(self, artifact_type: str, path: str | None = None) -> bool:
        if self.artifact_type != artifact_type:
            return False
        if not self.paths:
            return True
        if path is None:
            return False
        normalized = path.replace("\\", "/")
        return any(normalized == p.replace("\\", "/") or (
            not p.startswith(("/", "\\")) and
            normalized.endswith("/" + p.replace("\\", "/"))) for p in self.paths)


class TaskContract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    goal: str = Field(default="", max_length=800)
    goal_artifact_types: list[str] = Field(default_factory=list, max_length=12)
    retrieval_queries: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(default_factory=list, max_length=8)
    input_policy: Literal["unspecified", "only_listed"] = "unspecified"
    allowed_existing_inputs: list[ArtifactConstraint] = Field(default_factory=list, max_length=30)
    forbidden_existing_inputs: list[ArtifactConstraint] = Field(default_factory=list, max_length=30)
    forbidden_capability_ids: list[str] = Field(default_factory=list, max_length=30)
    plan_scope: Literal["requested_steps", "goal_from_inputs"] = "requested_steps"
    allow_generated_intermediates: bool = True

    def allows_external(self, artifact_type: str, path: str | None = None) -> bool:
        if any(item.matches(artifact_type, path) for item in self.forbidden_existing_inputs):
            return False
        if self.input_policy == "unspecified":
            return True
        return any(item.artifact_type == artifact_type and
                   (path is None or item.matches(artifact_type, path))
                   for item in self.allowed_existing_inputs)

    def allows_slot(self, slot, path: str | None = None) -> bool:
        # The catalog has both the gradient-table parent and two precise subtypes.
        # Resolve from declared port formats, never from the user's wording. A
        # b-value permission alone must not authorize the b-vector port (or vice versa).
        types = {slot.type}
        if slot.type == 'gradient_table':
            formats = set(slot.formats)
            if '.bval' in formats and '.bvec' not in formats:
                types.add('b_values')
            if '.bvec' in formats and '.bval' not in formats:
                types.add('b_vectors')
        elif slot.type in {'b_values', 'b_vectors'}:
            types.add('gradient_table')
        if any(item.artifact_type in types and item.matches(item.artifact_type, path)
               for item in self.forbidden_existing_inputs):
            return False
        return self.input_policy == 'unspecified' or any(item.artifact_type in types and
            (path is None or item.matches(item.artifact_type, path)) for item in self.allowed_existing_inputs)


class PlanNotMatched(ValueError):
    """No validated plan was found; this does NOT prove software is absent."""

    def __init__(self, reason: str, diagnostics: dict | None = None):
        super().__init__(reason)
        self.diagnostics = diagnostics or {}


def binding_scope_errors(contract: TaskContract, workflow) -> list[str]:
    errors = []
    for step in workflow.steps:
        method = next((m for m in step.method_options if m.id == step.selected_method_id), None)
        for binding in step.input_bindings.values():
            if binding.source == "upstream_output":
                continue
            paths = [binding.absolute_path or binding.relative_path]
            if binding.sample_matches:
                paths = [m.absolute_path for m in binding.sample_matches]
            if binding.history:
                paths = [a.absolute_path for a in binding.history.artifacts]
            slot = next((s for s in method.input_slots if s.id == binding.slot_id), None) if method else None
            if any(not (contract.allows_slot(slot, path) if slot else
                       contract.allows_external(binding.artifact_type, path)) for path in paths):
                errors.append(f"{step.title}/{binding.slot_id}：已有输入不符合本次允许范围")
    return errors
