from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .conversation_models import ConversationMemoryStatus
from .workflow_models import Workflow


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    history: list[Message] = Field(default_factory=list)
    conversation_id: str | None = None
    conversation_summary: str = Field(default="", exclude=True, repr=False)
    selected_skills: list[str] = Field(default_factory=list)
    dataset_id: str | None = None
    interaction_mode: Literal["chat", "task"] = "chat"
    language: str = "zh-CN"


class CapabilityRecommendationItem(BaseModel):
    capability_id: str
    label: str
    description: str = ""
    execution_level: Literal["advisory", "planning", "structured"]
    skill_ids: list[str] = Field(default_factory=list)
    tree_path: list[str] = Field(default_factory=list)


class CapabilityRecommendation(BaseModel):
    title: str
    summary: str
    plan_kind: Literal["atomic", "composite"]
    fully_executable: bool = False
    items: list[CapabilityRecommendationItem] = Field(default_factory=list)
    notice: str = (
        "推荐项来自现有 SKILL.md；planning Manifest 可进入流程并选择参数，"
        "但只有 runner Manifest 才表示已定义执行方法。"
    )


class CapabilityRoutingLevel(BaseModel):
    level: int
    parent_ids: list[str] = Field(default_factory=list)
    candidate_count: int = 0
    payload_chars: int = 0
    selected_node_ids: list[str] = Field(default_factory=list)
    source: str = "model"


class CapabilityRoutingTrace(BaseModel):
    strategy: Literal["hierarchical", "heuristic", "semantic"] = "hierarchical"
    levels: list[CapabilityRoutingLevel] = Field(default_factory=list)
    candidates_seen: int = 0
    payload_chars: int = 0
    full_tree_payload_chars: int = 0
    payload_ratio: float = 0.0
    selected_paths: list[list[str]] = Field(default_factory=list)
    intent_source: str = ""
    normalized_task: str = ""
    semantic_hints: list[str] = Field(default_factory=list)
    reused_input_capabilities: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class ChatResponse(BaseModel):
    type: Literal["done", "recommendation", "workflow"] = "done"
    content: str
    provider_used: str
    model_used: str
    mode: Literal["demo", "model"]
    selected_skills: list[str]
    conversation_id: str | None = None
    memory: ConversationMemoryStatus | None = None
    auto_selected: bool = False
    interaction_mode: Literal["chat", "task"] = "chat"
    workflow_recommended: bool = False
    workflow_decision_source: str = "not_applicable"
    clarification_required: bool = False
    recommended_capabilities: list[str] = Field(default_factory=list)
    capability_routing: CapabilityRoutingTrace | None = None
    capability_recommendation: CapabilityRecommendation | None = None
    workflow: Workflow | None = None


class SkillSummary(BaseModel):
    name: str
    display_name: str
    description: str
    layer: str = "workflow"
    skill_type: str = "data-processing"
    runtime: str = "Not configured"
    status: str = "imported"
    summary_en: str = ""
    summary_zh: str = ""
    dependencies: list[str] = Field(default_factory=list)
    complementary_skills: list[str] = Field(default_factory=list)
    source: str = "LocalFlow"
    script_count: int = 0
    has_handler: bool = False
    executable: bool = False
    structure_mode: Literal["advisory", "planning", "runner"] = "advisory"
