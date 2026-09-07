from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .workflow_models import (
    CommandReference,
    ExecutionRecipeSpec,
    InputSlotSpec,
    MethodSourceReference,
    OutputSlotSpec,
    ParameterSpec,
)


class ArtifactTypeDefinition(BaseModel):
    id: str
    label: str
    description: str
    kind: Literal["file", "folder", "file_bundle", "artifact"] = "artifact"
    formats: list[str] = Field(default_factory=list)
    companions: list[str] = Field(default_factory=list)


class CapabilityMethod(BaseModel):
    capability: str
    method_id: str
    skill_id: str
    label: str
    description: str
    runner_id: str
    execution_mode: Literal["planning", "runner"] = "runner"
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    requires_features: list[str] = Field(default_factory=list)
    default_recommended: bool = False
    default_reason: str = ""
    parameters: list[ParameterSpec] = Field(default_factory=list)
    input_slots: list[InputSlotSpec] = Field(default_factory=list)
    output_slots: list[OutputSlotSpec] = Field(default_factory=list)
    structure_level: Literal["profile", "evidence", "reviewed"] = "reviewed"
    source_references: list[MethodSourceReference] = Field(default_factory=list)
    command_references: list[CommandReference] = Field(default_factory=list)
    delegate_skill_ids: list[str] = Field(default_factory=list)
    execution_recipe: ExecutionRecipeSpec | None = None
    included_capabilities: list[str] = Field(default_factory=list)
    replaces_operations: list[str] = Field(default_factory=list)


class CapabilityRegistry:
    """Loads reviewed machine-readable method definitions from Skill folders."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir
        self._signature: tuple[tuple[str, int, int], ...] | None = None
        self._by_capability: dict[str, list[CapabilityMethod]] = {}
        self._artifact_types: dict[str, ArtifactTypeDefinition] = {}
        self._recipes_by_operation: dict[tuple[str, str], ExecutionRecipeSpec] = {}

    def methods_for(self, capability: str) -> list[CapabilityMethod]:
        self._load()
        return [item.model_copy(deep=True) for item in self._by_capability.get(capability, [])]

    def selectable_methods_for(self, capability: str) -> list[CapabilityMethod]:
        """Expand a planning Skill's operation choices into workflow methods.

        Generated planning manifests historically stored real task/method choices in
        one ``operation`` parameter below a single ``*-guided`` wrapper.  The workflow
        UI needs those choices before the parameter phase, so expose them as stable
        in-memory method variants without changing the capability tree or source Skill.
        """
        expanded: list[CapabilityMethod] = []
        candidates = self.methods_for(capability)
        reviewed = [m for m in candidates if m.runner_id.startswith('reviewed.')]
        replaced = {value for m in reviewed for value in m.replaces_operations}
        for method in candidates:
            operation = next(
                (
                    parameter
                    for parameter in method.parameters
                    if parameter.id == "operation" and len(parameter.options) > 1
                ),
                None,
            )
            if operation is None:
                expanded.append(method)
                continue

            for option in operation.options:
                if method.execution_mode == 'planning' and str(option.value) in replaced:
                    continue
                option_slug = re.sub(
                    r"[^a-z0-9]+",
                    "-",
                    str(option.value).lower(),
                ).strip("-") or "option"
                option_text = " ".join(
                    (option.label, option.description, str(option.value))
                ).lower()
                delegates = [
                    skill_id
                    for skill_id in method.delegate_skill_ids
                    if self._mentions_skill(option_text, skill_id)
                ]
                selected_operation = operation.model_copy(
                    deep=True,
                    update={
                        "default": option.value,
                        "options": [option.model_copy(deep=True)],
                        "label": "已选任务范围",
                        "description": "该值由流程中的方法选择确定。",
                    },
                )
                parameters = [
                    selected_operation
                    if parameter.id == operation.id
                    else parameter.model_copy(deep=True)
                    for parameter in method.parameters
                ]
                recipe = self._recipes_by_operation.get(
                    (method.skill_id, str(option.value))
                )
                if recipe is not None:
                    interface = self._method_from_loaded(
                        recipe.interface_capability,
                        recipe.interface_method_id,
                    )
                    if interface is None:
                        raise RuntimeError(
                            f"执行配方 {recipe.recipe_id} 的接口方法不存在："
                            f"{recipe.interface_capability}/{recipe.interface_method_id}"
                        )
                    exposed = set(recipe.exposed_parameters)
                    recipe_parameters = [
                        parameter.model_copy(deep=True)
                        for parameter in interface.parameters
                        if not exposed or parameter.id in exposed
                    ]
                    recipe_inputs = (
                        [slot.model_copy(deep=True) for slot in recipe.input_slots]
                        if recipe.input_slots
                        else [slot.model_copy(deep=True) for slot in interface.input_slots]
                    )
                    recipe_outputs = (
                        [slot.model_copy(deep=True) for slot in recipe.output_slots]
                        if recipe.output_slots
                        else [slot.model_copy(deep=True) for slot in interface.output_slots]
                    )
                    expanded.append(
                        interface.model_copy(
                            deep=True,
                            update={
                                "method_id": f"{method.method_id}--{option_slug}",
                                "skill_id": method.skill_id,
                                "label": option.label,
                                "description": (
                                    recipe.label
                                    + "。"
                                    + (option.description or method.description)
                                    + f"；确认后将展开为 {len(recipe.steps)} 个受信任 Runner 步骤。"
                                ),
                                # Keep the dedicated executable method as the
                                # default. Recipes are explicit alternatives the
                                # model or user can choose when their scope matches.
                                "default_recommended": False,
                                "default_reason": "该方法已映射到受审核的 Runner 执行配方。",
                                "parameters": recipe_parameters,
                                "input_slots": recipe_inputs,
                                "output_slots": recipe_outputs,
                                "input_types": [slot.type for slot in recipe_inputs],
                                "output_types": [slot.type for slot in recipe_outputs],
                                "structure_level": "reviewed",
                                "source_references": [
                                    *interface.source_references,
                                    *method.source_references,
                                ],
                                "execution_recipe": recipe.model_copy(deep=True),
                            },
                        )
                    )
                    continue
                expanded.append(
                    method.model_copy(
                        deep=True,
                        update={
                            "method_id": f"{method.method_id}--{option_slug}",
                            "label": option.label,
                            "description": option.description or method.description,
                            "default_recommended": bool(
                                method.default_recommended
                                and option.value == operation.default
                            ),
                            "default_reason": (
                                "该方法来自命中 Skill 的任务选项；模型会结合当前需求"
                                "在相关实现中排序推荐。"
                            ),
                            "parameters": parameters,
                            "delegate_skill_ids": delegates,
                            "command_references": self._matching_commands(
                                method.command_references,
                                option_text,
                            ),
                        },
                    )
                )
        return expanded

    def method_for(self, capability: str, method_id: str) -> CapabilityMethod | None:
        self._load()
        method = self._method_from_loaded(capability, method_id)
        return method.model_copy(deep=True) if method is not None else None

    def recipe_methods(self, recipe: ExecutionRecipeSpec) -> list[CapabilityMethod]:
        self._load()
        methods: list[CapabilityMethod] = []
        for step in recipe.steps:
            method = self._method_from_loaded(step.capability, step.method_id)
            if method is None:
                raise RuntimeError(
                    f"执行配方 {recipe.recipe_id} 引用了不存在的方法："
                    f"{step.capability}/{step.method_id}"
                )
            methods.append(method.model_copy(deep=True))
        return methods

    def capabilities(self) -> list[str]:
        self._load()
        return sorted(self._by_capability)

    def all_methods(self) -> list[CapabilityMethod]:
        self._load()
        return [
            method.model_copy(deep=True)
            for capability in sorted(self._by_capability)
            for method in self._by_capability[capability]
        ]

    def planner_catalog(self, capabilities: list[str]) -> dict[str, list[str]]:
        self._load()
        return {
            capability: [item.method_id for item in self._by_capability.get(capability, [])]
            for capability in capabilities
        }

    def runner_ids(self) -> set[str]:
        self._load()
        return {
            method.runner_id
            for methods in self._by_capability.values()
            for method in methods
            if method.execution_mode == "runner"
        }

    def artifact_types(self) -> list[ArtifactTypeDefinition]:
        self._load()
        return [item.model_copy(deep=True) for item in self._artifact_types.values()]

    def stats(self) -> dict[str, int]:
        self._load()
        selectable_counts = [
            len(self.selectable_methods_for(capability))
            for capability in self._by_capability
        ]
        return {
            "capabilities": len(self._by_capability),
            "methods": sum(len(items) for items in self._by_capability.values()),
            "planning_methods": sum(
                method.execution_mode == "planning"
                for methods in self._by_capability.values()
                for method in methods
            ),
            "runner_methods": sum(
                method.execution_mode == "runner"
                for methods in self._by_capability.values()
                for method in methods
            ),
            "evidence_backed_methods": sum(
                method.structure_level in {"evidence", "reviewed"}
                for methods in self._by_capability.values()
                for method in methods
            ),
            "reference_commands": sum(
                len(method.command_references)
                for methods in self._by_capability.values()
                for method in methods
            ),
            "artifact_types": len(self._artifact_types),
            "selectable_methods": sum(selectable_counts),
            "multi_method_capabilities": sum(count > 1 for count in selectable_counts),
        }

    @staticmethod
    def _mentions_skill(text: str, skill_id: str) -> bool:
        normalized = skill_id.lower().strip()
        aliases = {
            normalized,
            normalized.replace("-", " "),
            re.sub(r"-(?:tool|skill)$", "", normalized),
        }
        return any(alias and alias in text for alias in aliases)

    @staticmethod
    def _matching_commands(
        references: list[CommandReference],
        option_text: str,
    ) -> list[CommandReference]:
        if len(references) <= 1:
            return [reference.model_copy(deep=True) for reference in references]
        terms = {
            token
            for token in re.findall(r"[a-z][a-z0-9_-]{2,}", option_text)
            if token not in {"the", "and", "with", "from", "for", "output", "skill"}
        }
        matched = [
            reference.model_copy(deep=True)
            for reference in references
            if terms.intersection(
                re.findall(r"[a-z][a-z0-9_-]{2,}", reference.command.lower())
            )
        ]
        return matched[:4] if matched else [
            reference.model_copy(deep=True) for reference in references[:4]
        ]

    def _load(self) -> None:
        manifests = sorted(
            [
                *self.skills_dir.glob("*/tool.manifest.json"),
                *self.skills_dir.glob("*/execution.manifest.json"),
                *self.skills_dir.glob("*/planning.manifest.json"),
            ]
        )
        recipe_manifests = sorted(self.skills_dir.glob("*/recipes.manifest.json"))
        artifact_path = self.skills_dir / "artifact-types.json"
        signature_paths = [
            *manifests,
            *recipe_manifests,
            *([artifact_path] if artifact_path.is_file() else []),
        ]
        signature = tuple(
            (str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in signature_paths
        )
        if signature == self._signature:
            return

        artifact_types: dict[str, ArtifactTypeDefinition] = {}
        if artifact_path.is_file():
            try:
                artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"无法载入 Artifact 类型表 {artifact_path}: {exc}") from exc
            for raw_artifact in artifact_payload.get("artifact_types", []):
                artifact = ArtifactTypeDefinition.model_validate(raw_artifact)
                if artifact.id in artifact_types:
                    raise RuntimeError(f"重复的 Artifact 类型：{artifact.id}")
                artifact_types[artifact.id] = artifact

        by_capability: dict[str, list[CapabilityMethod]] = {}
        seen: set[tuple[str, str]] = set()
        for path in manifests:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"无法载入工具 manifest {path}: {exc}") from exc
            if payload.get("schema_version") != 1:
                raise RuntimeError(f"不支持的工具 manifest 版本：{path}")
            skill_id = str(payload.get("skill_id") or path.parent.name)
            provides = payload.get("provides")
            if not isinstance(provides, list):
                raise RuntimeError(f"工具 manifest 缺少 provides：{path}")
            for raw in provides:
                if not isinstance(raw, dict):
                    raise RuntimeError(f"工具 manifest provides 项格式错误：{path}")
                method = CapabilityMethod.model_validate({**raw, "skill_id": skill_id})
                declared_types = {
                    slot.type for slot in [*method.input_slots, *method.output_slots]
                }
                unknown_types = sorted(declared_types - set(artifact_types))
                if unknown_types:
                    raise RuntimeError(
                        f"方法 {method.capability}/{method.method_id} 引用了未知 Artifact 类型："
                        + ", ".join(unknown_types)
                    )
                if not method.source_references:
                    references = [
                        MethodSourceReference(
                            path=f"skills/{skill_id}/{path.name}",
                            label="结构化方法声明",
                            kind="skill",
                            line_start=1,
                        )
                    ]
                    skill_doc = path.parent / "SKILL.md"
                    if skill_doc.is_file():
                        references.append(
                            MethodSourceReference(
                                path=f"skills/{skill_id}/SKILL.md",
                                label="Skill 使用说明",
                                kind="skill",
                                line_start=1,
                            )
                        )
                    method = method.model_copy(update={"source_references": references})
                key = (method.capability, method.method_id)
                if key in seen:
                    raise RuntimeError(f"重复的方法定义：{method.capability}/{method.method_id}")
                seen.add(key)
                by_capability.setdefault(method.capability, []).append(method)

        recipes_by_operation: dict[tuple[str, str], ExecutionRecipeSpec] = {}
        for path in recipe_manifests:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"无法载入执行配方 {path}: {exc}") from exc
            if payload.get("schema_version") != 1:
                raise RuntimeError(f"不支持的执行配方版本：{path}")
            skill_id = str(payload.get("skill_id") or path.parent.name)
            raw_recipes = payload.get("recipes")
            if not isinstance(raw_recipes, list):
                raise RuntimeError(f"执行配方缺少 recipes：{path}")
            for raw_recipe in raw_recipes:
                recipe = ExecutionRecipeSpec.model_validate(raw_recipe)
                key = (skill_id, recipe.operation_value)
                if key in recipes_by_operation:
                    raise RuntimeError(
                        f"重复的 Skill 操作执行配方：{skill_id}/{recipe.operation_value}"
                    )
                interface = next(
                    (
                        item
                        for item in by_capability.get(recipe.interface_capability, [])
                        if item.method_id == recipe.interface_method_id
                    ),
                    None,
                )
                if interface is None:
                    raise RuntimeError(
                        f"执行配方 {recipe.recipe_id} 的接口方法不存在："
                        f"{recipe.interface_capability}/{recipe.interface_method_id}"
                    )
                for recipe_step in recipe.steps:
                    target = next(
                        (
                            item
                            for item in by_capability.get(recipe_step.capability, [])
                            if item.method_id == recipe_step.method_id
                        ),
                        None,
                    )
                    if target is None or target.execution_mode != "runner":
                        raise RuntimeError(
                            f"执行配方 {recipe.recipe_id} 只能引用可执行方法："
                            f"{recipe_step.capability}/{recipe_step.method_id}"
                        )
                    unknown_parameters = sorted(
                        set(recipe_step.fixed_parameters)
                        - {parameter.id for parameter in target.parameters}
                    )
                    if unknown_parameters:
                        raise RuntimeError(
                            f"执行配方 {recipe.recipe_id}/{recipe_step.id} 含有未声明参数："
                            + ", ".join(unknown_parameters)
                        )
                recipes_by_operation[key] = recipe

        self._signature = signature
        self._by_capability = by_capability
        self._artifact_types = artifact_types
        self._recipes_by_operation = recipes_by_operation

    def _method_from_loaded(
        self,
        capability: str,
        method_id: str,
    ) -> CapabilityMethod | None:
        return next(
            (
                item
                for item in self._by_capability.get(capability, [])
                if item.method_id == method_id
            ),
            None,
        )
