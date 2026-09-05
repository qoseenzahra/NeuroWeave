from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware

from .chat_service import ChatService
from .capability_tree import CapabilityTree
from .capability_registry import CapabilityRegistry
from .conversation_models import (
    ConversationPage,
    ConversationRecord,
    ConversationSnapshot,
    ConversationUpdateRequest,
)
from .conversation_service import ConversationService
from .dataset_models import (
    DatasetPathPreview,
    DatasetRecord,
    DatasetRegisterRequest,
    DirectoryListing,
)
from .dataset_service import DatasetService
from .execution import RunnerRegistry, RunConflict, RunService
from .local_store import LocalStore
from .models import ChatRequest, ChatResponse
from .neuroclaw_compat.validate_dag import find_cycles, find_missing_deps, load_skill_graph
from .skill_loader import SkillLoader
from .run_models import RunCreateRequest, WorkflowRun
from .workflow_models import (
    InputBindingRequest,
    InputPreviewRequest,
    MethodSelectionRequest,
    ParameterUpdateRequest,
    Workflow,
    WorkflowDraftRequest,
    WorkflowMutationRequest,
)
from .workflow_service import RevisionConflict, WorkflowService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"
SKILL_SUMMARIES_FILE = BACKEND_ROOT / "resources" / "neuroclaw_skill_summaries.json"
configured_database = Path(os.getenv("LOCALFLOW_DATABASE_PATH", "data/localflow.db"))
DATABASE_PATH = (
    configured_database
    if configured_database.is_absolute()
    else (BACKEND_ROOT / configured_database).resolve()
)

skill_loader = SkillLoader(SKILLS_DIR, SKILL_SUMMARIES_FILE)
chat_service = ChatService()
capability_registry = CapabilityRegistry(SKILLS_DIR)
capability_tree = CapabilityTree(SKILLS_DIR / "capability.tree.json")
local_store = LocalStore(DATABASE_PATH)
dataset_service = DatasetService(PROJECT_ROOT, local_store)
conversation_service = ConversationService(local_store, chat_service)
runner_registry = RunnerRegistry()
workflow_service = WorkflowService(
    SKILLS_DIR / "dwi-skill" / "workflow.manifest.json",
    chat_service,
    capability_registry,
    local_store,
    dataset_service,
    capability_tree,
    skill_loader,
    runner_registry.available_ids(),
    runner_registry,
)
configured_output_root = Path(
    os.getenv("LOCALFLOW_OUTPUT_ROOT", str(PROJECT_ROOT / "outputs"))
)
OUTPUT_ROOT = (
    configured_output_root
    if configured_output_root.is_absolute()
    else (PROJECT_ROOT / configured_output_root).resolve()
)
run_service = RunService(
    local_store,
    capability_registry,
    runner_registry,
    OUTPUT_ROOT,
)


def _skill_with_execution_status(skill: Any) -> dict[str, Any]:
    methods = [
        method for method in capability_registry.all_methods()
        if method.skill_id == skill.name
    ]
    runner_ids = sorted(
        {method.runner_id for method in methods if method.execution_mode == "runner"}
    )
    ready: list[str] = []
    reasons: list[str] = []
    for runner_id in runner_ids:
        runner = runner_registry.get(runner_id)
        if runner is None:
            reasons.append(f"{runner_id}：尚未接入可信 Runner")
            continue
        status = runner.runtime_status()
        if status.get("available"):
            ready.append(runner_id)
        else:
            reasons.append(f"{runner_id}：{status.get('reason') or '环境不可用'}")
    payload = skill.public_dict()
    payload.update(
        executable=bool(ready),
        runner_count=len(runner_ids),
        ready_runner_count=len(ready),
        planning_method_count=sum(method.execution_mode == "planning" for method in methods),
        execution_state=(
            "ready" if ready else "needs_environment" if runner_ids else "planning"
        ),
        runtime_reasons=reasons[:6],
    )
    return payload


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    run_service.shutdown()

app = FastAPI(
    title="LocalFlow API",
    version="0.1.0",
    description="Local dialogue and skill-discovery API.",
    lifespan=lifespan,
)

origins = [
    origin.strip()
    for origin in os.getenv(
        "LOCALFLOW_CORS_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5173,http://localhost:5173",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "LocalFlow API", "docs": "/docs"}


@app.get("/api/health")
async def health() -> dict[str, Any]:
    skill_stats = skill_loader.stats()
    skill_stats["execution_enabled"] = run_service.enabled
    return {
        "status": "ok",
        "mode": chat_service.mode,
        "model": chat_service.model or "conversation-demo",
        "prompt_version": chat_service.prompt_version,
        "thinking": chat_service.thinking if chat_service.mode == "model" else "disabled",
        "skill_catalog": skill_stats,
        "capability_catalog": capability_registry.stats(),
        "capability_tree": capability_tree.stats(),
        "conversation_memory": {
            "compact_trigger_tokens": conversation_service.compact_trigger_tokens,
            "keep_recent_messages": conversation_service.keep_recent_messages,
            "storage": "sqlite",
        },
        "persistence": "sqlite",
        "dataset_roots": len(dataset_service.roots()),
        "execution": {
            "enabled": run_service.enabled,
            "runner_count": len(runner_registry.ids()),
            "ready_runner_count": len(runner_registry.available_ids()),
            "runners": runner_registry.public_catalog(),
            "output_root": str(OUTPUT_ROOT),
        },
    }


@app.get("/api/datasets/roots")
async def dataset_roots() -> dict[str, Any]:
    return {"roots": [root.model_dump() for root in dataset_service.roots()]}


@app.get("/api/capabilities/tree")
async def capabilities_tree() -> dict[str, Any]:
    return {
        "tree": capability_tree.compact(),
        "stats": capability_tree.stats(),
        "registered_capabilities": capability_registry.capabilities(),
    }


@app.get("/api/artifacts/types")
async def artifact_types() -> dict[str, Any]:
    return {
        "artifact_types": [
            item.model_dump(mode="json") for item in capability_registry.artifact_types()
        ]
    }


@app.get("/api/datasets/directories", response_model=DirectoryListing)
async def dataset_directories(root_id: str, relative_path: str = "") -> DirectoryListing:
    try:
        return dataset_service.list_directories(root_id, relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/datasets")
async def list_datasets() -> dict[str, list[DatasetRecord]]:
    return {"datasets": dataset_service.list()}


@app.post("/api/datasets/register", response_model=DatasetRecord)
async def register_dataset(request: DatasetRegisterRequest) -> DatasetRecord:
    try:
        return dataset_service.register(
            request.root_id,
            request.relative_path,
            request.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/datasets/{dataset_id}", response_model=DatasetRecord)
async def get_dataset(dataset_id: str) -> DatasetRecord:
    try:
        return dataset_service.get(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc


@app.post("/api/datasets/{dataset_id}/inspect", response_model=DatasetRecord)
async def inspect_dataset(dataset_id: str) -> DatasetRecord:
    try:
        return dataset_service.inspect(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/skills")
async def list_skills(q: str = "", source: str = "") -> dict[str, Any]:
    skills = skill_loader.load_all()
    normalized_query = q.strip().lower()
    normalized_source = source.strip().lower()
    if normalized_query:
        skills = [
            skill
            for skill in skills
            if normalized_query
            in " ".join(
                (
                    skill.name,
                    skill.display_name,
                    skill.description,
                    skill.summary_en,
                    skill.summary_zh,
                    skill.skill_type,
                )
            ).lower()
        ]
    if normalized_source:
        skills = [skill for skill in skills if skill.source.lower() == normalized_source]
    skill_stats = skill_loader.stats()
    skill_stats["execution_enabled"] = run_service.enabled
    return {
        "skills": [_skill_with_execution_status(skill) for skill in skills],
        "stats": {
            **skill_stats,
            "capability_catalog": capability_registry.stats(),
        },
    }


@app.get("/api/skills/graph")
async def skill_graph() -> dict[str, Any]:
    graph, _metadata = load_skill_graph(SKILLS_DIR)
    return {
        "nodes": len(graph),
        "edges": sum(len(dependencies) for dependencies in graph.values()),
        "cycles": find_cycles(graph),
        "missing_dependencies": find_missing_deps(graph),
        "graph": graph,
    }


@app.get("/api/skills/{skill_name}")
async def get_skill(skill_name: str) -> dict[str, Any]:
    skill = skill_loader.find(skill_name)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    files = [
        str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
        for path in sorted(skill.path.rglob("*"))
        if path.is_file()
    ]
    return {
        **_skill_with_execution_status(skill),
        "instructions": skill.instructions,
        "files": files,
    }


@app.post("/api/conversations", response_model=ConversationRecord)
async def create_conversation() -> ConversationRecord:
    return conversation_service.create()


@app.get("/api/conversations", response_model=ConversationPage)
async def list_conversations(
    limit: int = Query(default=20, ge=1, le=50),
    q: str = Query(default="", max_length=1000),
    archived: bool = False,
    cursor: str = Query(default="", max_length=1024),
) -> ConversationPage:
    try:
        return conversation_service.list_page(
            limit,
            query=q,
            archived=archived,
            cursor=cursor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.delete("/api/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str) -> Response:
    try:
        conversation_service.delete(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@app.patch("/api/conversations/{conversation_id}", response_model=ConversationRecord)
async def update_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
) -> ConversationRecord:
    try:
        return conversation_service.update(
            conversation_id,
            title=request.title,
            archived=request.archived,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/conversations/{conversation_id}", response_model=ConversationSnapshot)
async def get_conversation(conversation_id: str) -> ConversationSnapshot:
    try:
        return conversation_service.snapshot(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@app.post("/api/conversations/{conversation_id}/compact", response_model=ConversationSnapshot)
async def compact_conversation(conversation_id: str) -> ConversationSnapshot:
    try:
        await conversation_service.compact_if_needed(conversation_id, force=True)
        return conversation_service.snapshot(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        request, conversation_id = conversation_service.begin_turn(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc

    async def finalize(response: ChatResponse) -> ChatResponse:
        memory = await conversation_service.finish_turn(conversation_id, response)
        return response.model_copy(
            update={
                "conversation_id": conversation_id,
                "memory": memory,
            }
        )

    requested_names = list(dict.fromkeys(request.selected_skills))
    selected = [skill for name in requested_names if (skill := skill_loader.find(name))]
    auto_selected = False
    if not requested_names:
        selected = skill_loader.infer(request.message)
        auto_selected = bool(selected)
    try:
        if request.interaction_mode == "task":
            decision = await workflow_service.assess_task(request)
            if decision.get("clarification_required"):
                return await finalize(ChatResponse(
                    type="done",
                    content=(
                        str(decision.get("clarification_question") or "").strip()
                        or "请再说明希望完成的具体数据处理目标。"
                    ),
                    provider_used=chat_service.provider_name,
                    model_used=chat_service.model or "conversation-demo",
                    mode=chat_service.mode,
                    selected_skills=[skill.name for skill in selected],
                    auto_selected=auto_selected,
                    interaction_mode="task",
                    workflow_recommended=False,
                    workflow_decision_source=decision["decision_source"],
                    clarification_required=True,
                    recommended_capabilities=[],
                    capability_routing=decision.get("routing_trace"),
                ))
            if decision["recommend_workflow"]:
                workflow, content = await workflow_service.draft(request, decision)
                related_skill_ids = {
                    skill_id
                    for step in workflow.steps
                    if (node := capability_tree.leaf(step.capability)) is not None
                    for skill_id in node.skill_ids
                }
                selected = [
                    skill
                    for skill_id in sorted(related_skill_ids)
                    if (skill := skill_loader.find(skill_id)) is not None
                ]
                auto_selected = bool(selected) and {
                    skill.name for skill in selected
                } != set(requested_names)
                return await finalize(ChatResponse(
                    type="workflow",
                    content=content,
                    provider_used=chat_service.provider_name,
                    model_used=chat_service.model or "workflow-demo",
                    mode=chat_service.mode,
                    selected_skills=[skill.name for skill in selected],
                    auto_selected=auto_selected,
                    interaction_mode="task",
                    workflow_recommended=True,
                    workflow_decision_source=decision["decision_source"],
                    recommended_capabilities=decision["capability_ids"],
                    capability_routing=decision.get("routing_trace"),
                    workflow=workflow,
                ))
            if decision.get("recommend_skills"):
                recommendation = workflow_service.build_capability_recommendation(
                    decision
                )
                related_skill_ids = {
                    skill_id
                    for item in recommendation.items
                    for skill_id in item.skill_ids
                }
                selected = [
                    skill
                    for skill_id in sorted(related_skill_ids)
                    if (skill := skill_loader.find(skill_id)) is not None
                ]
                auto_selected = bool(selected) and {
                    skill.name for skill in selected
                } != set(requested_names)
                candidate_context = workflow_service.recommendation_context(
                    decision["capability_ids"]
                )
                content = await chat_service.explain_capability_recommendation(
                    request,
                    candidate_context,
                    str(decision.get("reason") or ""),
                )
                return await finalize(ChatResponse(
                    type="recommendation",
                    content=content,
                    provider_used=chat_service.provider_name,
                    model_used=chat_service.model or "conversation-demo",
                    mode=chat_service.mode,
                    selected_skills=[skill.name for skill in selected],
                    auto_selected=auto_selected,
                    interaction_mode="task",
                    workflow_recommended=False,
                    workflow_decision_source=decision["decision_source"],
                    recommended_capabilities=decision["capability_ids"],
                    capability_routing=decision.get("routing_trace"),
                    capability_recommendation=recommendation,
                ))
            response = await chat_service.reply(
                request,
                selected,
                auto_selected=auto_selected,
            )
            return await finalize(
                ChatResponse.model_validate(
                    {
                        **response.model_dump(mode="python"),
                        "workflow_recommended": False,
                        "workflow_decision_source": decision["decision_source"],
                        "capability_routing": decision.get("routing_trace"),
                    }
                )
            )
        return await finalize(
            await chat_service.reply(request, selected, auto_selected=auto_selected)
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"模型服务请求失败（HTTP {exc.response.status_code}）",
        ) from exc
    except (httpx.RequestError, RuntimeError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"模型服务未返回有效回复：{exc}") from exc


@app.post("/api/workflows/draft", response_model=Workflow)
async def draft_workflow(request: WorkflowDraftRequest) -> Workflow:
    try:
        workflow, _content = await workflow_service.draft(
            ChatRequest(**request.model_dump())
        )
        return workflow
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"模型服务请求失败（HTTP {exc.response.status_code}）",
        ) from exc
    except (httpx.RequestError, RuntimeError, KeyError, IndexError, TypeError) as exc:
        raise HTTPException(status_code=502, detail=f"无法生成流程：{exc}") from exc


@app.get("/api/workflows/{workflow_id}", response_model=Workflow)
async def get_workflow(workflow_id: str) -> Workflow:
    try:
        return workflow_service.get(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc


@app.get("/api/workflows")
async def list_workflows(limit: int = 50) -> dict[str, list[Workflow]]:
    return {"workflows": workflow_service.list(limit)}


@app.get("/api/workflows/{workflow_id}/events")
async def workflow_events(workflow_id: str) -> dict[str, Any]:
    try:
        return {"events": workflow_service.events(workflow_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc


@app.patch("/api/workflows/{workflow_id}/steps/{step_id}/method", response_model=Workflow)
async def select_workflow_method(
    workflow_id: str,
    step_id: str,
    request: MethodSelectionRequest,
) -> Workflow:
    try:
        return workflow_service.select_method(
            workflow_id,
            step_id,
            request.method_id,
            request.expected_revision,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/lock", response_model=Workflow)
async def lock_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.lock_chain(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/unlock", response_model=Workflow)
async def unlock_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.unlock_chain(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/replan", response_model=Workflow)
async def replan_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        workflow, _content = await workflow_service.replan(
            workflow_id,
            request.expected_revision,
        )
        return workflow
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/complete-dependencies", response_model=Workflow)
async def complete_workflow_dependencies(
    workflow_id: str,
    request: WorkflowMutationRequest,
) -> Workflow:
    try:
        return await workflow_service.complete_dependencies(
            workflow_id,
            request.expected_revision,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch(
    "/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}",
    response_model=Workflow,
)
async def bind_workflow_input(
    workflow_id: str,
    step_id: str,
    slot_id: str,
    request: InputBindingRequest,
) -> Workflow:
    try:
        return workflow_service.bind_input(
            workflow_id,
            step_id,
            slot_id,
            request.root_id,
            request.relative_path,
            request.expected_revision,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/preview",
    response_model=DatasetPathPreview,
)
async def preview_workflow_input(
    workflow_id: str,
    step_id: str,
    slot_id: str,
    request: InputPreviewRequest,
) -> DatasetPathPreview:
    try:
        return workflow_service.preview_input_mapping(
            workflow_id,
            step_id,
            slot_id,
            request.root_id,
            request.relative_path,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow or dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/workflows/{workflow_id}/steps/{step_id}/parameters", response_model=Workflow)
async def update_workflow_parameters(
    workflow_id: str,
    step_id: str,
    request: ParameterUpdateRequest,
) -> Workflow:
    try:
        return workflow_service.update_parameters(
            workflow_id,
            step_id,
            request.parameters,
            request.expected_revision,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/review-parameters", response_model=Workflow)
async def review_workflow_parameters(
    workflow_id: str,
    request: WorkflowMutationRequest,
) -> Workflow:
    try:
        return workflow_service.review_parameters(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/dry-run", response_model=Workflow)
async def dry_run_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.dry_run(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/confirm", response_model=Workflow)
async def confirm_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.confirm(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/runs", response_model=WorkflowRun)
async def start_workflow_run(
    workflow_id: str,
    request: RunCreateRequest,
) -> WorkflowRun:
    try:
        return run_service.create(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/runs")
async def list_runs(
    workflow_id: str | None = None,
    limit: int = 50,
) -> dict[str, list[WorkflowRun]]:
    return {"runs": run_service.list(workflow_id=workflow_id, limit=limit)}


@app.get("/api/runs/{run_id}", response_model=WorkflowRun)
async def get_run(run_id: str) -> WorkflowRun:
    try:
        return run_service.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, after_event_id: int = 0) -> dict[str, Any]:
    try:
        return {
            "events": run_service.events(run_id, after_event_id=after_event_id)
        }
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/api/runs/{run_id}/cancel", response_model=WorkflowRun)
async def cancel_run(run_id: str) -> WorkflowRun:
    try:
        return run_service.cancel(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except RunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _revision_http_error(exc: RevisionConflict) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "revision_conflict",
            "message": str(exc),
            "current": exc.current.model_dump(mode="json"),
        },
    )
