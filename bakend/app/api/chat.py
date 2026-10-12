"""Chat HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..application_services import ApplicationServices
from ..models import ChatRequest, ChatResponse
from ..access.service import AuthorizationDenied


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    def authorization_error(exc: AuthorizationDenied) -> HTTPException:
        return HTTPException(status_code=403, detail=str(exc))

    @router.post("/api/chat/turns")
    async def submit_chat_turn(request: ChatRequest):
        return services.chat_turns.submit(request)

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

    @router.post("/api/chat/turns/{identity}/cancel")
    def cancel_chat_turn(identity: str):
        try:
            return services.chat_turns.cancel(identity)
        except KeyError as exc:
            raise HTTPException(404, "Turn not found") from exc

    @router.post("/api/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        turn = services.chat_turns.submit(request)
        return await services.chat_turns.wait(turn["turn_id"])

    return router
