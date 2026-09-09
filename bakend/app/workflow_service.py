from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from .capability_retriever import CapabilityRetriever
from .capability_tree import CapabilityTree
from .capability_registry import CapabilityMethod, CapabilityRegistry
from .chat_service import ChatService
from .dataset_models import DatasetPathPreview, DatasetRecord
from .dataset_service import DatasetService
from .execution.recipe_compiler import RecipeCompilationError, RecipeCompiler
from .execution.runner_registry import RunnerRegistry
from .local_store import LocalStore
from .operation_context import checkpoint
from .historical_inputs import HistoricalInputs
from .sample_scope import partial_sample_scope, restrict_sample_bindings
from .models import (
    CapabilityRecommendation,
    CapabilityRecommendationItem,
    ChatRequest,
)
from .skill_loader import SkillLoader
from .task_scope import existing_input_capabilities
from .workflow_ordering import order_capabilities
from .workflow_models import (
    DryRunCommand,
    DryRunReport,
    InputBinding,
    MethodOption,
    ParameterSpec,
    Workflow,
    WorkflowStep,
)


class RevisionConflict(ValueError):
    def __init__(self, current: Workflow) -> None:
        super().__init__(f"流程版本已更新，当前版本为 R{current.revision}")
        self.current = current


class WorkflowService:
    """Persistent and revision-safe state machine for local workflows."""

    PLANNING_WARNING = (
        "流程包含规划型结构化 Skill：可以选择参数并保存方案，但不会声称存在可执行 runner。"
    )

    def __init__(
        self,
        manifest_path: Path,
        chat_service: ChatService,
        registry: CapabilityRegistry,
        store: LocalStore,
        dataset_service: DatasetService,
        capability_tree: CapabilityTree | None = None,
        skill_loader: SkillLoader | None = None,
        executable_runner_ids: set[str] | None = None,
        runner_registry: RunnerRegistry | None = None,
    ) -> None:
        self.manifest_path = manifest_path
        self.chat_service = chat_service
        self.registry = registry
        self.store = store
        self.dataset_service = dataset_service
        self.capability_tree = capability_tree
        self.skill_loader = skill_loader
        self.executable_runner_ids = set(executable_runner_ids or set())
        self.runner_registry = runner_registry
        self._declared_order = [step["capability"] for step in self._load_manifest()["steps"]]
        self.capability_retriever = (
            CapabilityRetriever(capability_tree, registry, skill_loader)
            if capability_tree is not None and skill_loader is not None
            else None
        )
        self._lock = RLock()

    @staticmethod
    def matches_request(message: str, selected_skills: list[str]) -> bool:
        lowered = message.lower()
        explicit_domain = bool(
            re.search(r"\b(dwi|dti|diffusion|qsiprep|eddy|dtifit)\b", lowered)
            or any(term in lowered for term in ("扩散磁共振", "扩散成像", "扩散指标"))
        )
        selected_dwi = any(skill.lower() == "dwi-skill" for skill in selected_skills)
        actionable = any(
            term in lowered
            for term in ("处理", "预处理", "计算", "分析", "流程", "pipeline", "fa", "md", "张量")
        )
        return (explicit_domain or selected_dwi) and actionable

    async def assess_task(self, request: ChatRequest) -> dict[str, Any]:
        """Route through shallow tree frontiers before loading any Skill body."""
        if self.capability_tree is None:
            raise RuntimeError("CapabilityTree 尚未配置")
        dataset = self.dataset_service.get(request.dataset_id) if request.dataset_id else None
        allowed = [node.id for node in self.capability_tree.leaves()]
        heuristic_ids = self._heuristic_capabilities(request, allowed)
        retrieved = (
            self.capability_retriever.retrieve(
                request.message,
                request.selected_skills,
                limit=8,
            )
            if self.capability_retriever is not None
            else []
        )
        retrieved_ids = [item.capability_id for item in retrieved if item.capability_id in allowed]
        catalog_skill_ids = list(dict.fromkeys([*heuristic_ids, *retrieved_ids]))
        intent_catalog = self._specific_intent_catalog(allowed, catalog_skill_ids)
        intent = await self.chat_service.normalize_task_intent(
            request,
            intent_catalog,
            heuristic_ids,
        )
        routing = await self._route_capabilities_hierarchically(
            request,
            allowed,
            dataset.inspection.model_dump(mode="json") if dataset else None,
            intent,
        )
        routing_trace = routing.setdefault("routing_trace", {})
        routing_trace["retrieval"] = {
            "strategy": "local_sparse_skill_shortlist",
            "candidate_count": len(retrieved),
            "candidates": [item.public_dict() for item in retrieved],
            "intent_catalog_count": len(intent_catalog),
            "forced_capability_ids": heuristic_ids,
        }

        capability_ids = [item for item in routing["capability_ids"] if item in allowed]
        structured_ids = [
            capability_id
            for capability_id in capability_ids
            if self.registry.methods_for(capability_id)
        ]
        advisory_ids = [
            capability_id
            for capability_id in capability_ids
            if capability_id not in structured_ids
        ]
        is_task = routing["decision"] == "task" and bool(capability_ids)
        return {
            **routing,
            "capability_ids": capability_ids,
            "structured_capability_ids": structured_ids,
            "advisory_capability_ids": advisory_ids,
            "recommend_skills": is_task,
            "recommend_workflow": is_task and not advisory_ids,
            "clarification_required": bool(routing.get("clarification_required")),
            "clarification_question": str(routing.get("clarification_question") or ""),
            "task_intent": intent,
            "workflow_id": (
                "dynamic-capability-plan"
                if is_task and not advisory_ids
                else None
            ),
        }

    async def _route_capabilities_hierarchically(
        self,
        request: ChatRequest,
        allowed_leaf_ids: list[str],
        dataset_context: dict[str, Any] | None,
        intent: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.capability_tree is None:
            raise RuntimeError("CapabilityTree 尚未配置")

        tree = self.capability_tree
        intent = intent or {}
        reused_inputs = existing_input_capabilities(request.message) | {
            item for item in intent.get("input_capability_ids", []) if item in allowed_leaf_ids
        }
        allowed_leaf_ids = [item for item in allowed_leaf_ids if item not in reused_inputs]
        heuristic_leaves = self._heuristic_capabilities(request, allowed_leaf_ids)
        semantic_leaves = [
            str(item)
            for item in intent.get("candidate_capability_ids") or []
            if str(item) in allowed_leaf_ids and str(item) not in existing_input_capabilities(request.message)
        ]
        explicit_skill_leaves = self._explicit_skill_capabilities(
            request.message,
            allowed_leaf_ids,
        )
        semantic_leaves = self._drop_shadowed_modality_skills(
            semantic_leaves,
            explicit_skill_leaves,
        )
        confidence = float(intent.get("confidence") or 0.0)
        # A complete semantic result is authoritative. Keyword hints must not
        # turn mentioned inputs into additional requested producer operations.
        if intent.get('source', '').startswith('model') and intent.get('coverage') == 'complete' and confidence >= 0.7:
            heuristic_leaves = []
        routed_catalog = self._specific_intent_catalog(
            allowed_leaf_ids,
            [*semantic_leaves, *heuristic_leaves],
        )
        anchor_leaves = self._prune_generic_skill_leaves(
            list(dict.fromkeys([*semantic_leaves, *heuristic_leaves]))
        )
        full_tree_payload_chars = len(
            json.dumps(tree.compact(), ensure_ascii=False, separators=(",", ":"))
        )
        intent_payload_chars = len(
            json.dumps(routed_catalog, ensure_ascii=False)
        )
        semantic_trace = {
            "strategy": "semantic",
            "levels": [],
            "candidates_seen": len(routed_catalog),
            "payload_chars": intent_payload_chars,
            "full_tree_payload_chars": full_tree_payload_chars,
            "payload_ratio": round(
                intent_payload_chars / full_tree_payload_chars,
                4,
            ) if full_tree_payload_chars else 0.0,
            "selected_paths": [tree.label_path_for(item) for item in anchor_leaves],
            "intent_source": str(intent.get("source") or "unknown"),
            "normalized_task": str(intent.get("task_brief") or request.message)[:600],
            "semantic_hints": semantic_leaves,
            "confidence": confidence,
            "reused_input_capabilities": sorted(reused_inputs),
        }
        if intent.get("needs_clarification") and not anchor_leaves:
            return {
                "decision": "task",
                "capability_ids": [],
                "reason": str(intent.get("reason") or "需要补充任务信息。"),
                "decision_source": "semantic_clarification",
                "clarification_required": True,
                "clarification_question": str(intent.get("clarification_question") or ""),
                "routing_trace": semantic_trace,
            }
        if (
            intent.get("decision") == "task"
            and anchor_leaves
            and intent.get("coverage") == "complete"
            and confidence >= 0.7
        ):
            return {
                "decision": "task",
                "capability_ids": anchor_leaves,
                "reason": str(intent.get("reason") or "标准化任务意图已匹配具体能力。"),
                "decision_source": "semantic_intent",
                "clarification_required": False,
                "clarification_question": "",
                "routing_trace": semantic_trace,
            }
        if intent.get("decision") == "chat" and not anchor_leaves and confidence >= 0.7:
            return {
                "decision": "chat",
                "capability_ids": [],
                "reason": str(intent.get("reason") or "当前请求不需要生成数据处理流程。"),
                "decision_source": "semantic_intent",
                "clarification_required": False,
                "clarification_question": "",
                "routing_trace": semantic_trace,
            }
        if self.chat_service.mode != "model":
            return {
                "decision": "task" if anchor_leaves else "chat",
                "capability_ids": anchor_leaves,
                "reason": (
                    "需求与能力树中的现有能力匹配。"
                    if anchor_leaves
                    else "当前需求不需要任务建议，或未匹配到现有能力。"
                ),
                "decision_source": "heuristic",
                "routing_trace": {
                    "strategy": "heuristic",
                    "levels": [],
                    "candidates_seen": 0,
                    "payload_chars": 0,
                    "full_tree_payload_chars": full_tree_payload_chars,
                    "payload_ratio": 0.0,
                    "selected_paths": [
                        tree.label_path_for(capability_id)
                        for capability_id in anchor_leaves
                    ],
                },
            }

        frontier = [tree.root_id]
        selected_leaves: list[str] = []
        task_brief = str(intent.get("task_brief") or "")[:600]
        reason = "当前需求不需要任务建议，或未匹配到现有能力。"
        levels: list[dict[str, Any]] = []
        used_fallback = False
        decision = "chat"

        # The reviewed tree is currently at most four edges deep. Six levels leave
        # room for taxonomy growth while still bounding model calls and token use.
        for level in range(1, 7):
            candidate_groups = tree.routing_frontier(frontier)
            if not candidate_groups:
                break
            candidate_payload = json.dumps(
                candidate_groups,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            fallback_hops = tree.next_hops_for(frontier, anchor_leaves)
            result = await self.chat_service.route_capability_level(
                request,
                candidate_groups,
                dataset_context,
                level=level,
                task_brief=task_brief,
                fallback_node_ids=fallback_hops,
                first_level=level == 1,
            )
            selected_node_ids = list(result.get("selected_node_ids") or [])
            source = str(result.get("decision_source") or "model")
            if fallback_hops:
                merged_nodes = list(dict.fromkeys([*fallback_hops, *selected_node_ids]))[:4]
                if merged_nodes != selected_node_ids or result.get("decision") != "task":
                    selected_node_ids = merged_nodes
                    result["decision"] = "task"
                    source = "model_with_semantic_anchors"
            used_fallback = used_fallback or source != "model"
            levels.append(
                {
                    "level": level,
                    "parent_ids": list(frontier),
                    "candidate_count": sum(
                        len(group.get("candidates", []))
                        for group in candidate_groups
                    ),
                    "payload_chars": len(candidate_payload),
                    "selected_node_ids": selected_node_ids,
                    "source": source,
                }
            )
            task_brief = str(result.get("task_brief") or task_brief)[:600]
            reason = str(result.get("reason") or reason)
            decision = str(result.get("decision") or "chat")
            if decision != "task":
                break

            next_frontier: list[str] = []
            for node_id in selected_node_ids:
                node = tree.node(node_id)
                if node is None:
                    continue
                if node.is_leaf:
                    if node.id in allowed_leaf_ids and node.id not in selected_leaves:
                        selected_leaves.append(node.id)
                elif node.id not in next_frontier:
                    next_frontier.append(node.id)
            if not next_frontier:
                break
            frontier = next_frontier

        if decision == "task" and not selected_leaves and anchor_leaves:
            selected_leaves = anchor_leaves
            used_fallback = True
            reason = "分层路由未到达叶子，已使用本地能力匹配结果。"
        if anchor_leaves:
            selected_leaves = list(dict.fromkeys([*selected_leaves, *anchor_leaves]))
        selected_leaves = self._prune_generic_skill_leaves(selected_leaves)
        selected_leaves = [item for item in selected_leaves if item not in existing_input_capabilities(request.message)]
        decision = "task" if selected_leaves else "chat"

        payload_chars = sum(item["payload_chars"] for item in levels)
        return {
            "decision": decision,
            "capability_ids": selected_leaves if decision == "task" else [],
            "reason": reason,
            "decision_source": (
                "hierarchical_with_semantic"
                if used_fallback and semantic_leaves
                else "hierarchical_with_heuristic"
                if used_fallback
                else "model_hierarchical"
            ),
            "routing_trace": {
                "strategy": "hierarchical",
                "levels": levels,
                "candidates_seen": sum(item["candidate_count"] for item in levels),
                "payload_chars": payload_chars,
                "full_tree_payload_chars": full_tree_payload_chars,
                "payload_ratio": round(
                    payload_chars / full_tree_payload_chars,
                    4,
                ) if full_tree_payload_chars else 0.0,
                "selected_paths": [
                    tree.label_path_for(capability_id)
                    for capability_id in selected_leaves
                ],
                "intent_source": str(intent.get("source") or "unknown"),
                "normalized_task": str(intent.get("task_brief") or request.message)[:600],
                "semantic_hints": semantic_leaves,
                "reused_input_capabilities": sorted(reused_inputs),
                "confidence": confidence,
            },
        }

    def _prune_generic_skill_leaves(self, capability_ids: list[str]) -> list[str]:
        """Drop a whole-Skill leaf when a more specific leaf from it was selected."""
        if self.capability_tree is None:
            return capability_ids
        specific_skill_ids = {
            skill_id
            for capability_id in capability_ids
            if not capability_id.startswith("skill.")
            for node in [self.capability_tree.leaf(capability_id)]
            if node is not None
            for skill_id in node.skill_ids
        }
        return [
            capability_id
            for capability_id in capability_ids
            if not (
                capability_id.startswith("skill.")
                and (node := self.capability_tree.leaf(capability_id)) is not None
                and specific_skill_ids.intersection(node.skill_ids)
            )
        ]

    def _drop_shadowed_modality_skills(
        self,
        capability_ids: list[str],
        explicit_skill_ids: list[str],
    ) -> list[str]:
        """A named concrete tool supersedes broad modality Skills for the same turn."""
        if self.capability_tree is None or self.skill_loader is None:
            return capability_ids

        explicit = set(explicit_skill_ids)
        has_specific_tool = False
        for capability_id in explicit:
            node = self.capability_tree.leaf(capability_id)
            for skill_id in node.skill_ids if node is not None else []:
                skill = self.skill_loader.find(skill_id)
                if skill is not None and skill.skill_type in {"tool", "model"}:
                    has_specific_tool = True
                    break
            if has_specific_tool:
                break
        if not has_specific_tool:
            return capability_ids

        filtered: list[str] = []
        for capability_id in capability_ids:
            if capability_id in explicit or not capability_id.startswith("skill."):
                filtered.append(capability_id)
                continue
            node = self.capability_tree.leaf(capability_id)
            skill_types = {
                skill.skill_type
                for skill_id in node.skill_ids if node is not None
                if (skill := self.skill_loader.find(skill_id)) is not None
            }
            if "modality" not in skill_types:
                filtered.append(capability_id)
        return filtered

    def build_capability_recommendation(
        self,
        routing: dict[str, Any],
    ) -> CapabilityRecommendation:
        if self.capability_tree is None:
            raise RuntimeError("CapabilityTree 尚未配置")
        items: list[CapabilityRecommendationItem] = []
        for capability_id in routing.get("capability_ids") or []:
            node = self.capability_tree.leaf(str(capability_id))
            if node is None:
                continue
            items.append(
                CapabilityRecommendationItem(
                    capability_id=node.id,
                    label=node.label,
                    description=node.description,
                    execution_level=(
                        "structured"
                        if any(
                            method.execution_mode == "runner"
                            for method in self.registry.methods_for(node.id)
                        )
                        else "planning"
                        if self.registry.methods_for(node.id)
                        else "advisory"
                    ),
                    skill_ids=node.skill_ids,
                    tree_path=self.capability_tree.label_path_for(node.id),
                )
            )
        labels = [item.label for item in items]
        plan_kind = "atomic" if len(items) == 1 else "composite"
        return CapabilityRecommendation(
            title=labels[0] if plan_kind == "atomic" and labels else "Skill 能力组合建议",
            summary=" → ".join(labels) if labels else str(routing.get("reason") or ""),
            plan_kind=plan_kind,
            fully_executable=all(
                item.execution_level == "structured" for item in items
            ),
            items=items,
        )

    def recommendation_context(
        self,
        capability_ids: list[str],
    ) -> list[dict[str, Any]]:
        return self._candidate_context(capability_ids)

    async def draft(
        self,
        request: ChatRequest,
        routing: dict[str, Any] | None = None,
    ) -> tuple[Workflow, str]:
        decision = routing or await self.assess_task(request)
        if not decision.get("recommend_workflow"):
            raise ValueError("当前需求没有匹配到可生成任务的能力")
        workflow, content = await self._build_dynamic(request, decision)
        self.store.save_workflow(workflow, event_type="workflow_created")
        return workflow.model_copy(deep=True), content

    async def replan(
        self,
        workflow_id: str,
        expected_revision: int,
    ) -> tuple[Workflow, str]:
        with self._lock:
            current = self._require(workflow_id)
            self._check_revision(current, expected_revision)
            if current.status == "confirmed":
                raise ValueError("已确认的流程不可覆盖，请创建新流程")
            snapshot = current.model_copy(deep=True)

        request = ChatRequest(
            message=snapshot.original_request,
            dataset_id=snapshot.dataset_id,
            interaction_mode="task",
        )
        routing = ({
            "recommend_workflow": True,
            "capability_ids": snapshot.requested_capabilities,
            "decision_source": "user_edited_scope",
        } if snapshot.excluded_capabilities else await self.assess_task(request))
        if not routing.get("recommend_workflow"):
            raise ValueError("重新规划时没有匹配到可生成任务的能力")
        replacement, content = await self._build_dynamic(
            request,
            routing,
            existing=snapshot,
        )
        self._preserve_step_configuration(replacement, snapshot)
        with self._lock:
            latest = self._require(workflow_id)
            self._check_revision(latest, expected_revision)
            self.store.save_workflow(
                replacement,
                event_type="workflow_replanned",
                event_payload={"previous_revision": expected_revision},
            )
        return replacement.model_copy(deep=True), content

    async def complete_dependencies(
        self,
        workflow_id: str,
        expected_revision: int,
    ) -> Workflow:
        with self._lock:
            current = self._require(workflow_id)
            self._check_revision(current, expected_revision)
            if current.status == "confirmed":
                raise ValueError("已确认的流程不可补充依赖，请创建新流程")
            snapshot = current.model_copy(deep=True)

        routing = {
            "capability_ids": snapshot.requested_capabilities,
            "decision_source": "dependency_resolver",
        }
        request = ChatRequest(
            message=snapshot.original_request,
            dataset_id=snapshot.dataset_id,
            interaction_mode="task",
        )
        replacement, _content = await self._build_dynamic(
            request,
            routing,
            existing=snapshot,
            dependency_policy="complete",
        )
        self._preserve_step_configuration(replacement, snapshot)
        with self._lock:
            latest = self._require(workflow_id)
            self._check_revision(latest, expected_revision)
            self.store.save_workflow(
                replacement,
                event_type="workflow_dependencies_completed",
                event_payload={"requested_capabilities": snapshot.requested_capabilities},
            )
        return replacement.model_copy(deep=True)

    def _preserve_step_configuration(self, replacement: Workflow, snapshot: Workflow) -> None:
        """Keep compatible user choices and bindings when the task chain changes."""
        previous_steps = {step.capability: step for step in snapshot.steps}
        for step in replacement.steps:
            previous = previous_steps.get(step.capability)
            if previous is not None:
                step.manual_input_types = list(previous.manual_input_types)
            if previous is None or previous.selected_method_id is None:
                continue
            method = next(
                (
                    option
                    for option in step.method_options
                    if option.id == previous.selected_method_id and option.compatible
                ),
                None,
            )
            if method is None:
                continue
            step.selected_method_id = method.id
            declared = {spec.id for spec in method.parameters}
            step.selected_parameters = {
                **self._default_parameters(method),
                **{
                    key: value
                    for key, value in previous.selected_parameters.items()
                    if key in declared
                },
            }
            step.input_bindings = previous.input_bindings

        self._revalidate_chain(replacement)
        self._resolve_workflow_inputs(replacement)
        self._refresh(replacement)

    def get(self, workflow_id: str) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            # Warnings are derived state. Refresh them on reads so persisted task
            # cards immediately benefit from newer context-sensitive warning rules.
            self._refresh_execution_summary(workflow)
            return workflow.model_copy(deep=True)

    def list(self, limit: int = 50) -> list[Workflow]:
        workflows = self.store.list_workflows(limit)
        for workflow in workflows:
            if workflow.locked_at is None and workflow.status != "confirmed":
                self._revalidate_chain(workflow, check_runtime=False)
                self._refresh(workflow)
            self._refresh_execution_summary(workflow)
        return workflows

    def events(self, workflow_id: str) -> list[dict[str, Any]]:
        self._require(workflow_id)
        return self.store.workflow_events(workflow_id)

    def select_method(
        self,
        workflow_id: str,
        step_id: str,
        method_id: str,
        expected_revision: int,
    ) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            self._ensure_editable_chain(workflow)
            self._revalidate_chain(workflow)
            step = self._step(workflow, step_id)
            method = next((item for item in step.method_options if item.id == method_id), None)
            if method is None:
                raise ValueError(f"方法 {method_id} 不属于步骤 {step_id}")
            if not method.compatible:
                raise ValueError("该方法与当前数据或上游输出不兼容：" + "；".join(method.blocked_reasons))
            step.selected_method_id = method.id
            step.selected_parameters = self._default_parameters(method)
            self._clear_review(workflow)
            self._revalidate_chain(workflow)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(
                workflow,
                "method_selected",
                {"step_id": step_id, "method_id": method_id},
            )
            return workflow.model_copy(deep=True)

    def remove_step(self, workflow_id: str, step_id: str, expected_revision: int) -> Workflow:
        """Remove an operation, keeping downstream input requirements explicit."""
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            self._ensure_editable_chain(workflow)
            removed = self._step(workflow, step_id)
            if len(workflow.steps) == 1:
                raise ValueError("流程至少需要保留一个步骤。")
            position = workflow.steps.index(removed)
            selected = next((m for m in removed.method_options if m.id == removed.selected_method_id), None)
            producers = [selected] if selected else removed.method_options
            output_types = {output.type for method in producers for output in method.output_slots
                            if selected is None or self._output_generated(output, removed.selected_parameters)}
            output_types.discard("execution_log")
            for step in workflow.steps[position + 1:]:
                # A direct binding is authoritative; before method selection,
                # retain the hole for any method with a matching declared slot.
                affected = {
                    slot.type for method in step.method_options for slot in method.input_slots
                    if slot.type in output_types and (
                        not step.input_bindings.get(slot.id)
                        or step.input_bindings[slot.id].upstream_step_id == removed.id
                    )
                }
                step.manual_input_types = sorted(set(step.manual_input_types) | affected)
                step.input_bindings = {key: binding for key, binding in step.input_bindings.items()
                                       if binding.upstream_step_id != removed.id}
            workflow.steps.remove(removed)
            workflow.excluded_capabilities = list(dict.fromkeys([*workflow.excluded_capabilities, removed.capability]))
            # The remaining visible chain becomes the user's chosen scope.
            workflow.requested_capabilities = [step.capability for step in workflow.steps]
            for index, step in enumerate(workflow.steps):
                step.order = index + 1
                step.depends_on = [workflow.steps[index - 1].id] if index else []
                step.origin = "requested"
            workflow.plan_kind = "atomic" if len(workflow.steps) == 1 else "composite"
            workflow.template_id = "dynamic:" + "+".join(workflow.requested_capabilities)
            workflow.title = " → ".join(step.title for step in workflow.steps)
            workflow.summary = "按你的选择保留：" + " → ".join(step.title for step in workflow.steps)
            self._clear_review(workflow)
            self._revalidate_chain(workflow)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(workflow, "workflow_step_removed", {"step_id": removed.id, "capability": removed.capability})
            return workflow.model_copy(deep=True)

    def bind_input(
        self,
        workflow_id: str,
        step_id: str,
        slot_id: str,
        root_id: str,
        relative_path: str,
        expected_revision: int,
    ) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            if workflow.status == "confirmed":
                raise ValueError("流程已经确认，不能继续修改输入")
            if workflow.locked_at is None:
                raise ValueError("请先确定流程链，再配置输入")
            step = self._step(workflow, step_id)
            method = self._selected_method(step)
            slot = next((item for item in method.input_slots if item.id == slot_id), None)
            if slot is None:
                raise ValueError(f"方法 {method.label} 没有输入槽位 {slot_id}")
            if "existing_path" not in slot.source_options:
                raise ValueError(f"输入 {slot.label} 不允许绑定已有路径")
            root, candidate, normalized = self.dataset_service.resolve_artifact_path(
                root_id,
                relative_path,
            )
            if slot.binding == "folder" and not candidate.is_dir():
                raise ValueError(f"输入 {slot.label} 必须选择文件夹")
            if slot.binding == "file" and not candidate.is_file():
                raise ValueError(f"输入 {slot.label} 必须选择文件")
            if candidate.is_file() and slot.formats:
                lowered = candidate.name.lower()
                if not any(lowered.endswith(item.lower()) for item in slot.formats):
                    raise ValueError(
                        f"输入 {slot.label} 仅接受：{', '.join(slot.formats)}"
                    )
            messages = ["路径存在且位于后端授权的数据根目录中。"]
            if slot.companions:
                messages.append("仍需在 dry-run 检查配套文件：" + ", ".join(slot.companions))
            preview = None
            if workflow.dataset_id:
                preview = self.dataset_service.preview_sample_mapping(
                    workflow.dataset_id,
                    root_id,
                    relative_path,
                    binding=slot.binding,
                    formats=slot.formats,
                )
                workflow.dataset = self.dataset_service.get(workflow.dataset_id)
                if not preview.can_apply:
                    raise ValueError("样本路径规则未覆盖全部样本，请检查匹配预览后重新选择")
                messages = [*preview.messages, *messages]
            label = candidate.name or root.label
            if preview and preview.binding_mode == "per_sample":
                label = f"{preview.coverage.matched} 个样本 · {preview.path_template}"
            step.input_bindings[slot.id] = InputBinding(
                slot_id=slot.id,
                artifact_type=slot.type,
                source="existing_path",
                label=label,
                root_id=root.root_id,
                relative_path=normalized,
                absolute_path=str(candidate),
                binding_mode=preview.binding_mode if preview else "single",
                dataset_id=workflow.dataset_id if preview else None,
                path_template=preview.path_template if preview else "",
                variables=preview.variables if preview else [],
                coverage=preview.coverage if preview else None,
                sample_matches=preview.matches if preview else [],
                status="validated" if preview else "selected",
                messages=messages,
            )
            self._clear_review(workflow)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(
                workflow,
                "workflow_input_bound",
                {
                    "step_id": step_id,
                    "slot_id": slot_id,
                    "relative_path": normalized,
                    "binding_mode": preview.binding_mode if preview else "single",
                    "path_template": preview.path_template if preview else "",
                },
            )
            return workflow.model_copy(deep=True)

    def preview_input_mapping(
        self,
        workflow_id: str,
        step_id: str,
        slot_id: str,
        root_id: str,
        relative_path: str,
    ) -> DatasetPathPreview:
        with self._lock:
            workflow = self._require(workflow_id)
            if workflow.status == "confirmed":
                raise ValueError("流程已经确认，不能继续修改输入")
            if workflow.locked_at is None:
                raise ValueError("请先确定流程链，再配置输入")
            if not workflow.dataset_id:
                raise ValueError("当前流程没有关联数据集，无法生成样本路径规则")
            step = self._step(workflow, step_id)
            method = self._selected_method(step)
            slot = next((item for item in method.input_slots if item.id == slot_id), None)
            if slot is None:
                raise ValueError(f"方法 {method.label} 没有输入槽位 {slot_id}")
            if "existing_path" not in slot.source_options:
                raise ValueError(f"输入 {slot.label} 不允许绑定已有路径")
            return self.dataset_service.preview_sample_mapping(
                workflow.dataset_id,
                root_id,
                relative_path,
                binding=slot.binding,
                formats=slot.formats,
            )

    def _historical_input_target(self, workflow_id, step_id, slot_id, expected_revision=None):
        workflow = self._require(workflow_id)
        if expected_revision is not None:
            self._check_revision(workflow, expected_revision)
        if workflow.status == "confirmed" or workflow.locked_at is None:
            raise ValueError("请先锁定可编辑的流程链，再选择历史输入")
        step = self._step(workflow, step_id)
        slot = next((item for item in self._selected_method(step).input_slots if item.id == slot_id), None)
        if slot is None or "existing_path" not in slot.source_options:
            raise ValueError("当前方法输入不接受已有文件")
        return workflow.model_copy(deep=True), slot

    def historical_input_candidates(self, workflow_id, step_id, slot_id, offset=0):
        with self._lock:
            workflow, slot = self._historical_input_target(workflow_id, step_id, slot_id)
        return HistoricalInputs(self.store).candidates(workflow, slot, offset=offset)

    def preview_historical_input(self, workflow_id, step_id, slot_id, request):
        with self._lock:
            workflow, slot = self._historical_input_target(workflow_id, step_id, slot_id, request.expected_revision)
        preview, _ = HistoricalInputs(self.store).preview(workflow, slot, request.run_id, request.group_id, allow_partial=True)
        with self._lock:
            self._check_revision(self._require(workflow_id), request.expected_revision)
        return preview

    def bind_historical_input(self, workflow_id, step_id, slot_id, request):
        with self._lock:
            workflow, slot = self._historical_input_target(workflow_id, step_id, slot_id, request.expected_revision)
        # Filesystem work is outside the global workflow lock. Apply rechecks the
        # source and uses CAS so a preview can never overwrite newer parameters.
        preview, binding = HistoricalInputs(self.store).preview(workflow, slot, request.run_id, request.group_id,
                                                               allow_partial=request.allow_partial)
        if not preview["can_apply"]:
            raise ValueError("历史输出未能唯一覆盖所有样本；可明确选择仅使用匹配样本，至少需匹配一个样本")
        with self._lock:
            current, _ = self._historical_input_target(workflow_id, step_id, slot_id, request.expected_revision)
            self._step(current, step_id).input_bindings[slot_id] = binding
            self._clear_review(current)
            self._advance(current)
            self._refresh(current)
            self._save(current, "workflow_historical_input_bound",
                       {"step_id": step_id, "slot_id": slot_id, "run_id": request.run_id,
                        "group_id": request.group_id, "sample_count": preview["coverage"]["matched"]})
            return current.model_copy(deep=True)

    def lock_chain(self, workflow_id: str, expected_revision: int) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            self._ensure_editable_chain(workflow)
            self._revalidate_chain(workflow)
            self._resolve_workflow_inputs(workflow)
            if any(step.selected_method_id is None for step in workflow.steps):
                raise ValueError("仍有步骤尚未选择可兼容的方法，不能锁定流程链")
            workflow.locked_at = self._now()
            self._clear_review(workflow)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(workflow, "chain_locked")
            return workflow.model_copy(deep=True)

    def change_dataset(self, workflow_id: str, dataset_id: str, expected_revision: int) -> Workflow:
        """Replace the draft's dataset and invalidate input choices from its old snapshot."""
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            if workflow.locked_at is not None or workflow.status == "confirmed":
                raise ValueError("流程已锁定，请先解锁流程再更换数据集；已确认流程请新建对话。")
            dataset = self.dataset_service.get(dataset_id)
            if workflow.dataset == dataset:
                return workflow.model_copy(deep=True)
            previous_dataset_id = workflow.dataset_id
            workflow.dataset_id = dataset.dataset_id
            workflow.dataset = dataset
            for step in workflow.steps:
                step.input_bindings = {}
                step.command_preview = None
            self._clear_review(workflow)
            self._revalidate_chain(workflow)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(workflow, "workflow_dataset_changed", {
                "previous_dataset_id": previous_dataset_id, "dataset_id": dataset_id,
            })
            return workflow.model_copy(deep=True)

    def unlock_chain(self, workflow_id: str, expected_revision: int) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            if workflow.status == "confirmed":
                raise ValueError("已确认的流程不可解锁，请创建新流程")
            if workflow.locked_at is None:
                raise ValueError("流程链尚未锁定")
            workflow.locked_at = None
            self._clear_review(workflow)
            self._revalidate_chain(workflow, check_runtime=False)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(workflow, "chain_unlocked")
            return workflow.model_copy(deep=True)

    def update_parameters(
        self,
        workflow_id: str,
        step_id: str,
        parameters: dict[str, Any],
        expected_revision: int,
    ) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            if workflow.status == "confirmed":
                raise ValueError("流程已经确认，不能继续修改参数")
            if workflow.locked_at is None:
                raise ValueError("请先确定流程链，再配置参数")
            step = self._step(workflow, step_id)
            method = self._selected_method(step)
            specs = {spec.id: spec for spec in method.parameters}
            unknown = sorted(set(parameters) - set(specs))
            if unknown:
                raise ValueError(f"包含未声明的参数：{', '.join(unknown)}")
            merged = {**step.selected_parameters}
            for parameter_id, value in parameters.items():
                spec = specs[parameter_id]
                if value is None and not spec.required:
                    merged.pop(parameter_id, None)
                else:
                    merged[parameter_id] = value
            self._validate_method_parameters(method, merged)
            step.selected_parameters = merged
            self._resolve_workflow_inputs(workflow)
            self._clear_review(workflow)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(
                workflow,
                "parameters_updated",
                {"step_id": step_id, "parameter_ids": sorted(parameters)},
            )
            return workflow.model_copy(deep=True)

    def review_parameters(self, workflow_id: str, expected_revision: int) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            if workflow.locked_at is None:
                raise ValueError("请先锁定流程链")
            self._resolve_workflow_inputs(workflow)
            missing = [
                f"{step.title}：{', '.join(step.missing_required_inputs)}"
                for step in workflow.steps
                if step.missing_required_inputs
            ]
            if missing:
                raise ValueError("仍有必需输入未绑定：" + "；".join(missing))
            workflow.sample_scope = partial_sample_scope(workflow)
            if workflow.sample_scope is not None and not workflow.sample_scope.eligible_sample_ids:
                raise ValueError("各输入没有共同匹配的样本，无法执行；请调整历史输入或补齐文件")
            self._validate_all_parameters(workflow)
            workflow.parameters_reviewed_at = self._now()
            workflow.dry_run_report = None
            self._advance(workflow)
            self._refresh(workflow)
            self._save(workflow, "parameters_reviewed")
            return workflow.model_copy(deep=True)

    def dry_run(self, workflow_id: str, expected_revision: int) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
        if workflow.parameters_reviewed_at is None:
            raise ValueError("请先审阅并确认参数")
        self._validate_all_parameters(workflow)
        declared_runners = self.registry.runner_ids()
        selected_methods = [self._selected_method(step) for step in workflow.steps]
        workflow.sample_scope = partial_sample_scope(workflow)
        checked_workflow = restrict_sample_bindings(workflow, workflow.sample_scope)
        try:
            execution_units = RecipeCompiler(self.registry).compile(checked_workflow)
        except RecipeCompilationError as exc:
            raise ValueError(f"执行配方无法展开：{exc}") from exc
        dataset_required = any(
            not method.input_slots and "*" not in method.input_types
            for method in selected_methods
        )
        dataset_valid = bool(
            workflow.dataset
            and Path(workflow.dataset.absolute_path).is_dir()
            and workflow.dataset_id
        )
        history_problems = HistoricalInputs(self.store).validate_workflow(workflow)
        structured_inputs_valid = not history_problems and all(
            not step.missing_required_inputs
            and all(
                binding.source == "upstream_output"
                or self._binding_paths_exist(binding)
                for binding in step.input_bindings.values()
            )
            for step, method in zip(checked_workflow.steps, selected_methods, strict=True)
            if method.input_slots
        )
        dataset_check_passed = (
            (dataset_valid or not dataset_required) and structured_inputs_valid
        )
        commands: list[DryRunCommand] = []
        for unit in execution_units:
            checkpoint(f"检查步骤：{unit.step.title}")
            step, method = unit.step, unit.method
            runner_valid = (
                method.execution_mode == "planning"
                or method.runner_id in declared_runners
            )
            messages: list[str] = (
                ["规划型步骤：只校验参数和流程连接，不对应可执行 runner"]
                if method.execution_mode == "planning"
                else [] if runner_valid else ["runner_id 未在受信任注册表中声明"]
            )
            command_valid = runner_valid
            if (
                runner_valid
                and method.execution_mode == "runner"
                and self.runner_registry is not None
            ):
                preflight_problems = self.runner_registry.preflight_snapshot(
                    workflow, step, method
                )
                messages.extend(preflight_problems)
                for slot_id, binding in step.input_bindings.items():
                    if binding.source == "upstream_output":
                        messages.append(
                            f"输入 {slot_id} 将由上游步骤 {binding.upstream_step_id} "
                            f"的输出 {binding.output_slot_id} 提供；"
                            "流程连接已校验，实际文件及内容将在执行该步骤前检查。"
                        )
                if not preflight_problems and step.selected_parameters.get("backend") == "cuda":
                    messages.append("CUDA 方法将在实际执行节点再次检测 GPU；无显卡的主节点请使用 Slurm 并申请 GPU")
                command_valid = command_valid and not preflight_problems
            commands.append(
                DryRunCommand(
                    step_id=step.id,
                    runner_id=method.runner_id,
                    command_preview=self._command_preview(
                        method,
                        step.selected_parameters,
                        workflow.dataset,
                        step.input_bindings,
                    ),
                    execution_mode=method.execution_mode,
                    valid=command_valid,
                    messages=messages,
                )
            )
        available_runner_ids = (
            {unit.method.runner_id for unit in execution_units
             if self.runner_registry.get(unit.method.runner_id)
             and self.runner_registry.get(unit.method.runner_id).runtime_status().get("available")}
            if self.runner_registry is not None
            else self.executable_runner_ids
        )
        execution_enabled = bool(execution_units) and all(
            unit.method.execution_mode == "runner"
            and unit.method.runner_id in available_runner_ids
            for unit in execution_units
        )
        warnings = ["Dry-run 已验证流程、参数、路径和 runner 声明，尚未运行处理软件。", *history_problems]
        if workflow.sample_scope is not None:
            count = len(workflow.sample_scope.eligible_sample_ids)
            warnings.append(f"仅运行共同匹配的 {count} / {workflow.sample_scope.total} 个样本；其余样本不提交执行。")
            dataset_check_passed = dataset_check_passed and count > 0
        if any(unit.method.execution_mode == "planning" for unit in execution_units):
            warnings.append("流程包含规划型步骤；这些步骤只形成参数快照，不生成可执行命令。")
        unavailable_runners = sorted(
            {
                unit.method.runner_id
                for unit in execution_units
                if unit.method.execution_mode == "runner"
                and unit.method.runner_id not in available_runner_ids
            }
        )
        if unavailable_runners:
            warnings.append(
                "以下 Runner 尚未接入可信实现或当前环境依赖不可用："
                + "、".join(unavailable_runners)
            )
        if execution_enabled:
            warnings.append("所有步骤都已接入受信任 Worker；最终确认后可以启动真实运行。")
        if dataset_required and not dataset_valid:
            warnings.append("未关联有效的数据集目录，无法通过 dry-run。")
        if not structured_inputs_valid:
            warnings.append("存在未绑定或已经失效的方法输入路径，无法通过 dry-run。")
        valid = dataset_check_passed and all(command.valid for command in commands)
        workflow.dry_run_report = DryRunReport(
            valid=valid,
            execution_enabled=execution_enabled,
            dataset_path_validated=dataset_check_passed,
            commands=commands,
            warnings=warnings,
            checked_at=self._now(),
        )
        with self._lock:
            checkpoint()
            self._check_revision(self._require(workflow_id), expected_revision)
            self._advance(workflow)
            self._refresh(workflow)
            self._save(workflow, "dry_run_completed", {"valid": valid})
            return workflow.model_copy(deep=True)

    def confirm(self, workflow_id: str, expected_revision: int) -> Workflow:
        with self._lock:
            workflow = self._require(workflow_id)
            self._check_revision(workflow, expected_revision)
            if (
                workflow.status != "ready"
                or workflow.dry_run_report is None
                or not workflow.dry_run_report.valid
            ):
                raise ValueError("流程尚未通过参数审阅和 dry-run，不能确认")
            workflow.status = "confirmed"
            workflow.confirmed_at = self._now()
            workflow.can_lock = False
            workflow.can_unlock = False
            workflow.can_review_parameters = False
            workflow.can_dry_run = False
            workflow.can_confirm = False
            self._advance(workflow)
            for step in workflow.steps:
                step.status = "confirmed"
            self._save(workflow, "workflow_confirmed")
            return workflow.model_copy(deep=True)

    async def _build_dynamic(
        self,
        request: ChatRequest,
        routing: dict[str, Any],
        existing: Workflow | None = None,
        dependency_policy: str = "target_only",
    ) -> tuple[Workflow, str]:
        if self.capability_tree is None:
            raise RuntimeError("CapabilityTree 尚未配置")
        dataset = self.dataset_service.get(request.dataset_id) if request.dataset_id else None
        initial_types = set(dataset.inspection.input_types if dataset else ["dataset_folder"])
        excluded = set(existing.excluded_capabilities if existing else [])
        reused_inputs = (set(existing.input_capabilities if existing else [])
                         | set(routing.get("routing_trace", {}).get("reused_input_capabilities", []))
                         | existing_input_capabilities(request.message))
        if existing:
            initial_types.update(value for step in existing.steps for value in step.manual_input_types)
        requested_capability_ids = order_capabilities(self.registry, [
            item for item in routing.get("capability_ids") or []
            if item not in reused_inputs and item not in excluded
        ], self._declared_order)
        capability_ids = (
            self._expand_and_order_capabilities(
                requested_capability_ids, initial_types, excluded | reused_inputs,
                {step.capability: (self._selected_method(step), step.selected_parameters)
                 for step in existing.steps if step.selected_method_id} if existing else None,
            )
            if dependency_policy == "complete"
            else requested_capability_ids
        )
        capability_ids = order_capabilities(self.registry, capability_ids, self._declared_order)
        if not capability_ids:
            raise ValueError("能力路由没有返回可用任务")
        candidate_context = self._candidate_context(capability_ids)
        for candidate in candidate_context:
            candidate["methods"] = [
                method for method in candidate["methods"]
                if not (set(method.get("included_capabilities", [])) | {
                    step["capability"] for step in (method.get("execution_recipe") or {}).get("steps", [])
                }) & (excluded | reused_inputs)
            ]
        planning = await self.chat_service.plan_capability_chain(
            request,
            candidate_context,
            dataset.inspection.model_dump(mode="json") if dataset else None,
        )
        recommendations = planning["recommendations"]
        reasons = planning["reasons"]

        steps: list[WorkflowStep] = []
        available_types = set(initial_types)
        features = dataset.inspection.features if dataset else {}
        previous_step_id: str | None = None
        for capability_id in capability_ids:
            node = self.capability_tree.leaf(capability_id)
            if node is None:
                raise RuntimeError(f"能力树中不存在叶子能力：{capability_id}")
            all_definitions = self.registry.selectable_methods_for(capability_id)
            if not all_definitions:
                raise RuntimeError(f"能力 {capability_id} 没有注册任何方法")
            # Keep the task-specific shortlist, but restore methods hidden only
            # because the user removed an operation or plans to reuse its output.
            method_candidate_ids = list(planning.get("method_candidates", {}).get(capability_id, []))
            previous_step = next((step for step in existing.steps if step.capability == capability_id), None) if existing else None
            if method_candidate_ids:
                if previous_step and previous_step.selected_method_id:
                    method_candidate_ids.append(previous_step.selected_method_id)
                method_candidate_ids.extend(method.method_id for method in all_definitions
                                            if self._scope_conflicts(method, excluded | reused_inputs))
                # A recommendation shortlist must not hide the direct existing-
                # input method behind newly added composite alternatives.
                method_candidate_ids.extend(method.method_id for method in all_definitions
                                            if method.default_recommended)
            definitions = [method for method in all_definitions if method.method_id in method_candidate_ids] or all_definitions
            options = [
                self._option(method, available_types, features, dataset is not None)
                for method in definitions
            ]
            for option in options:
                self._restrict_method_scope(option, excluded | reused_inputs)
            compatible = [option for option in options if option.compatible]
            recommendable = [option for option in compatible if not option.scope_warnings]
            recommendable = [option for option in recommendable if not option.input_warnings] or recommendable
            requested_method = recommendations.get(capability_id)
            preferred = next(
                (option for option in recommendable if option.id == requested_method),
                None,
            ) or next(
                (
                    option
                    for option in recommendable
                    if self._definition_default(definitions, option.id)
                ),
                None,
            )
            if preferred is None and recommendable:
                preferred = recommendable[0]
            for option in options:
                option.recommended = bool(preferred and option.id == preferred.id)
                option.recommendation_reason = (
                    str(reasons.get(capability_id) or "")
                    if option.recommended and option.id == requested_method
                    else self._definition_reason(definitions, option.id)
                )

            selection = "auto" if len(definitions) == 1 else "user"
            selected_id = preferred.id if selection == "auto" and preferred else None
            selected_parameters = (
                self._default_parameters(preferred) if selected_id and preferred else {}
            )
            step_id = re.sub(r"[^a-z0-9]+", "_", capability_id.lower()).strip("_")
            step = WorkflowStep(
                id=step_id,
                order=len(steps) + 1,
                title=node.label,
                description=node.description,
                capability=capability_id,
                origin=(
                    "requested"
                    if capability_id in requested_capability_ids
                    else "dependency"
                ),
                selection=selection,
                depends_on=[previous_step_id] if previous_step_id else [],
                status="configured" if selected_id else "needs_method",
                method_options=options,
                selected_method_id=selected_id,
                selected_parameters=selected_parameters,
            )
            steps.append(step)
            if selected_id:
                available_types.update(self._selected_method(step).output_types)
            else:
                for option in compatible:
                    if option.scope_warnings:
                        continue
                    available_types.update(option.output_types)
            previous_step_id = step.id

        now = self._now()
        warnings: list[str] = []
        dataset_required = any(
            "*" not in option.input_types
            for step in steps
            for option in step.method_options
        )
        if dataset is None:
            warnings.append(
                "尚未关联数据集；可以规划，但 dry-run 前必须选择并检查数据目录。"
                if dataset_required
                else "当前规划型步骤不要求关联数据集目录。"
            )
        routing_source = str(routing.get("decision_source") or "unknown")
        planning_source = str(planning.get("planner_source") or "unknown")
        if "heuristic_after_" in routing_source or "heuristic_after_" in planning_source:
            warnings.append("模型规划暂时不可用，当前推荐由本地能力图安全回退生成。")
        execution_modes = {
            option.execution_mode
            for step in steps
            for option in step.method_options
        }
        workflow_execution_mode = (
            "mixed"
            if len(execution_modes) > 1
            else next(iter(execution_modes), "planning")
        )
        workflow = Workflow(
            workflow_id=existing.workflow_id if existing else f"wf_{uuid4().hex[:12]}",
            template_id="dynamic:" + "+".join(capability_ids),
            revision=existing.revision + 1 if existing else 1,
            title=planning["workflow_title"],
            summary=planning["workflow_summary"],
            original_request=request.message,
            status="awaiting_method_choice",
            dataset_id=dataset.dataset_id if dataset else None,
            dataset=dataset,
            planner_source=f"capability-tree:{routing_source}/{planning_source}",
            execution_mode=workflow_execution_mode,
            plan_kind=(
                "atomic"
                if len(requested_capability_ids) == 1
                else "composite"
            ),
            requested_capabilities=requested_capability_ids,
            excluded_capabilities=sorted(excluded),
            input_capabilities=sorted(reused_inputs),
            dependency_policy=("complete" if dependency_policy == "complete" else "target_only"),
            steps=steps,
            warnings=warnings,
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self._revalidate_chain(workflow)
        self._resolve_workflow_inputs(workflow)
        self._refresh(workflow)
        return workflow, planning["assistant_message"]

    def _specific_intent_catalog(
        self,
        allowed: list[str],
        included_skill_capabilities: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.capability_tree is None:
            return []
        included_skills = set(included_skill_capabilities or [])
        catalog: list[dict[str, Any]] = []
        for node in self.capability_tree.leaves():
            if node.id not in allowed:
                continue
            if node.id.startswith("skill.") and node.id not in included_skills:
                continue
            methods = self.registry.methods_for(node.id)
            if not methods:
                continue
            operation_options = [
                {
                    "value": option.value,
                    "label": option.label,
                    "description": option.description,
                }
                for method in methods
                for parameter in method.parameters
                if parameter.id == "operation"
                for option in parameter.options[:12]
            ]
            catalog.append(
                {
                    "capability_id": node.id,
                    "label": node.label,
                    "description": node.description,
                    "keywords": node.keywords[:8],
                    "input_types": sorted(
                        {item for method in methods for item in method.input_types}
                    ),
                    "output_types": sorted(
                        {item for method in methods for item in method.output_types}
                    ),
                    "task_options": operation_options,
                }
            )
        return catalog

    def _heuristic_capabilities(
        self,
        request: ChatRequest,
        allowed: list[str],
    ) -> list[str]:
        """Deterministic fallback used only when the router model is unavailable."""
        lowered = request.message.lower()
        conceptual = any(
            token in lowered
            for token in (
                "是什么",
                "什么意思",
                "有什么区别",
                "原理",
                "介绍",
                "解释",
                "了解",
                "怎么理解",
                "what is",
                "explain",
            )
        )
        explicit_execution = any(
            token in lowered
            for token in (
                "做一下",
                "处理这个",
                "开始处理",
                "帮我做",
                "帮我处理",
                "运行",
                "执行",
                "进行",
                "生成",
                "run ",
                "execute",
            )
        )
        if conceptual and not explicit_execution:
            return []
        actionable = any(
            token in lowered
            for token in (
                "做",
                "处理",
                "整理",
                "转换",
                "配准",
                "预处理",
                "分割",
                "拟合",
                "去除",
                "提取",
                "重建",
                "训练",
                "预测",
                "清洗",
                "校正",
                "可视化",
                "使用",
                "采用",
                "用",
                "计算",
                "生成",
                "检查",
                "分析",
                "流程",
                "organize",
                "convert",
                "register",
                "registration",
                "preprocess",
                "calculate",
                "run",
                "use ",
                "using ",
                "segment",
                "segmentation",
                "进行",
                "执行",
                "完成",
                "开始",
                "想要",
                "需要",
                "希望",
                "帮我",
            )
        )
        if not actionable:
            return []

        dwi_context = bool(
            re.search(r"\b(dwi|dti|diffusion|qsiprep|eddy|dtifit)\b", lowered)
            or any(term in lowered for term in ("扩散磁共振", "扩散成像", "扩散指标"))
        )
        explicit_skill_capabilities = self._explicit_skill_capabilities(
            request.message,
            allowed,
        )
        patterns: list[tuple[str, tuple[str, ...]]] = [
            ("dwi.inspect", ("巡检", "检查数据", "检查这个数据", "inspect")),
            ("dwi.bids", ("bids", "整理数据", "组织数据")),
            ("image.registration", ("图像配准", "影像配准", "registration", "flirt", "ants", "syn")),
            ("dwi.report", ("报告", "qc", "质量控制", "结果汇总")),
            ("dwi.response", ("响应函数", "response function", "dwi2response", "dhollander", "tournier")),
            ("dwi.fod", ("纤维方向分布", "dwi2fod", "msmt-csd", "msmt_csd", "fod")),
            ("dwi.five_tt", ("5tt", "five tissue", "5ttgen", "五组织")),
            (
                "dwi.tractography",
                ("纤维追踪", "tractography", "probtrackx", "tckgen"),
            ),
            ("dwi.connectome", ("结构连接组", "connectome", "连接矩阵", "tck2connectome")),
        ]
        if not explicit_skill_capabilities:
            patterns.append(
                (
                    "skill.smri-skill",
                    (
                        "组织分割",
                        "组织分类",
                        "灰质白质脑脊液",
                        "tissue segmentation",
                        "tissue classification",
                        "gm/wm/csf",
                    ),
                )
            )
        if dwi_context:
            patterns.append(
                ("dwi.preprocess", ("预处理", "eddy", "topup", "qsiprep", "运动校正"))
            )
        matched: list[tuple[int, str]] = []
        for capability_id, terms in patterns:
            if capability_id in existing_input_capabilities(request.message):
                continue
            positions = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
            if positions and capability_id in allowed:
                matched.append((min(positions), capability_id))
        if (
            re.search(r"\b(fa|md|ad|rd|dti|dtifit|tensor)\b", lowered)
            or "张量" in lowered
            or "扩散指标" in lowered
        ) and "dwi.tensor_metrics" in allowed:
            matched.append((len(lowered), "dwi.tensor_metrics"))

        if matched:
            return list(
                dict.fromkeys(
                    capability_id
                    for _position, capability_id in sorted(matched)
                )
            )

        if (
            any(term in lowered for term in ("dwi", "dti", "扩散磁共振", "扩散成像"))
            and "dwi.preprocess" in allowed
        ):
            return ["dwi.preprocess"]

        if explicit_skill_capabilities:
            return explicit_skill_capabilities

        return []

    def _explicit_skill_capabilities(
        self,
        message: str,
        allowed: list[str],
    ) -> list[str]:
        """Match software/Skill names in the current turn before sticky selections."""
        if self.capability_retriever is not None:
            retrieved = [
                capability_id
                for capability_id in self.capability_retriever.explicit_capability_ids(message)
                if capability_id in allowed
            ]
            if retrieved:
                return retrieved[:4]

        lowered = message.lower()
        normalized_text = re.sub(r"[^a-z0-9]+", " ", lowered)
        explicit_aliases: dict[str, tuple[str, ...]] = {
            "skill.asl-skill": ("脑灌注", "动脉自旋标记"),
            "skill.dwi-skill": ("扩散磁共振", "扩散成像", "纤维追踪"),
            "skill.eeg-skill": ("脑电",),
            "skill.fmri-skill": ("功能磁共振", "功能连接"),
            "skill.meg-skill": ("脑磁",),
            "skill.pet-skill": ("正电子发射",),
            "skill.smri-skill": ("结构磁共振", "结构像"),
            "skill.table-cleaning": ("表格清洗", "缺失值", "异常值"),
            "skill.image-batch-processing": ("影像批处理", "图像批处理"),
            "skill.freesurfer-tool": (
                "FreeSurfer",
                "recon-all",
                "aseg",
                "aparc",
                "皮层重建",
                "皮层分割",
                "皮层下分割",
            ),
            "skill.wmh-segmentation": ("WMH", "白质高信号", "白质病灶"),
        }
        advisory_matches: list[tuple[int, str]] = []
        for node in (self.capability_tree.leaves() if self.capability_tree else []):
            if node.id not in allowed or not node.id.startswith("skill."):
                continue
            skill_name = node.skill_ids[0] if node.skill_ids else ""
            parts = [
                part
                for part in re.split(r"[-_]+", skill_name.lower())
                if part not in {"skill", "tool"}
            ]
            name_match = bool(parts) and all(
                re.search(rf"\b{re.escape(part)}\b", normalized_text)
                for part in parts
            )
            terms = [node.label, *explicit_aliases.get(node.id, ())]
            positions = [
                lowered.find(term.lower())
                for term in terms
                if len(term.strip()) >= 3 and lowered.find(term.lower()) >= 0
            ]
            if name_match:
                positions.append(
                    min(
                        position
                        for part in parts
                        if (position := normalized_text.find(part)) >= 0
                    )
                )
            if positions:
                advisory_matches.append((min(positions), node.id))
        return list(
            dict.fromkeys(
                capability_id
                for _position, capability_id in sorted(advisory_matches)
            )
        )[:4]

    def _expand_and_order_capabilities(
        self,
        requested: list[str],
        initial_types: set[str],
        excluded: set[str] | None = None,
        selected: dict[str, tuple[MethodOption, dict[str, Any]]] | None = None,
    ) -> list[str]:
        """Add only required producer capabilities and return a validated linear DAG."""
        allowed = set(self.registry.capabilities()) - (excluded or set())
        selected = selected or {}
        internal = {stage.capability for method, _values in selected.values()
                    if method.execution_recipe for stage in method.execution_recipe.steps}
        allowed -= internal - set(requested)
        result: list[str] = []
        available = set(initial_types)
        visiting: set[str] = set()
        explicit_prerequisites: dict[str, list[str]] = {
            "dwi.fod": ["dwi.response"],
            "dwi.tractography": ["dwi.fod", "dwi.five_tt"],
            "dwi.connectome": ["dwi.tractography"],
        }

        def accepts(method: CapabilityMethod) -> bool:
            return "*" in method.input_types or bool(available.intersection(method.input_types))

        def ensure(capability_id: str) -> None:
            if capability_id in result or capability_id not in allowed:
                return
            if capability_id in visiting:
                raise RuntimeError(f"能力依赖包含循环：{capability_id}")
            visiting.add(capability_id)
            selection = selected.get(capability_id)
            methods = [selection[0]] if selection else self.registry.methods_for(capability_id)
            required = ({slot.type for slot in selection[0].input_slots
                         if self._slot_required(slot, selection[1])} if selection else None)
            for prerequisite in explicit_prerequisites.get(capability_id, []):
                # A requested recomputation must still run; otherwise reuse a
                # prerequisite artifact already present in the inspected inputs.
                products = {item for method in self.registry.methods_for(prerequisite)
                            for item in method.output_types if item != 'execution_log'}
                if required is not None and not products.intersection(required):
                    continue
                if prerequisite not in requested and products.intersection(available):
                    continue
                ensure(prerequisite)
            ready = lambda: required.issubset(available) if required is not None else any(accepts(method) for method in methods)
            if methods and not ready():
                required_types = (required - available) if required is not None else {
                    input_type
                    for method in methods
                    for input_type in method.input_types
                    if input_type != "*"
                }
                producers: list[tuple[int, str]] = []
                for producer_id in self.registry.capabilities():
                    if producer_id not in allowed or producer_id == capability_id or producer_id in result:
                        continue
                    producer_methods = self.registry.methods_for(producer_id)
                    if not any(
                        required_types.intersection(method.output_types)
                        for method in producer_methods
                    ):
                        continue
                    can_start = any(accepts(method) for method in producer_methods)
                    producers.append((0 if can_start else 1, producer_id))
                for _rank, producer_id in sorted(producers):
                    ensure(producer_id)
                    if ready():
                        break
            visiting.remove(capability_id)
            result.append(capability_id)
            for method in methods:
                available.update(method.output_types)

        for capability_id in requested:
            ensure(capability_id)
        return result

    def _candidate_context(self, capability_ids: list[str]) -> list[dict[str, Any]]:
        if self.capability_tree is None:
            raise RuntimeError("CapabilityTree 尚未配置")
        context: list[dict[str, Any]] = []
        for capability_id in capability_ids:
            node = self.capability_tree.leaf(capability_id)
            if node is None:
                continue
            skill_context: list[dict[str, str]] = []
            for skill_id in node.skill_ids:
                skill = self.skill_loader.find(skill_id) if self.skill_loader else None
                if skill is None:
                    continue
                skill_context.append(
                    {
                        "skill_id": skill.name,
                        "description": skill.description,
                        "summary": skill.summary_zh or skill.summary_en,
                        "skill_excerpt": skill.prompt_excerpt(max_chars=1_200),
                    }
                )
            methods = []
            for method in self.registry.selectable_methods_for(capability_id):
                runtime_status: dict[str, Any] = {
                    "available": False if method.execution_mode == "planning" else None,
                    "reason": (method.execution_resolution.get("reason") or "规划方法没有执行入口")
                    if method.execution_mode == "planning" else "Runner 状态未注入",
                }
                if method.execution_mode == "runner" and self.runner_registry is not None:
                    recipe_methods = (
                        self.registry.recipe_methods(method.execution_recipe)
                        if method.execution_recipe is not None
                        else [method]
                    )
                    stage_statuses: list[dict[str, Any]] = []
                    for recipe_method in recipe_methods:
                        runner = self.runner_registry.get(recipe_method.runner_id)
                        stage_statuses.append(
                            runner.runtime_status()
                            if runner is not None
                            else {
                                "available": False,
                                "reason": f"尚未接入可信 Runner：{recipe_method.runner_id}",
                            }
                        )
                    unavailable = [
                        status for status in stage_statuses if not status.get("available")
                    ]
                    runtime_status = {
                        "available": not unavailable,
                        "reason": (
                            "执行配方中的 Runner 均可用"
                            if not unavailable and method.execution_recipe is not None
                            else "；".join(
                                str(status.get("reason") or "Runner 不可用")
                                for status in unavailable
                            )
                            if unavailable
                            else str(stage_statuses[0].get("reason") or "Runner 可用")
                        ),
                    }
                methods.append(
                    {
                        "method_id": method.method_id,
                        "skill_id": method.skill_id,
                        "label": method.label,
                        "description": method.description,
                        "execution_mode": method.execution_mode,
                        "input_types": method.input_types,
                        "output_types": method.output_types,
                        "requires_features": method.requires_features,
                        "default_recommended": method.default_recommended,
                        "default_reason": method.default_reason,
                        "structure_level": method.structure_level,
                        "delegate_skill_ids": method.delegate_skill_ids,
                        "runtime_status": runtime_status,
                        "execution_recipe": (
                            {
                                "recipe_id": method.execution_recipe.recipe_id,
                                "label": method.execution_recipe.label,
                                "steps": [
                                    {
                                        "id": step.id,
                                        "title": step.title,
                                        "method_id": step.method_id,
                                        "capability": step.capability,
                                    }
                                    for step in method.execution_recipe.steps
                                ],
                            }
                            if method.execution_recipe is not None
                            else None
                        ),
                        "included_capabilities": method.included_capabilities,
                        "inputs": [
                            {
                                "id": slot.id,
                                "type": slot.type,
                                "label": slot.label,
                                "description": slot.description,
                                "required": slot.required,
                                "required_when": slot.required_when,
                            }
                            for slot in method.input_slots
                        ],
                        "outputs": [
                            {
                                "id": slot.id,
                                "type": slot.type,
                                "label": slot.label,
                                "description": slot.description,
                                "generated_when": slot.generated_when,
                            }
                            for slot in method.output_slots
                        ],
                        "parameter_summary": [
                            {
                                "id": parameter.id,
                                "label": parameter.label,
                                "level": parameter.level,
                            }
                            for parameter in method.parameters
                        ],
                    }
                )
            context.append(
                {
                    "capability_id": capability_id,
                    "label": node.label,
                    "description": node.description,
                    "tree_path": self.capability_tree.path_for(capability_id),
                    "skills": skill_context,
                    "methods": methods,
                }
            )
        return context

    def _option(
        self,
        definition: CapabilityMethod,
        available_types: set[str],
        features: dict[str, bool],
        has_dataset: bool,
        check_runtime: bool = True,
    ) -> MethodOption:
        reasons: list[str] = []
        input_warnings: list[str] = []
        if (
            not definition.input_slots
            and "*" not in definition.input_types
            and not available_types.intersection(definition.input_types)
        ):
            input_warnings.append("尚未识别到所需输入：" + ", ".join(definition.input_types)
                                  + "。仍可选择；请核对输入，执行前会再次校验。")
        if has_dataset:
            missing_features = [
                feature for feature in definition.requires_features if not features.get(feature, False)
            ]
            if missing_features:
                input_warnings.append("数据集扫描尚未确认条件：" + ", ".join(missing_features)
                                      + "。扫描结果可能不完整，请核对实际输入。")
        if definition.input_slots:
            missing_types = {slot.type for slot in definition.input_slots
                             if slot.required and slot.type not in available_types}
            if missing_types:
                input_warnings.append("输入待补齐：" + "、".join(sorted(missing_types))
                                      + "。可以先选择方法，锁定流程后手动绑定文件。")
        if check_runtime and definition.execution_mode == "runner" and self.runner_registry is not None:
            recipe_methods = (
                self.registry.recipe_methods(definition.execution_recipe)
                if definition.execution_recipe is not None
                else [definition]
            )
            for recipe_method in recipe_methods:
                runner = self.runner_registry.get(recipe_method.runner_id)
                if runner is None:
                    reasons.append(f"尚未接入可信 Runner：{recipe_method.runner_id}")
                    continue
                runtime = runner.runtime_status()
                if not runtime.get("available"):
                    reasons.append(str(runtime.get("reason") or "运行环境暂不可用"))
        return MethodOption(
            id=definition.method_id,
            skill_id=definition.skill_id,
            label=definition.label,
            description=definition.description,
            runner_id=definition.runner_id,
            execution_mode=definition.execution_mode,
            input_types=definition.input_types,
            output_types=definition.output_types,
            requires_features=definition.requires_features,
            compatible=not reasons,
            blocked_reasons=reasons,
            input_warnings=input_warnings,
            parameters=definition.parameters,
            input_slots=definition.input_slots,
            output_slots=definition.output_slots,
            structure_level=definition.structure_level,
            source_references=definition.source_references,
            command_references=definition.command_references,
            delegate_skill_ids=definition.delegate_skill_ids,
            execution_recipe=definition.execution_recipe,
            included_capabilities=definition.included_capabilities,
            execution_resolution=definition.execution_resolution,
        )

    @staticmethod
    def _scope_conflicts(method: MethodOption | CapabilityMethod, excluded: set[str]) -> set[str]:
        included = set(method.included_capabilities)
        if method.execution_recipe:
            included.update(item.capability for item in method.execution_recipe.steps)
        return included & excluded

    def _restrict_method_scope(self, method: MethodOption, excluded: set[str]) -> None:
        conflicts = self._scope_conflicts(method, excluded)
        if conflicts:
            labels = []
            for capability in sorted(conflicts):
                node = self.capability_tree.leaf(capability) if self.capability_tree else None
                labels.append(node.label if node else capability)
            method.scope_warnings.append(
                "此方法内部仍包含已移除或计划复用的操作：" + "、".join(labels)
                + "。手动选择后将按该方法原有定义执行；如需复用已有结果，请选择对应的已有输入方法。")

    def _revalidate_chain(self, workflow: Workflow, *, check_runtime: bool = True) -> None:
        if workflow.locked_at is None and workflow.status != "confirmed":
            ordered = order_capabilities(self.registry, [step.capability for step in workflow.steps],
                                         self._declared_order)
            changed_order = ordered != [step.capability for step in workflow.steps]
            workflow.steps.sort(key=lambda step: ordered.index(step.capability))
            if changed_order:
                workflow.title = " → ".join(step.title for step in workflow.steps)
            for index, step in enumerate(workflow.steps):
                step.order = index + 1
                step.depends_on = [workflow.steps[index - 1].id] if index else []
        available = set(
            workflow.dataset.inspection.input_types if workflow.dataset else ["dataset_folder"]
        )
        features = workflow.dataset.inspection.features if workflow.dataset else {}
        excluded = set(workflow.excluded_capabilities) | set(workflow.input_capabilities)
        for step in workflow.steps:
            previous_options = {option.id: option for option in step.method_options}
            definitions = {
                definition.method_id: definition
                for definition in self.registry.selectable_methods_for(step.capability)
                if definition.method_id in previous_options
                or definition.execution_resolution.get("source_method_id") in previous_options
                or self._scope_conflicts(definition, excluded)
            }
            if workflow.locked_at is not None or workflow.status == "confirmed":
                # A catalog release must not silently change the approved inputs,
                # algorithm parameters or nested steps of an existing workflow.
                definitions = {
                    option.id: CapabilityMethod.model_validate({
                        **option.model_dump(), "method_id": option.id,
                        "capability": step.capability,
                    }) for option in previous_options.values()
                }
            step.method_options = []
            for definition in definitions.values():
                checked = self._option(definition, available, features, workflow.dataset is not None,
                                       check_runtime=check_runtime)
                option = previous_options.get(definition.method_id)
                if option:
                    if not check_runtime:
                        checked.blocked_reasons = [reason for reason in option.blocked_reasons if not reason.startswith(
                            ("上游没有产生所需输入：", "数据集缺少条件：", "此方法包含已排除的生成操作"))]
                        checked.compatible = not checked.blocked_reasons
                    checked.recommended = option.recommended
                    checked.recommendation_reason = option.recommendation_reason
                self._restrict_method_scope(checked, excluded)
                if checked.scope_warnings:
                    checked.recommended = False
                step.method_options.append(checked)
            selected = next(
                (option for option in step.method_options if option.id == step.selected_method_id),
                None,
            )
            if selected and not selected.compatible:
                step.selected_method_id = None
                step.selected_parameters = {}
                selected = None
            if selected:
                available.update(selected.output_types)
            else:
                for option in step.method_options:
                    if option.compatible and not option.scope_warnings:
                        available.update(option.output_types)

    @staticmethod
    def _condition_matches(condition: dict[str, list[Any]], values: dict[str, Any]) -> bool:
        return all(values.get(parameter_id) in allowed for parameter_id, allowed in condition.items())

    @classmethod
    def _slot_required(cls, slot: Any, parameters: dict[str, Any]) -> bool:
        return bool(slot.required or (
            slot.required_when and cls._condition_matches(slot.required_when, parameters)
        ))

    @classmethod
    def _output_generated(cls, slot: Any, parameters: dict[str, Any]) -> bool:
        return not slot.generated_when or cls._condition_matches(slot.generated_when, parameters)

    def _dataset_binding(self, workflow: Workflow, slot: Any) -> InputBinding | None:
        dataset = workflow.dataset
        if dataset is None or "dataset" not in slot.source_options:
            return None
        # An inspection can prove that a file type exists somewhere in a dataset,
        # but it cannot identify the intended file. Only folder slots may bind the
        # dataset root automatically; file inputs must be chosen explicitly (or
        # connected to an upstream output).
        if slot.binding != "folder" and slot.type != "dataset_folder":
            return None
        available_types = set(dataset.inspection.input_types)
        if dataset.inspection.has_t1w:
            available_types.add("t1w_image")
        if slot.type not in available_types and slot.type != "dataset_folder":
            return None
        return InputBinding(
            slot_id=slot.id,
            artifact_type=slot.type,
            source="dataset",
            label=dataset.display_name,
            root_id=dataset.root_id,
            relative_path=dataset.relative_path,
            absolute_path=dataset.absolute_path,
            binding_mode="dataset",
            dataset_id=dataset.dataset_id,
            status="validated",
            messages=["由已登记数据集的只读扫描结果匹配。"],
        )

    def _resolve_workflow_inputs(self, workflow: Workflow) -> None:
        upstream_outputs: list[tuple[str, Any]] = []
        for step in workflow.steps:
            method = next(
                (item for item in step.method_options if item.id == step.selected_method_id),
                None,
            )
            if method is None:
                step.input_bindings = {}
                step.missing_required_inputs = []
                continue

            previous_bindings = step.input_bindings
            resolved: dict[str, InputBinding] = {}
            for slot in method.input_slots:
                existing = previous_bindings.get(slot.id)
                if (
                    existing
                    and existing.artifact_type == slot.type
                    and existing.source == "existing_path"
                    and (existing.history is not None or self._binding_paths_exist(existing))
                ):
                    # Honor an existing-file binding when a declared source
                    # selector controls whether software generates that input.
                    for key, allowed in slot.required_when.items():
                        spec = next((item for item in method.parameters if item.id == key), None)
                        if (key.endswith("_source") and "existing" in allowed and spec
                                and any(option.value == "existing" for option in spec.options)):
                            step.selected_parameters[key] = "existing"
                    resolved[slot.id] = existing
                    continue

                if slot.type in step.manual_input_types:
                    # A removed producer must not be silently replaced by a
                    # different upstream output or an inferred dataset binding.
                    continue

                upstream = next(
                    (
                        (upstream_step_id, output)
                        for upstream_step_id, output in reversed(upstream_outputs)
                        if output.type == slot.type and "upstream_output" in slot.source_options
                    ),
                    None,
                )
                if upstream:
                    upstream_step_id, output = upstream
                    resolved[slot.id] = InputBinding(
                        slot_id=slot.id,
                        artifact_type=slot.type,
                        source="upstream_output",
                        label=output.label,
                        upstream_step_id=upstream_step_id,
                        output_slot_id=output.id,
                        status="planned",
                        messages=["将在上游步骤完成后自动绑定。"],
                    )
                    continue

                dataset_binding = self._dataset_binding(workflow, slot)
                if dataset_binding:
                    resolved[slot.id] = dataset_binding

            step.input_bindings = resolved
            step.missing_required_inputs = [
                slot.id
                for slot in method.input_slots
                if (self._slot_required(slot, step.selected_parameters)
                    or (slot.type in step.manual_input_types and self._condition_matches(
                        {key: allowed for key, allowed in slot.required_when.items() if not key.endswith("_source")},
                        step.selected_parameters)))
                and slot.id not in resolved
            ]
            upstream_outputs.extend(
                (step.id, output)
                for output in method.output_slots
                if self._output_generated(output, step.selected_parameters)
            )

    def _refresh(self, workflow: Workflow) -> None:
        if workflow.status == "confirmed":
            return
        self._resolve_workflow_inputs(workflow)
        self._refresh_execution_summary(workflow)
        workflow.sample_scope = partial_sample_scope(workflow)
        unresolved = [step for step in workflow.steps if step.selected_method_id is None]
        if workflow.locked_at is None:
            workflow.status = "awaiting_method_choice" if unresolved else "chain_ready"
            workflow.can_lock = not unresolved
            workflow.can_unlock = False
            workflow.can_review_parameters = False
            workflow.can_dry_run = False
            workflow.can_confirm = False
            for step in workflow.steps:
                step.status = "needs_method" if step.selected_method_id is None else "method_selected"
                step.command_preview = None
            return

        parameters_valid = True
        missing_inputs = any(step.missing_required_inputs for step in workflow.steps) or (
            workflow.sample_scope is not None and not workflow.sample_scope.eligible_sample_ids)
        for step in workflow.steps:
            method = self._selected_method(step)
            try:
                self._validate_method_parameters(method, step.selected_parameters)
            except ValueError:
                parameters_valid = False
            step.command_preview = self._command_preview(
                method,
                step.selected_parameters,
                workflow.dataset,
                step.input_bindings,
            )
            step.status = (
                "parameters_reviewed" if workflow.parameters_reviewed_at else "parameters_ready"
            )

        workflow.can_lock = False
        workflow.can_unlock = True
        workflow.can_review_parameters = (
            parameters_valid
            and not missing_inputs
            and workflow.parameters_reviewed_at is None
        )
        workflow.can_dry_run = (
            parameters_valid
            and not missing_inputs
            and workflow.parameters_reviewed_at is not None
        )
        workflow.can_confirm = False
        if missing_inputs:
            workflow.status = "awaiting_input_binding"
        elif not parameters_valid or workflow.parameters_reviewed_at is None:
            workflow.status = "awaiting_parameter_review"
        elif workflow.dry_run_report is None or not workflow.dry_run_report.valid:
            workflow.status = "awaiting_dry_run"
        else:
            workflow.status = "ready"
            workflow.can_dry_run = True
            workflow.can_confirm = True

    def _refresh_execution_summary(self, workflow: Workflow) -> None:
        selected_by_step = [
            (
                step,
                next(
                    (
                        option
                        for option in step.method_options
                        if option.id == step.selected_method_id
                    ),
                    None,
                ),
            )
            for step in workflow.steps
        ]
        selected = [method for _step, method in selected_by_step]
        methods = (
            [method for method in selected if method is not None]
            if all(method is not None for method in selected)
            else [option for step in workflow.steps for option in step.method_options]
        )
        modes = {method.execution_mode for method in methods}
        workflow.execution_mode = (
            "mixed" if len(modes) > 1 else next(iter(modes), "planning")
        )
        managed_dataset_warnings = (
            set(workflow.dataset.inspection.warnings) if workflow.dataset else set()
        )
        workflow.warnings = [
            warning
            for warning in workflow.warnings
            if warning not in managed_dataset_warnings
            and not self._is_contextual_dataset_warning(warning)
            and not self._is_planning_warning(warning)
        ]
        workflow.warnings.extend(
            self._contextual_dataset_warnings(workflow, selected_by_step)
        )

        planning_steps = [
            (step, method)
            for step, method in selected_by_step
            if method is not None and method.execution_mode == "planning"
        ]
        if len(planning_steps) == 1:
            step, method = planning_steps[0]
            workflow.warnings.append(
                f"步骤“{step.title}”已选择“{method.label}”，该方法仅支持规划："
                "可以配置参数并保存方案，但当前没有可执行 runner。"
            )
        elif planning_steps:
            labels = "；".join(
                f"步骤“{step.title}”的“{method.label}”"
                for step, method in planning_steps
            )
            workflow.warnings.append(
                f"已选择的以下方法仅支持规划，不能由 runner 实际执行：{labels}。"
            )

    @classmethod
    def _is_planning_warning(cls, warning: str) -> bool:
        return warning == cls.PLANNING_WARNING or (
            warning.startswith("已选择的以下方法仅支持规划")
            or (warning.startswith("步骤“") and "该方法仅支持规划" in warning)
        )

    @staticmethod
    def _is_contextual_dataset_warning(warning: str) -> bool:
        return warning.startswith(
            (
                "当前已选方法需要 DWI 输入",
                "当前已选方法需要梯度表",
                "当前已选 DWI 预处理方法可能使用反向相位编码数据",
            )
        )

    @classmethod
    def _contextual_dataset_warnings(
        cls,
        workflow: Workflow,
        selected_by_step: list[tuple[WorkflowStep, MethodOption | None]],
    ) -> list[str]:
        if workflow.dataset is None:
            return []

        inspection = workflow.dataset.inspection
        dwi_source_warnings = {
            DatasetService.DWI_NOT_FOUND_WARNING,
            DatasetService.DWI_GRADIENT_WARNING,
            DatasetService.REVERSE_PHASE_WARNING,
        }
        warnings = [
            warning
            for warning in inspection.warnings
            if warning not in dwi_source_warnings
        ]
        chosen = [
            (step, method)
            for step, method in selected_by_step
            if method is not None
        ]
        dwi_inputs = [
            (step, method)
            for step, method in chosen
            if cls._method_needs_dwi_input(method)
        ]
        gradient_inputs = [
            (step, method)
            for step, method in chosen
            if cls._method_needs_gradient_table(method)
        ]
        reverse_phase_methods = [
            (step, method)
            for step, method in chosen
            if cls._method_may_use_reverse_phase(
                step.capability,
                method,
                step.selected_parameters,
            )
        ]

        if DatasetService.DWI_NOT_FOUND_WARNING in inspection.warnings and dwi_inputs:
            warnings.append(
                "当前已选方法需要 DWI 输入（"
                + cls._step_method_labels(dwi_inputs)
                + "），但数据集扫描没有识别到 DWI NIfTI 或 DICOM；"
                "请检查所选输入路径和文件命名。"
            )
        if DatasetService.DWI_GRADIENT_WARNING in inspection.warnings and gradient_inputs:
            warnings.append(
                "当前已选方法需要梯度表（"
                + cls._step_method_labels(gradient_inputs)
                + "），但数据集扫描发现 bval/bvec 不完整；请在 dry-run 前补齐或绑定正确文件。"
            )
        if DatasetService.REVERSE_PHASE_WARNING in inspection.warnings and reverse_phase_methods:
            warnings.append(
                "当前已选 DWI 预处理方法可能使用反向相位编码数据（"
                + cls._step_method_labels(reverse_phase_methods)
                + "），但扫描仅按文件名未识别到 AP/PA 配对。若使用 topup，请在参数确认和 "
                "dry-run 前核对实际文件及元数据；若选择不使用 topup，此提示不构成阻塞。"
            )
        return warnings

    @staticmethod
    def _step_method_labels(
        selected: list[tuple[WorkflowStep, MethodOption]],
    ) -> str:
        return "、".join(f"{step.title} / {method.label}" for step, method in selected)

    @staticmethod
    def _method_needs_dwi_input(method: MethodOption) -> bool:
        input_types = set(method.input_types)
        input_types.update(slot.type for slot in method.input_slots)
        return bool(input_types & {"raw_dwi", "bids_dwi", "preprocessed_dwi"})

    @staticmethod
    def _method_needs_gradient_table(method: MethodOption) -> bool:
        input_types = set(method.input_types)
        input_types.update(slot.type for slot in method.input_slots)
        slot_ids = {slot.id.lower() for slot in method.input_slots}
        return "gradient_table" in input_types or bool(
            slot_ids & {"bval", "bvals", "bvec", "bvecs"}
        )

    @staticmethod
    def _method_may_use_reverse_phase(
        capability: str,
        method: MethodOption,
        parameters: dict[str, Any],
    ) -> bool:
        if capability != "dwi.preprocess":
            return False
        if str(parameters.get("susceptibility_correction", "auto")).lower() == "none":
            return False
        searchable = " ".join(
            [
                method.id,
                method.runner_id,
                method.label,
                method.description,
                *(
                    text
                    for parameter in method.parameters
                    for text in (
                        parameter.id,
                        parameter.argument,
                        parameter.label,
                        parameter.description,
                    )
                ),
            ]
        ).lower()
        return any(
            term in searchable
            for term in ("topup", "susceptibility", "phase encoding", "畸变", "相位编码")
        )

    @staticmethod
    def _parameter_visible(spec: ParameterSpec, values: dict[str, Any]) -> bool:
        return all(values.get(parameter_id) in allowed for parameter_id, allowed in spec.visible_when.items())

    @staticmethod
    def _validate_parameter(spec: ParameterSpec, value: Any) -> None:
        valid_type = {
            "boolean": type(value) is bool,
            "integer": type(value) is int,
            "number": type(value) in {int, float},
            "string": isinstance(value, str),
        }[spec.type]
        if not valid_type:
            raise ValueError(f"参数 {spec.label} 的类型不正确")
        if spec.options and not any(option.value == value for option in spec.options):
            raise ValueError(f"参数 {spec.label} 不在允许的选项中")
        if spec.type in {"integer", "number"}:
            numeric = float(value)
            if spec.minimum is not None and numeric < spec.minimum:
                raise ValueError(f"参数 {spec.label} 不能小于 {spec.minimum:g}{spec.unit}")
            if spec.maximum is not None and numeric > spec.maximum:
                raise ValueError(f"参数 {spec.label} 不能大于 {spec.maximum:g}{spec.unit}")

    def _validate_method_parameters(
        self,
        method: MethodOption,
        values: dict[str, Any],
    ) -> None:
        specs = {spec.id: spec for spec in method.parameters}
        unknown = sorted(set(values) - set(specs))
        if unknown:
            raise ValueError(f"包含未声明的参数：{', '.join(unknown)}")
        for spec in specs.values():
            visible = self._parameter_visible(spec, values)
            if visible and spec.required and spec.id not in values:
                raise ValueError(f"缺少必填参数：{spec.label}")
            if visible and spec.id in values:
                self._validate_parameter(spec, values[spec.id])

    def _validate_all_parameters(self, workflow: Workflow) -> None:
        for step in workflow.steps:
            self._validate_method_parameters(self._selected_method(step), step.selected_parameters)

    @staticmethod
    def _binding_paths_exist(binding: InputBinding) -> bool:
        if binding.binding_mode == "per_sample":
            return bool(binding.sample_matches) and all(
                match.status == "matched"
                and bool(match.absolute_path)
                and Path(match.absolute_path).exists()
                for match in binding.sample_matches
            )
        return bool(binding.absolute_path and Path(binding.absolute_path).exists())

    @staticmethod
    def _command_preview(
        method: MethodOption,
        parameters: dict[str, Any],
        dataset: DatasetRecord | None,
        input_bindings: dict[str, InputBinding] | None = None,
    ) -> str:
        bindings = input_bindings or {}
        if method.execution_recipe is not None:
            stages = " -> ".join(
                f"{step.title}[{step.method_id}]"
                for step in method.execution_recipe.steps
            )
            parts = ["RUNNER_PIPELINE", method.execution_recipe.recipe_id, "::", stages]
            for spec in method.parameters:
                if spec.id not in parameters or not WorkflowService._parameter_visible(spec, parameters):
                    continue
                value = parameters[spec.id]
                rendered = str(value).lower() if isinstance(value, bool) else str(value)
                parts.extend((f"--{spec.argument}", rendered))
            return " ".join(parts)
        if method.execution_mode == "planning":
            parts = ["PLAN", method.skill_id, "--method", method.id]
            for slot in method.input_slots:
                binding = bindings.get(slot.id)
                if binding is None:
                    continue
                source = WorkflowService._binding_command_source(binding, dataset)
                if source:
                    parts.extend((f"--input-{slot.id}", subprocess.list2cmdline([source])))
            for spec in method.parameters:
                if spec.id not in parameters or not WorkflowService._parameter_visible(spec, parameters):
                    continue
                value = parameters[spec.id]
                if value == "" and not spec.required:
                    continue
                rendered = str(value).lower() if isinstance(value, bool) else str(value)
                parts.extend((f"--{spec.argument}", rendered))
            return " ".join(parts)

        parts = [method.runner_id]
        if method.input_slots:
            for slot in method.input_slots:
                binding = bindings.get(slot.id)
                if binding is None:
                    continue
                source = WorkflowService._binding_command_source(binding, dataset)
                if source:
                    parts.extend((f"--input-{slot.id}", subprocess.list2cmdline([source])))
        else:
            input_path = (
                subprocess.list2cmdline([dataset.absolute_path])
                if dataset
                else "<DATASET_FOLDER>"
            )
            parts.extend(("--input", input_path))
        parts.extend(("--output", "<OUTPUT_FOLDER>"))
        for spec in method.parameters:
            if spec.id not in parameters or not WorkflowService._parameter_visible(spec, parameters):
                continue
            value = parameters[spec.id]
            if value == "" and not spec.required:
                continue
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            parts.extend((f"--{spec.argument}", rendered))
        return " ".join(parts)

    @staticmethod
    def _binding_command_source(
        binding: InputBinding,
        dataset: DatasetRecord | None,
    ) -> str | None:
        if binding.source == "upstream_output":
            return f"<{binding.upstream_step_id}.{binding.output_slot_id}>"
        if binding.history and binding.binding_mode == "per_sample":
            return f"<历史运行 {binding.history.run_id}：按样本标识匹配>"
        if binding.binding_mode == "per_sample" and binding.path_template:
            base = dataset.absolute_path if dataset else "<DATASET_FOLDER>"
            return str(Path(base) / binding.path_template)
        return binding.absolute_path

    @staticmethod
    def _default_parameters(method: MethodOption) -> dict[str, Any]:
        return {spec.id: spec.default for spec in method.parameters if spec.default is not None}

    @staticmethod
    def _selected_method(step: WorkflowStep) -> MethodOption:
        method = next(
            (item for item in step.method_options if item.id == step.selected_method_id),
            None,
        )
        if method is None:
            raise ValueError(f"步骤 {step.title} 尚未选择方法")
        return method

    @staticmethod
    def _step(workflow: Workflow, step_id: str) -> WorkflowStep:
        step = next((item for item in workflow.steps if item.id == step_id), None)
        if step is None:
            raise ValueError(f"流程中不存在步骤 {step_id}")
        return step

    def _require(self, workflow_id: str) -> Workflow:
        workflow = self.store.get_workflow(workflow_id)
        if workflow is None:
            raise KeyError(workflow_id)
        if workflow.locked_at is None and workflow.status != "confirmed":
            # Compatibility and display order are derived from current declarations.
            # Reading old drafts does not rewrite their persisted snapshots.
            self._revalidate_chain(workflow, check_runtime=False)
            self._refresh(workflow)
        return workflow

    @staticmethod
    def _check_revision(workflow: Workflow, expected_revision: int) -> None:
        if workflow.revision != expected_revision:
            raise RevisionConflict(workflow)

    @staticmethod
    def _ensure_editable_chain(workflow: Workflow) -> None:
        if workflow.locked_at is not None:
            raise ValueError("流程链已经锁定，请先解锁再修改方法")
        if workflow.status == "confirmed":
            raise ValueError("流程已经确认")

    def _load_manifest(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"无法载入 DWI workflow manifest：{exc}") from exc
        if payload.get("schema_version") != 2 or not isinstance(payload.get("steps"), list):
            raise RuntimeError("DWI workflow manifest 格式不正确")
        return payload

    def _save(
        self,
        workflow: Workflow,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.store.save_workflow(workflow, event_type=event_type, event_payload=payload)

    @staticmethod
    def _clear_review(workflow: Workflow) -> None:
        workflow.parameters_reviewed_at = None
        workflow.dry_run_report = None
        workflow.confirmed_at = None

    @staticmethod
    def _advance(workflow: Workflow) -> None:
        workflow.revision += 1
        workflow.updated_at = WorkflowService._now()

    @staticmethod
    def _definition_default(definitions: list[CapabilityMethod], method_id: str) -> bool:
        definition = next((item for item in definitions if item.method_id == method_id), None)
        return bool(definition and definition.default_recommended)

    @staticmethod
    def _definition_reason(definitions: list[CapabilityMethod], method_id: str) -> str:
        definition = next((item for item in definitions if item.method_id == method_id), None)
        return definition.default_reason if definition else ""

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
