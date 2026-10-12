"""Chat HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..application_services import ApplicationServices
from ..models import ChatRequest, ChatResponse
from ..access.service import AuthorizationDenied


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    def require_current_user() -> None:
        if services.authorization_service is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            services.authorization_service.require_authenticated()
        except AuthorizationDenied as exc:
            raise HTTPException(status_code=401, detail="Authentication required") from exc

    def authorization_error(exc: AuthorizationDenied) -> HTTPException:
        return HTTPException(status_code=403, detail=str(exc))

    @router.get("/api/chat/scope")
    def chat_scope():
        if services.authorization_service is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        try:
            identity = services.authorization_service.require_authenticated()
        except AuthorizationDenied as exc:
            raise HTTPException(status_code=401, detail="Authentication required") from exc
        return {"userId": identity.user_id, "projectId": None}

    @router.post("/api/chat/turns")
    async def submit_chat_turn(request: ChatRequest):
        require_current_user()
        try:
            return services.chat_turns.submit(request)
        except AuthorizationDenied as exc:
            raise authorization_error(exc) from exc

    @router.get("/api/chat/turns/{identity}")
    def get_chat_turn(identity: str):
        try:
            return services.chat_turns.get(identity)
        except KeyError as exc:
            raise HTTPException(404, "Turn not found") from exc
        except AuthorizationDenied as exc:
            raise authorization_error(exc) from exc

    @router.post("/api/chat/turns/{identity}/retry")
    async def retry_chat_turn(identity: str):
        try:
            return services.chat_turns.retry(identity)
        except KeyError as exc:
            raise HTTPException(404, "Turn not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except AuthorizationDenied as exc:
            raise authorization_error(exc) from exc

    @router.post("/api/chat/turns/{identity}/cancel")
    def cancel_chat_turn(identity: str):
        try:
            return services.chat_turns.cancel(identity)
        except KeyError as exc:
            raise HTTPException(404, "Turn not found") from exc
        except AuthorizationDenied as exc:
            raise authorization_error(exc) from exc

    @router.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        require_current_user()
        try:
            turn = services.chat_turns.submit(request)
            return await services.chat_turns.wait(turn["turn_id"])
        except AuthorizationDenied as exc:
            raise authorization_error(exc) from exc

    return router
