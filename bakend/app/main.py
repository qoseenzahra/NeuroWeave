from __future__ import annotations

import os
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Response, Request
from fastapi.responses import JSONResponse
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
from .operation_service import OperationService
from .maintenance import storage_status, inventory_outputs
from .historical_inputs import HistoricalSelectionRequest
from .models import ChatRequest, ChatResponse
from .neuroclaw_compat.validate_dag import find_cycles, find_missing_deps, load_skill_graph
from .skill_loader import SkillLoader
from .skill_catalog import SkillCatalog
from .run_models import ExecutionDraftRequest, RunCreateRequest, RunRetryRequest, WorkflowRun
from .workflow_models import (
    InputBindingRequest,
    InputPreviewRequest,
    MethodSelectionRequest,
    ParameterUpdateRequest,
    Workflow,
    WorkflowDraftRequest,
    WorkflowDatasetRequest,
    WorkflowMutationRequest,
)
from .workflow_service import RevisionConflict, WorkflowService
from .workspace_service import WorkspaceService
from .workspace_routes import workspace_router
from .workspace_tools import WorkspaceTools
from .workspace_models import WorkflowOutputRequest, DatasetWorkspaceRequest
from .dataset_files import DatasetFiles, protect_datasets


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
operation_service = OperationService(local_store)
dataset_service = DatasetService(PROJECT_ROOT, local_store)
conversation_service = ConversationService(local_store, chat_service)
workspace_service = WorkspaceService(local_store, PROJECT_ROOT / "workspaces")
dataset_files = DatasetFiles(dataset_service)
workspace_tools = WorkspaceTools(workspace_service, chat_service, dataset_files)
runner_registry = RunnerRegistry()
skill_catalog = SkillCatalog(skill_loader, capability_registry, runner_registry)
workspace_tools.skill_catalog = skill_catalog
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


def _protected_workspace_paths():
    # Reads remain available; mutations cannot invalidate queued/running jobs.
    protected = [DATABASE_PATH.parent, PROJECT_ROOT / "bakend", PROJECT_ROOT / "skills",
                 PROJECT_ROOT / "deploy", PROJECT_ROOT / ".conda"]
    for run in local_store.incomplete_runs():
        protected.append(Path(run.output_directory))
        workflow = Workflow.model_validate(run.plan_snapshot)
        if workflow.dataset:
            protected.append(Path(workflow.dataset.absolute_path))
        for step in workflow.steps:
            for binding in step.input_bindings.values():
                if binding.absolute_path:
                    protected.append(Path(binding.absolute_path))
                protected.extend(Path(match.absolute_path) for match in binding.sample_matches if match.absolute_path)
    return protected


workspace_service.protected_paths = _protected_workspace_paths
workspace_service.run_lock = run_service._lock
dataset_service.registration_lock = run_service._lock
dataset_service.registration_guard = workspace_service.guard_dataset_registration


def _workspace_request(request: ChatRequest) -> ChatRequest:
    workspace_id = request.workspace_id
    if request.conversation_id:
        conversation = local_store.get_conversation(request.conversation_id)
        if conversation:
            if workspace_id and conversation.workspace_id and workspace_id != conversation.workspace_id:
                raise HTTPException(409, "工作区与对话不一致，请先显式切换工作区")
            workspace_id = workspace_id or conversation.workspace_id
    try:
        workspace = workspace_service.get(workspace_id) if workspace_id else None
        dataset_root = dataset_files.reader(request.dataset_id).root() if request.dataset_id else None
        context = json.dumps({"output_directory_id": workspace_id, "output_root": workspace.root_path if workspace else None,
                              "output_manageable": workspace.manageable if workspace else False,
                              "dataset_id": request.dataset_id, "dataset_root": str(dataset_root) if dataset_root else None,
                              "dataset_access": "read_only", "default_output": workspace.root_path if workspace else None}, ensure_ascii=False)
    except (KeyError, ValueError, OSError) as exc:
        raise HTTPException(409, str(exc)) from exc
    # Never accept a root/context supplied by an HTTP client as authoritative.
    return request.model_copy(update={"workspace_id": workspace_id, "workspace_context": context if workspace or dataset_root else "",
                                      "workspace_root_path": workspace.root_path if workspace else None})


def _skill_with_execution_status(skill: Any, methods: list[Any] | None = None,
                                 runtime_statuses: dict[str, dict] | None = None) -> dict[str, Any]:
    methods = methods if methods is not None else [
        method for method in capability_registry.all_methods()
        if method.skill_id == skill.name
    ]
    runner_ids = sorted(
        {method.runner_id for method in methods if method.execution_mode == "runner"}
    )
    ready: list[str] = []
    reasons: list[str] = []
    statuses = runtime_statuses if runtime_statuses is not None else {}
    for runner_id in runner_ids:
        runner = runner_registry.get(runner_id)
        if runner is None:
            reasons.append(f"{runner_id}：尚未接入可信 Runner")
            continue
        if runner_id not in statuses:
            statuses[runner_id] = runner.runtime_status()
        status = statuses[runner_id]
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
    operation_service.shutdown()
    run_service.shutdown()

app = FastAPI(
    title="NeuroWeave API",
    version="0.1.0",
    description="Local dialogue and skill-discovery API.",
    lifespan=lifespan,
)
app.include_router(workspace_router(workspace_service, dataset_files))

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
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def release_maintenance(request: Request, call_next):
    if request.method in {"POST", "PATCH", "DELETE"} and request.url.path.startswith(("/api/fs/", "/api/workspaces", "/api/output-directories")):
        origin = request.headers.get("origin")
        if origin and origin not in origins and origin != str(request.base_url).rstrip("/"):
            return JSONResponse({"detail": "工作区写请求来自未授权的网页来源"}, status_code=403)
    # Deployment keeps reads/health available while rejecting new mutations.
    marker = DATABASE_PATH.parent / "release-maintenance.lock"
    if request.method in {"POST","PUT","PATCH","DELETE"} and marker.exists():
        return JSONResponse({"detail":"系统正在发布维护，请稍后重试"}, status_code=503,
                            headers={"Retry-After":"30"})
    return await call_next(request)


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "NeuroWeave API", "docs": "/docs"}


@app.get("/api/health")
def health(include_runtime: bool = True) -> dict[str, Any]:
    skill_stats = skill_loader.stats()
    skill_stats["execution_enabled"] = run_service.enabled
    result = {
        "status": "ok",
        "release": {
            "backend_revision": os.getenv("NEUROWEAVE_RELEASE_REVISION", "development"),
            "worker_revision": Path(os.getenv("LOCALFLOW_SLURM_WORKER_ROOT", "unversioned")).name,
            "maintenance": (DATABASE_PATH.parent / "release-maintenance.lock").exists(),
        },
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
            "output_root": str(OUTPUT_ROOT),
        },
    }
    if include_runtime:
        runners = runner_registry.public_catalog()
        result['execution'].update(ready_runner_count=sum(bool(item.get('available')) for item in runners), runners=runners)
    return result


def _storage_paths():
    backups = Path(os.getenv("LOCALFLOW_BACKUP_ROOT", str(DATABASE_PATH.parent / "backups")))
    roots = [OUTPUT_ROOT, Path(os.getenv("LOCALFLOW_SLURM_OUTPUT_ROOT", str(OUTPUT_ROOT)))]
    return backups, roots


@app.get("/api/maintenance/storage")
def maintenance_storage() -> dict[str, Any]:
    backups, roots = _storage_paths()
    return {**storage_status(DATABASE_PATH, backups, roots),
            "backend_revision":os.getenv("NEUROWEAVE_RELEASE_REVISION","development")}


@app.post("/api/maintenance/inventory-jobs", status_code=202)
def maintenance_inventory() -> dict[str, Any]:
    _, roots = _storage_paths()
    try:
        return operation_service.submit("storage_inventory", "outputs",
                                        lambda: inventory_outputs(DATABASE_PATH, roots))
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.get("/api/datasets/roots")
def dataset_roots() -> dict[str, Any]:
    return {"roots": [root.model_dump() for root in dataset_service.roots()]}


@app.get("/api/capabilities/tree")
def capabilities_tree() -> dict[str, Any]:
    return {
        "tree": capability_tree.compact(),
        "stats": capability_tree.stats(),
        "registered_capabilities": capability_registry.capabilities(),
    }


@app.get("/api/artifacts/types")
def artifact_types() -> dict[str, Any]:
    return {
        "artifact_types": [
            item.model_dump(mode="json") for item in capability_registry.artifact_types()
        ]
    }


@app.get("/api/datasets/directories", response_model=DirectoryListing)
def dataset_directories(root_id: str, relative_path: str = "") -> DirectoryListing:
    try:
        return dataset_service.list_directories(root_id, relative_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/operations/{operation_id}")
def get_operation(operation_id: str) -> dict[str, Any]:
    try:
        return operation_service.get(operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Operation not found") from exc


@app.post("/api/operations/{operation_id}/cancel")
def cancel_operation(operation_id: str) -> dict[str, Any]:
    try:
        return operation_service.cancel(operation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Operation not found") from exc


def _submit_operation(kind, key, action):
    try:
        return operation_service.submit(kind, key, action)
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@app.post("/api/datasets/register-jobs", status_code=202)
def register_dataset_job(request: DatasetRegisterRequest) -> dict[str, Any]:
    return _submit_operation("dataset_register", f"{request.root_id}:{request.relative_path}",
        lambda: dataset_service.register(request.root_id,request.relative_path,request.display_name))


@app.post("/api/datasets/{dataset_id}/inspect-jobs", status_code=202)
def inspect_dataset_job(dataset_id: str) -> dict[str, Any]:
    return _submit_operation("dataset_inspect", dataset_id, lambda: dataset_service.inspect(dataset_id))


@app.post("/api/workflows/{workflow_id}/dry-run-jobs", status_code=202)
def dry_run_job(workflow_id: str, request: WorkflowMutationRequest) -> dict[str, Any]:
    return _submit_operation("workflow_dry_run", f"{workflow_id}:{request.expected_revision}",
        lambda: workflow_service.dry_run(workflow_id,request.expected_revision))


@app.get("/api/datasets")
def list_datasets() -> dict[str, list[DatasetRecord]]:
    return {"datasets": dataset_service.list()}


@app.patch("/api/datasets/{dataset_id}/workspace", response_model=DatasetRecord)
def associate_dataset_workspace(dataset_id: str, request: DatasetWorkspaceRequest):
    try:
        if request.workspace_id:
            workspace_service.get(request.workspace_id)
        dataset = dataset_service.get(dataset_id).model_copy(update={"workspace_id": request.workspace_id})
        local_store.save_dataset(dataset)
        return dataset
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.patch("/api/workflows/{workflow_id}/output", response_model=Workflow)
def set_workspace_output(workflow_id: str, request: WorkflowOutputRequest):
    try:
        with run_service._lock, workflow_service._lock:
            if request.conversation_id and not local_store.get_conversation(request.conversation_id):
                raise ValueError("对话不存在")
            workflow = workflow_service.get(workflow_id)
            if workflow.revision != request.expected_revision:
                raise ValueError("流程版本已变化，请刷新")
            if workflow.status == "confirmed" or local_store.active_run_for_workflow(workflow_id):
                raise ValueError("请先解锁流程；已有任务的输出目录不受后续修改影响")
            if "workspace_id" in request.model_fields_set:
                selected = workspace_service.get(request.workspace_id) if request.workspace_id else None
                workflow.workspace_id = selected.id if selected else None
                workflow.workspace_root_path = selected.root_path if selected else None
            if workflow.workspace_root_path:
                root = workspace_service.validate_output_directory(Path(workflow.workspace_root_path))
                output = workspace_service.paths.output_root(str(root), request.relative_path)
                protect_datasets(local_store, output)
                workflow.output_relative_path = str(output.relative_to(root))
            elif "workspace_id" in request.model_fields_set:
                output = OUTPUT_ROOT
                workflow.output_relative_path = "outputs"
            else:
                raise ValueError("请先选择输出目录")
            workflow_service._advance(workflow)
            workflow.dry_run_report = None
            workflow_service._refresh(workflow)
            local_store.save_workflow(workflow, event_type="workspace_output_changed", event_payload={"path": str(output)})
            if "workspace_id" in request.model_fields_set and request.conversation_id:
                workspace_service.bind_conversation(request.conversation_id, request.workspace_id)
            return workflow
    except (ValueError, KeyError, OSError) as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/datasets/register", response_model=DatasetRecord)
def register_dataset(request: DatasetRegisterRequest) -> DatasetRecord:
    try:
        return dataset_service.register(
            request.root_id,
            request.relative_path,
            request.display_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/datasets/{dataset_id}", response_model=DatasetRecord)
def get_dataset(dataset_id: str) -> DatasetRecord:
    try:
        return dataset_service.get(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc


@app.post("/api/datasets/{dataset_id}/inspect", response_model=DatasetRecord)
def inspect_dataset(dataset_id: str) -> DatasetRecord:
    try:
        return dataset_service.inspect(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Dataset not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/skills")
def list_skills(q: str = "", source: str = "") -> dict[str, Any]:
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
    methods_by_skill: dict[str, list[Any]] = {}
    for method in capability_registry.all_methods():
        methods_by_skill.setdefault(method.skill_id, []).append(method)
    runtime_statuses: dict[str, dict] = {}
    return {
        "skills": [_skill_with_execution_status(skill, methods_by_skill.get(skill.name, []), runtime_statuses) for skill in skills],
        "stats": {
            **skill_stats,
            "capability_catalog": capability_registry.stats(),
        },
    }


@app.get("/api/skills/graph")
def skill_graph() -> dict[str, Any]:
    graph, _metadata = load_skill_graph(SKILLS_DIR)
    return {
        "nodes": len(graph),
        "edges": sum(len(dependencies) for dependencies in graph.values()),
        "cycles": find_cycles(graph),
        "missing_dependencies": find_missing_deps(graph),
        "graph": graph,
    }


@app.get("/api/skills/{skill_name}")
def get_skill(skill_name: str) -> dict[str, Any]:
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
        "instructions": skill.overview or skill.prompt_excerpt(),
        "reference_chars": len(skill.instructions),
        "layered": bool(skill.overview),
        "files": files,
    }


@app.get("/api/skills/{skill_name}/methods")
def skill_methods(skill_name: str, q: str = Query('', max_length=500),
                  cursor: str = '', limit: int = Query(20, ge=1, le=50), executable_only: bool = False):
    try:
        return skill_catalog.list_methods(skill_name, q, cursor, limit, executable_only)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/skill-methods/{capability}/{method_id}")
def skill_method(capability: str, method_id: str):
    try:
        return skill_catalog.method(capability, method_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/skills/{skill_name}/reference")
def skill_reference(skill_name: str, offset: int = Query(0, ge=0, le=2000000),
                    max_chars: int = Query(6000, ge=1, le=12000)):
    try:
        return skill_catalog.read_reference(skill_name, offset, max_chars)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/conversations", response_model=ConversationRecord)
def create_conversation() -> ConversationRecord:
    return conversation_service.create()


@app.get("/api/conversations", response_model=ConversationPage)
def list_conversations(
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
def delete_conversation(conversation_id: str) -> Response:
    try:
        conversation_service.delete(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=204)


@app.patch("/api/conversations/{conversation_id}", response_model=ConversationRecord)
def update_conversation(
    conversation_id: str,
    request: ConversationUpdateRequest,
) -> ConversationRecord:
    try:
        if "workspace_id" in request.model_fields_set:
            workspace_service.bind_conversation(conversation_id, request.workspace_id)
            if request.title is None and request.archived is None:
                return local_store.get_conversation(conversation_id)
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
def get_conversation(conversation_id: str, limit: int = Query(40,ge=1,le=100), before_sequence: int | None = Query(None,ge=1)) -> ConversationSnapshot:
    try:
        return conversation_service.snapshot(conversation_id,limit=limit,before_sequence=before_sequence)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@app.post("/api/conversations/{conversation_id}/compact", response_model=ConversationSnapshot)
async def compact_conversation(conversation_id: str) -> ConversationSnapshot:
    try:
        await conversation_service.compact_if_needed(conversation_id, force=True)
        return conversation_service.snapshot(conversation_id,limit=40)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    request = _workspace_request(request)
    try:
        request, conversation_id = conversation_service.begin_turn(request)
        if request.workspace_id:
            workspace_service.bind_conversation(conversation_id, request.workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Conversation not found") from exc

    async def finalize(response: ChatResponse) -> ChatResponse:
        response = response.model_copy(update={"workspace_id": request.workspace_id,
            "workspace_tool_events": workspace_service.events(request.client_turn_id) if request.client_turn_id else []})
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
        workspace_answer = await workspace_tools.reply(request)
        if workspace_answer is not None:
            return await finalize(ChatResponse(content=workspace_answer, provider_used=chat_service.provider_name,
                model_used=chat_service.model or "conversation-demo", mode=chat_service.mode,
                selected_skills=[skill.name for skill in selected], interaction_mode=request.interaction_mode))
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
            _workspace_request(ChatRequest(**request.model_dump()))
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
def get_workflow(workflow_id: str) -> Workflow:
    try:
        return workflow_service.get(workflow_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc


@app.get("/api/workflows")
def list_workflows(limit: int = 50) -> dict[str, list[Workflow]]:
    return {"workflows": workflow_service.list(limit)}


@app.get("/api/workflows/{workflow_id}/events")
def workflow_events(workflow_id: str) -> dict[str, Any]:
    try:
        return {"events": workflow_service.events(workflow_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc


@app.patch("/api/workflows/{workflow_id}/steps/{step_id}/method", response_model=Workflow)
def select_workflow_method(
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
def lock_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.lock_chain(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/api/workflows/{workflow_id}/dataset", response_model=Workflow)
def change_workflow_dataset(workflow_id: str, request: WorkflowDatasetRequest) -> Workflow:
    try:
        return workflow_service.change_dataset(
            workflow_id, request.dataset_id, request.expected_revision,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow or dataset not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/unlock", response_model=Workflow)
def unlock_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.unlock_chain(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/steps/{step_id}/remove", response_model=Workflow)
def remove_workflow_step(workflow_id: str, step_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.remove_step(workflow_id, step_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow or step not found") from exc
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
def bind_workflow_input(
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
def preview_workflow_input(
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


@app.get("/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/history")
def historical_input_candidates(workflow_id: str, step_id: str, slot_id: str,
                                offset: int = Query(0, ge=0, le=1000000)):
    try:
        return workflow_service.historical_input_candidates(workflow_id, step_id, slot_id, offset)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/history/preview")
def preview_historical_input(workflow_id: str, step_id: str, slot_id: str, request: HistoricalSelectionRequest):
    try:
        return workflow_service.preview_historical_input(workflow_id, step_id, slot_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow or historical run not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/steps/{step_id}/inputs/{slot_id}/history", response_model=Workflow)
def bind_historical_input(workflow_id: str, step_id: str, slot_id: str, request: HistoricalSelectionRequest):
    try:
        return workflow_service.bind_historical_input(workflow_id, step_id, slot_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow or historical run not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/workflows/{workflow_id}/steps/{step_id}/parameters", response_model=Workflow)
def update_workflow_parameters(
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
def review_workflow_parameters(
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
def dry_run_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.dry_run(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/confirm", response_model=Workflow)
def confirm_workflow(workflow_id: str, request: WorkflowMutationRequest) -> Workflow:
    try:
        return workflow_service.confirm(workflow_id, request.expected_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except RevisionConflict as exc:
        raise _revision_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/workflows/{workflow_id}/execution-draft")
def get_execution_draft(workflow_id: str) -> dict[str, Any]:
    if local_store.get_workflow(workflow_id) is None:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return local_store.execution_draft(workflow_id)


@app.put("/api/workflows/{workflow_id}/execution-draft")
def put_execution_draft(workflow_id: str, request: ExecutionDraftRequest) -> dict[str, Any]:
    try:
        return local_store.save_execution_draft(workflow_id, request.expected_revision,
            request.expected_draft_revision, request.execution)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/workflows/{workflow_id}/runs", response_model=WorkflowRun)
def start_workflow_run(
    workflow_id: str,
    request: RunCreateRequest,
) -> WorkflowRun:
    try:
        return run_service.create(workflow_id, request.expected_revision, request.execution)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except (RunConflict, ValueError, OSError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/runs")
def list_runs(
    workflow_id: str | None = None,
    limit: int = 50,
    summary: bool = False,
) -> dict[str, Any]:
    return {"runs": local_store.list_runs(workflow_id=workflow_id, limit=limit, summary=summary)}


@app.get("/api/execution/backends")
def execution_backends() -> dict[str, Any]:
    return run_service.execution_backends()


@app.get("/api/runs/{run_id}", response_model=WorkflowRun)
def get_run(run_id: str) -> WorkflowRun:
    try:
        return run_service.get(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/events")
def run_events(run_id: str, after_event_id: int = 0, before_event_id: int | None = Query(None, ge=1),
               tail: bool = False, limit: int = Query(1000, ge=1, le=1000)) -> dict[str, Any]:
    try:
        return local_store.run_event_page(run_id, after_event_id=after_event_id,
            before_event_id=before_event_id, tail=tail, limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.get("/api/runs/{run_id}/monitor")
def monitor_run(run_id: str, after_revision: int = -1) -> dict[str, Any]:
    try:
        return local_store.monitor_run(run_id, after_revision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc


@app.post("/api/runs/{run_id}/cancel", response_model=WorkflowRun)
def cancel_run(run_id: str) -> WorkflowRun:
    try:
        return run_service.cancel(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except RunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/retry", response_model=WorkflowRun)
def retry_run(run_id: str, request: RunRetryRequest) -> WorkflowRun:
    try:
        return run_service.retry(run_id, request.step_ids, request.sample_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except (RunConflict, ValueError, OSError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/recover-freesurfer")
def recover_freesurfer_run(
    run_id: str, request: RunCreateRequest, dry_run: bool = True,
) -> dict[str, Any]:
    try:
        return run_service.recover_freesurfer(
            run_id, request.expected_revision, dry_run=dry_run)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Run not found") from exc
    except RunConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/runs/{run_id}/resume-monitoring", response_model=WorkflowRun)
def resume_slurm_monitoring(run_id: str) -> WorkflowRun:
    try:
        return run_service.resume_slurm_monitoring(run_id)
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
