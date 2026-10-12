"""Operations HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..access.contracts import AuthorizationDenied
from ..application_services import ApplicationServices


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    def owner() -> str:
        if services.authorization_service is None:
            raise AuthorizationDenied("authentication_required")
        return services.authorization_service.require_authenticated().user_id

    @router.get("/api/operations/{operation_id}")
    def get_operation(operation_id: str) -> dict[str, Any]:
        try:
            return services.operation_service.get(operation_id, owner_id=owner())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Operation not found") from exc

    @router.post("/api/operations/{operation_id}/cancel")
    def cancel_operation(operation_id: str) -> dict[str, Any]:
        try:
            return services.operation_service.cancel(operation_id, owner_id=owner())
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Operation not found") from exc

    return router
