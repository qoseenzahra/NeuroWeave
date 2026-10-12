"""Library browsing and structured Pipeline authoring API."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .access.contracts import AuthorizationDenied, ResourceAction, ResourceType
from .pipeline_models import ComposeRequest, UsePipeline, DeletePipeline, RestorePipeline
from .pipeline_management import DraftDeletedError
from .pipeline_repository import PipelineDeletedError


class SaveWorkflowPipeline(BaseModel):
    expected_revision: int
    name: str = Field(default="", max_length=160)


class RestoreDraft(BaseModel):
    expected_revision: int = Field(ge=0)


PIPELINE = ResourceType.PIPELINE
DRAFT = ResourceType.PIPELINE_DRAFT


def library_router(library, workflows, workspaces, runners, chat=None, *, access=None):
    router = APIRouter()
    from .pipeline_description import PipelineDescriber
    from .pipeline_models import DraftSave

    describer = PipelineDescriber(library, chat)

    def resource_access():
        if access is None:
            raise AuthorizationDenied("authentication_required")
        return access

    def require_pipeline(identity, action):
        """User Pipelines are owned; built-in ones are readable by all users."""
        if identity.startswith("user-"):
            resource_access().require(PIPELINE, identity, action)
        else:
            # Built-ins are visible to every logged-in user; the library itself
            # rejects any attempt to modify them (read-only trust rule).
            resource_access().actor()

    def require_draft(identity, action, *, creating=False):
        policy = resource_access().policy(DRAFT, identity)
        if policy is None:
            if creating:
                # A brand-new draft id: ownership is recorded on first save.
                resource_access().actor()
                return
            raise HTTPException(404, "Draft not found")
        resource_access().require(DRAFT, identity, action)

    @router.get("/api/library/drafts")
    def drafts():
        return {"items": library.drafts(), **library.draft_trash()}

    def validate_draft_id(identity):
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identity):
            raise HTTPException(422, "Invalid draft ID")

    @router.delete("/api/library/drafts/{identity}")
    def delete_draft(identity: str, request: DraftSave):
        validate_draft_id(identity)
        require_draft(identity, ResourceAction.DELETE)
        try:
            return library.delete_draft(identity, request)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/api/library/drafts/{identity}/restore")
    def restore_draft(identity: str, request: RestoreDraft):
        validate_draft_id(identity)
        require_draft(identity, ResourceAction.RESTORE)
        try:
            return library.restore_draft(identity, request.expected_revision)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.put("/api/library/drafts/{identity}")
    def save_draft(identity: str, request: DraftSave):
        validate_draft_id(identity)
        # Covers explicit saves and the editor's background autosave.
        require_draft(identity, ResourceAction.UPDATE, creating=True)
        try:
            return library.save_draft(identity, request)
        except DraftDeletedError as exc:
            raise HTTPException(409, {"code": "draft_deleted", "message": str(exc)}) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/api/library/pipelines/describe")
    async def describe(
        request: ComposeRequest, language: str = Query("zh", pattern="^(zh|en)$")
    ):
        try:
            return await describer.describe(request, language)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/library/pipelines/{identity}/versions")
    def versions(identity: str):
        require_pipeline(identity, ResourceAction.READ)
        return {"items": [p for p in library.records() if p["id"] == identity]}

    @router.get("/api/library/pipelines/trash")
    def pipeline_trash():
        return {"items": library.trash()}

    @router.delete("/api/library/pipelines/{identity}")
    def delete_pipeline(identity: str, request: DeletePipeline):
        if not identity.startswith("user-"):
            raise HTTPException(422, "内置 Pipeline 只读，不能删除。")
        require_pipeline(identity, ResourceAction.DELETE)
        try:
            return library.delete(identity, request.expected_version, request.expected_deletion_revision)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/api/library/pipelines/{identity}/restore")
    def restore_pipeline(identity: str, request: RestorePipeline):
        require_pipeline(identity, ResourceAction.RESTORE)
        try:
            return library.restore(identity, request.expected_deletion_revision)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.get("/api/library/pipelines/{identity}/source")
    def source(identity: str, version: int | None = None):
        require_pipeline(identity, ResourceAction.READ)
        try:
            return library.source(identity, version)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/library/pipelines/{identity}/migration")
    def migration(identity: str, version: int | None = None):
        # Migration review is a less visible read path; it still needs READ.
        require_pipeline(identity, ResourceAction.READ)
        try:
            return library.migration(identity, version)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.patch("/api/library/pipelines/{identity}/versions/{version}")
    def lifecycle(
        identity: str,
        version: int,
        status: str = Query(pattern="^(published|archived)$"),
    ):
        require_pipeline(identity, ResourceAction.PUBLISH)
        try:
            return library.lifecycle(identity, version, status)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/api/library")
    def listing(
        kind: str = Query("method", pattern="^(skill|method|pipeline)$"),
        q: str = Query("", max_length=500),
        cursor: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200),
        category: str = Query("", max_length=150),
        software: str = Query("", max_length=100),
        language: str = Query("zh", pattern="^(zh|en)$"),
    ):
        return library.catalog(kind, q, cursor, limit, category, software, language)

    @router.get("/api/library/methods/{identity}")
    def method(identity: str):
        try:
            value = library.registry.definitions.method(identity).model_dump(
                mode="json"
            )
            runner = runners.get(identity)
            value["option_coverage"] = [
                {"flag": flag, "description": reason}
                for flag, reason in value.get("execution", {})
                .get("contract", {})
                .get("omitted_options", {})
                .items()
            ]
            value["verification"] = library.registry.definitions.verification(identity)
            value["runtime_status"] = (
                runner.runtime_status()
                if runner
                else {"available": False, "reason": "Runner 未注册"}
            )
            return value
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.get("/api/library/pipelines/{identity}")
    def pipeline(identity: str, version: int | None = None):
        require_pipeline(identity, ResourceAction.READ)
        try:
            value = library.get(identity, version)
            if identity.startswith("user-") and isinstance(value, dict):
                return resource_access().annotate(PIPELINE, identity, value)
            return value
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc

    @router.post("/api/library/pipelines/validate")
    def validate(request: ComposeRequest):
        try:
            return library.compile(request)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/api/library/pipelines")
    def create(request: ComposeRequest):
        try:
            return library.save(request)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.put("/api/library/pipelines/{identity}")
    def update(identity: str, request: ComposeRequest):
        require_pipeline(identity, ResourceAction.UPDATE)
        try:
            return library.save(request, identity)
        except PipelineDeletedError as exc:
            raise HTTPException(409, {"code": "pipeline_deleted", "message": str(exc)}) from exc
        except (ValueError, KeyError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/api/library/pipelines/{identity}/workflows")
    def use(identity: str, request: UsePipeline):
        # Using a (shared) Pipeline creates the caller's own task. The data,
        # output and conversation it binds are checked separately.
        require_pipeline(identity, ResourceAction.SUBMIT)
        if request.dataset_id:
            resource_access().require(ResourceType.DATASET, request.dataset_id, ResourceAction.READ)
        if request.workspace_id:
            resource_access().require(ResourceType.OUTPUT, request.workspace_id, ResourceAction.READ)
        if request.conversation_id:
            resource_access().require(ResourceType.CONVERSATION, request.conversation_id, ResourceAction.UPDATE)
        try:
            return library.workflow(identity, request, workflows, workspaces)
        except (ValueError, KeyError, OSError) as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.post("/api/library/from-workflow/{workflow_id}")
    def from_workflow(workflow_id: str, request: SaveWorkflowPipeline):
        resource_access().require(ResourceType.TASK, workflow_id, ResourceAction.READ)
        try:
            with workflows.mutation_lock:
                workflow = workflows.get(workflow_id)
                if workflow.revision != request.expected_revision:
                    raise ValueError("流程版本已变化，请刷新")
                return library.from_workflow(workflow, request.name)
        except (ValueError, KeyError, RuntimeError) as exc:
            raise HTTPException(422, str(exc)) from exc

    return router
