"""Library browsing and structured Pipeline authoring API."""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

class SaveWorkflowPipeline(BaseModel):
    expected_revision: int
    name: str = Field(default='',max_length=160)
from .pipeline_library import ComposeRequest, UsePipeline


def library_router(library, workflows, workspaces, runners):
    router=APIRouter()

    @router.get('/api/library')
    def listing(kind: str=Query('method',pattern='^(skill|method|pipeline)$'),q: str=Query('',max_length=500),
                cursor: int=Query(0,ge=0),limit: int=Query(50,ge=1,le=200)):
        return library.catalog(kind,q,cursor,limit)

    @router.get('/api/library/methods/{identity}')
    def method(identity: str):
        try:
            value=library.registry.definitions.method(identity).model_dump(mode='json')
            runner=runners.get(identity)
            value['verification']=library.registry.definitions.verification(identity)
            value['runtime_status']=runner.runtime_status() if runner else {'available':False,'reason':'Runner 未注册'}
            return value
        except KeyError as exc:raise HTTPException(404,str(exc)) from exc

    @router.get('/api/library/pipelines/{identity}')
    def pipeline(identity: str,version: int | None=None):
        try:return library.get(identity,version)
        except KeyError as exc:raise HTTPException(404,str(exc)) from exc

    @router.post('/api/library/pipelines/validate')
    def validate(request: ComposeRequest):
        try:return library.compile(request)
        except (ValueError,KeyError) as exc:raise HTTPException(422,str(exc)) from exc

    @router.post('/api/library/pipelines')
    def create(request: ComposeRequest):
        try:return library.save(request)
        except (ValueError,KeyError) as exc:raise HTTPException(422,str(exc)) from exc

    @router.put('/api/library/pipelines/{identity}')
    def update(identity: str,request: ComposeRequest):
        try:return library.save(request,identity)
        except (ValueError,KeyError) as exc:raise HTTPException(409,str(exc)) from exc

    @router.post('/api/library/pipelines/{identity}/workflows')
    def use(identity: str,request: UsePipeline):
        try:return library.workflow(identity,request,workflows,workspaces)
        except (ValueError,KeyError,OSError) as exc:raise HTTPException(422,str(exc)) from exc

    @router.post('/api/library/from-workflow/{workflow_id}')
    def from_workflow(workflow_id: str,request: SaveWorkflowPipeline):
        try:
            with workflows._lock:
                workflow=workflows.get(workflow_id)
                if workflow.revision!=request.expected_revision:raise ValueError('流程版本已变化，请刷新')
                return library.from_workflow(workflow,request.name)
        except (ValueError,KeyError,RuntimeError) as exc:raise HTTPException(422,str(exc)) from exc

    return router
