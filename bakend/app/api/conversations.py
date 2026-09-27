"""Conversations HTTP endpoints; dependencies are supplied by the application factory."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from ..application_services import ApplicationServices
from ..conversation_models import (
    ConversationPage,
    ConversationRecord,
    ConversationSnapshot,
    ConversationUpdateRequest,
)


def router_for(services: ApplicationServices) -> APIRouter:
    router = APIRouter()

    @router.post("/api/conversations", response_model=ConversationRecord)
    def create_conversation() -> ConversationRecord:
        return services.conversation_service.create()

    @router.get("/api/conversations", response_model=ConversationPage)
    def list_conversations(
        limit: int = Query(default=20, ge=1, le=50),
        q: str = Query(default="", max_length=1000),
        archived: bool = False,
        cursor: str = Query(default="", max_length=1024),
    ) -> ConversationPage:
        try:
            return services.conversation_service.list_page(
                limit,
                query=q,
                archived=archived,
                cursor=cursor,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.delete("/api/conversations/{conversation_id}", status_code=204)
    def delete_conversation(conversation_id: str) -> Response:
        try:
            services.conversation_service.delete(conversation_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Conversation not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return Response(status_code=204)

    @router.patch(
        "/api/conversations/{conversation_id}", response_model=ConversationRecord
    )
    def update_conversation(
        conversation_id: str,
        request: ConversationUpdateRequest,
    ) -> ConversationRecord:
        try:
            if "workspace_id" in request.model_fields_set:
                services.workspace_service.bind_conversation(
                    conversation_id, request.workspace_id
                )
                if request.title is None and request.archived is None:
                    return services.local_store.get_conversation(conversation_id)
            return services.conversation_service.update(
                conversation_id,
                title=request.title,
                archived=request.archived,
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Conversation not found"
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get(
        "/api/conversations/{conversation_id}", response_model=ConversationSnapshot
    )
    def get_conversation(
        conversation_id: str,
        limit: int = Query(40, ge=1, le=100),
        before_sequence: int | None = Query(None, ge=1),
    ) -> ConversationSnapshot:
        try:
            return services.conversation_service.snapshot(
                conversation_id, limit=limit, before_sequence=before_sequence
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Conversation not found"
            ) from exc

    @router.post(
        "/api/conversations/{conversation_id}/compact",
        response_model=ConversationSnapshot,
    )
    async def compact_conversation(conversation_id: str) -> ConversationSnapshot:
        try:
            await services.conversation_service.compact_if_needed(
                conversation_id, force=True
            )
            return services.conversation_service.snapshot(conversation_id, limit=40)
        except KeyError as exc:
            raise HTTPException(
                status_code=404, detail="Conversation not found"
            ) from exc

    return router
