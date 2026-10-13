"""Datasets HTTP endpoints; dependencies are supplied by the application factory.

Datasets are read-only inputs. Registration needs a live read grant on the
physical directory; listing, inspection and binding need object permission.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ..access.contracts import AuthorizationDenied, ResourceAction, ResourceType
from ..access.filesystem import GrantScope
from ..application_services import ApplicationServices
from ..dataset_models import (
    DatasetRecord,
    DatasetRegisterRequest,
    DirectoryListing,
)
from ..workspace_models import DatasetWorkspaceRequest
from .errors import submit_operation

DATASET = ResourceType.DATASET


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    def access():
        if services.resource_access is None or services.directory_access is None:
            raise AuthorizationDenied("authentication_required")
        return services.resource_access

    def directories():
        access()
        return services.directory_access

    def annotate(dataset: DatasetRecord) -> dict[str, Any]:
        return access().annotate(DATASET, dataset.dataset_id, dataset.model_dump(mode="json"))

    def require_registration_scope(root_id: str, relative_path: str) -> None:
        """Directory grant plus duplicate/overlap protection before any write."""
        try:
            _root, directory, normalized = services.dataset_service._resolve(root_id, relative_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        directories().require(directory, GrantScope.READ)
        existing = services.local_store.find_dataset_by_path(root_id, normalized)
        if existing is not None and not access().can(DATASET, existing.dataset_id, ResourceAction.UPDATE):
            # Repeated registration of the same physical directory must not
            # adopt (or rename) a dataset owned in another scope.
            raise HTTPException(409, "This directory is already registered in another scope")
        resolved = directory.resolve()
        for dataset in services.local_store.list_datasets():
            other = Path(dataset.absolute_path).resolve()
            if other == resolved:
                continue
            if (resolved in other.parents or other in resolved.parents) and not access().can(
                DATASET, dataset.dataset_id, ResourceAction.UPDATE
            ):
                raise HTTPException(409, "This directory overlaps a dataset registered in another scope")

    def _registration_guard(request: DatasetRegisterRequest):
        base = access().background_guard()

        def authorize() -> None:
            base()
            # The directory grant is re-checked live before the dataset commit.
            require_registration_scope(request.root_id, request.relative_path)

        return authorize

    @router.get("/api/datasets/roots")
    def dataset_roots() -> dict[str, Any]:
        visible = []
        for root in services.dataset_service.roots():
            if directories().leads_to_grant(Path(root.path)):
                visible.append(root.model_dump())
        return {"roots": visible}

    @router.get("/api/datasets/directories", response_model=DirectoryListing)
    def dataset_directories(root_id: str, relative_path: str = "") -> DirectoryListing:
        try:
            _root, directory, _normalized = services.dataset_service._resolve(root_id, relative_path)
            kind = directories().classify(directory)
            if kind is None:
                raise PermissionError("directory_grant_required")
            listing = services.dataset_service.list_directories(root_id, relative_path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if kind == "ancestor":
            # Above a grant only the path toward granted subtrees is shown.
            root_path = Path(listing.root.path).resolve()
            entries = [
                entry for entry in listing.directories
                if directories().leads_to_grant(root_path / entry.relative_path)
            ]
            listing = listing.model_copy(update={
                "directories": entries, "files": [],
                "directory_count": len(entries), "file_count": 0,
                "directories_truncated": False, "files_truncated": False,
            })
        return listing

    @router.post("/api/datasets/register-jobs", status_code=202)
    def register_dataset_job(request: DatasetRegisterRequest) -> dict[str, Any]:
        require_registration_scope(request.root_id, request.relative_path)
        return submit_operation(
            services.operation_service,
            "dataset_register",
            f"{request.root_id}:{request.relative_path}",
            lambda: services.dataset_service.register(
                request.root_id, request.relative_path, request.display_name
            ),
            owner_id=access().actor().user_id,
            authorize=_registration_guard(request),
        )

    @router.post("/api/datasets/{dataset_id}/inspect-jobs", status_code=202)
    def inspect_dataset_job(dataset_id: str) -> dict[str, Any]:
        access().require(DATASET, dataset_id, ResourceAction.UPDATE)
        return submit_operation(
            services.operation_service,
            "dataset_inspect",
            dataset_id,
            lambda: services.dataset_service.inspect(dataset_id),
            owner_id=access().actor().user_id,
            authorize=access().background_guard((DATASET, dataset_id, ResourceAction.UPDATE)),
        )

    @router.get("/api/datasets")
    def list_datasets() -> dict[str, list[dict[str, Any]]]:
        visible = access().visible_ids(DATASET)
        return {
            "datasets": [
                annotate(dataset) for dataset in services.dataset_service.list()
                if dataset.dataset_id in visible
            ]
        }

    @router.patch("/api/datasets/{dataset_id}/workspace", response_model=DatasetRecord)
    def associate_dataset_workspace(dataset_id: str, request: DatasetWorkspaceRequest):
        access().require(DATASET, dataset_id, ResourceAction.UPDATE)
        if request.workspace_id:
            access().require(ResourceType.OUTPUT, request.workspace_id, ResourceAction.READ)
        try:
            if request.workspace_id:
                services.workspace_service.get(request.workspace_id)
            dataset = services.dataset_service.get(dataset_id).model_copy(
                update={"workspace_id": request.workspace_id}
            )
            services.local_store.save_dataset(dataset)
            return dataset
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc)) from exc

    @router.post("/api/datasets/register", response_model=DatasetRecord)
    def register_dataset(request: DatasetRegisterRequest) -> DatasetRecord:
        require_registration_scope(request.root_id, request.relative_path)
        try:
            return services.dataset_service.register(
                request.root_id,
                request.relative_path,
                request.display_name,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/api/datasets/{dataset_id}", response_model=DatasetRecord)
    def get_dataset(dataset_id: str) -> DatasetRecord:
        # allowed_actions for one dataset: GET /api/access/resources/dataset/{id}
        try:
            access().require(DATASET, dataset_id, ResourceAction.READ)
            return services.dataset_service.get(dataset_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Dataset not found") from exc

    @router.post("/api/datasets/{dataset_id}/inspect", response_model=DatasetRecord)
    def inspect_dataset(dataset_id: str) -> DatasetRecord:
        try:
            access().require(DATASET, dataset_id, ResourceAction.UPDATE)
            return services.dataset_service.inspect(dataset_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Dataset not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return router
