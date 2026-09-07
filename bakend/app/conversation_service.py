from __future__ import annotations

import base64
import binascii
import json
import math
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from .chat_service import ChatService
from .conversation_models import (
    ConversationListItem,
    ConversationMemoryStatus,
    ConversationPage,
    ConversationRecord,
    ConversationSnapshot,
)
from .local_store import LocalStore
from .models import ChatRequest, ChatResponse, Message


class ConversationService:
    """Own server-side history and compact older turns into a working summary."""

    def __init__(
        self,
        store: LocalStore,
        chat_service: ChatService,
        *,
        compact_trigger_tokens: int | None = None,
        keep_recent_messages: int | None = None,
    ) -> None:
        self.store = store
        self.chat_service = chat_service
        self.compact_trigger_tokens = max(
            256,
            compact_trigger_tokens
            if compact_trigger_tokens is not None
            else int(os.getenv("LOCALFLOW_HISTORY_COMPACT_TRIGGER_TOKENS", "12000")),
        )
        self.keep_recent_messages = max(
            4,
            keep_recent_messages
            if keep_recent_messages is not None
            else int(os.getenv("LOCALFLOW_HISTORY_KEEP_RECENT_MESSAGES", "8")),
        )

    def create(self, title: str = "新数据处理对话") -> ConversationRecord:
        now = self._now()
        conversation = ConversationRecord(
            conversation_id=f"conv_{uuid4().hex[:16]}",
            title=title.strip()[:120] or "新数据处理对话",
            created_at=now,
            updated_at=now,
        )
        self.store.create_conversation(conversation)
        return conversation

    def list(
        self,
        limit: int = 100,
        *,
        query: str = "",
        archived: bool = False,
    ) -> list[ConversationListItem]:
        return self.store.list_conversations(
            limit,
            query=query,
            archived=archived,
        )

    def list_page(
        self,
        limit: int = 20,
        *,
        query: str = "",
        archived: bool = False,
        cursor: str = "",
    ) -> ConversationPage:
        safe_limit = max(1, min(limit, 50))
        before_updated_at, before_conversation_id = self._decode_cursor(cursor)
        rows = self.store.list_conversations(
            safe_limit + 1,
            query=query,
            archived=archived,
            before_updated_at=before_updated_at,
            before_conversation_id=before_conversation_id,
        )
        has_more = len(rows) > safe_limit
        conversations = rows[:safe_limit]
        next_cursor = None
        if has_more and conversations:
            last = conversations[-1]
            next_cursor = self._encode_cursor(last.updated_at, last.conversation_id)
        return ConversationPage(
            conversations=conversations,
            next_cursor=next_cursor,
            has_more=has_more,
        )

    def update(
        self,
        conversation_id: str,
        *,
        title: str | None = None,
        archived: bool | None = None,
    ) -> ConversationRecord:
        if title is None and archived is None:
            raise ValueError("至少需要提供一个要更新的字段")
        normalized_title = None
        if title is not None:
            normalized_title = re.sub(r"\s+", " ", title).strip()
            if not normalized_title:
                raise ValueError("对话标题不能为空")
            normalized_title = normalized_title[:120]
        conversation = self.store.update_conversation(
            conversation_id,
            title=normalized_title,
            archived=archived,
            updated_at=self._now(),
        )
        if conversation is None:
            raise KeyError(conversation_id)
        return conversation

    def delete(self, conversation_id: str) -> None:
        if not self.store.delete_archived_conversation(conversation_id):
            raise KeyError(conversation_id)

    def begin_turn(self, request: ChatRequest) -> tuple[ChatRequest, str]:
        conversation = (
            self.store.get_conversation(request.conversation_id)
            if request.conversation_id
            else None
        )
        if request.conversation_id and conversation is None:
            raise KeyError("Conversation not found")
        if conversation is None:
            conversation = self.create(self._title_from_message(request.message))
            self._import_legacy_history(conversation, request.history)

        history_records = self.store.conversation_messages(
            conversation.conversation_id,
            after_sequence=conversation.summarized_through_sequence,
        )
        history = [
            Message(role=message.role, content=message.content)
            for message in history_records
        ]
        self.store.append_conversation_message(
            conversation.conversation_id,
            role="user",
            content=request.message,
            estimated_tokens=self.estimate_tokens(request.message),
            metadata={
                "interaction_mode": request.interaction_mode,
                "dataset_id": request.dataset_id,
                "selected_skills": request.selected_skills,
            },
            created_at=self._now(),
        )
        prepared = request.model_copy(
            update={
                "conversation_id": conversation.conversation_id,
                "conversation_summary": conversation.summary,
                "history": history,
            }
        )
        return prepared, conversation.conversation_id

    async def finish_turn(
        self,
        conversation_id: str,
        response: ChatResponse,
    ) -> ConversationMemoryStatus:
        self.store.append_conversation_message(
            conversation_id,
            role="assistant",
            content=response.content,
            estimated_tokens=self.estimate_tokens(response.content),
            metadata={
                "response_type": response.type,
                "selected_skills": response.selected_skills,
                "recommended_capabilities": response.recommended_capabilities,
                "workflow_id": response.workflow.workflow_id if response.workflow else None,
                "interaction_mode": response.interaction_mode,
                "workflow_recommended": response.workflow_recommended,
                "clarification_required": response.clarification_required,
                "capability_routing": (
                    response.capability_routing.model_dump(mode="json")
                    if response.capability_routing
                    else None
                ),
                "capability_recommendation": (
                    response.capability_recommendation.model_dump(mode="json")
                    if response.capability_recommendation
                    else None
                ),
            },
            created_at=self._now(),
        )
        compacted = await self.compact_if_needed(conversation_id)
        return self.memory_status(conversation_id, compacted_this_turn=compacted)

    async def compact_if_needed(
        self,
        conversation_id: str,
        *,
        force: bool = False,
    ) -> bool:
        conversation = self._require(conversation_id)
        messages = self.store.conversation_messages(
            conversation_id,
            after_sequence=conversation.summarized_through_sequence,
        )
        estimated = self.estimate_tokens(conversation.summary) + sum(
            message.estimated_tokens for message in messages
        )
        if not force and estimated < self.compact_trigger_tokens:
            return False
        keep = min(self.keep_recent_messages, max(2, len(messages) // 2))
        candidates = messages[:-keep]
        if not candidates:
            return False
        try:
            summary = await self.chat_service.compact_history(
                conversation.summary,
                candidates,
            )
        except Exception:
            return False
        if not summary.strip():
            return False
        self.store.update_conversation_summary(
            conversation_id,
            summary=summary.strip(),
            summary_version=conversation.summary_version + 1,
            summarized_through_sequence=candidates[-1].sequence,
            updated_at=self._now(),
        )
        return True

    def snapshot(self, conversation_id: str) -> ConversationSnapshot:
        conversation = self._require(conversation_id)
        messages = self.store.conversation_messages(conversation_id)
        recent = self.store.conversation_messages(
            conversation_id,
            after_sequence=conversation.summarized_through_sequence,
        )
        return ConversationSnapshot(
            conversation=conversation,
            memory=self.memory_status(conversation_id),
            messages=messages,
            recent_messages=recent,
        )

    def memory_status(
        self,
        conversation_id: str,
        *,
        compacted_this_turn: bool = False,
    ) -> ConversationMemoryStatus:
        conversation = self._require(conversation_id)
        recent = self.store.conversation_messages(
            conversation_id,
            after_sequence=conversation.summarized_through_sequence,
        )
        return ConversationMemoryStatus(
            summary_version=conversation.summary_version,
            summarized_messages=conversation.summarized_through_sequence,
            recent_messages=len(recent),
            estimated_recent_tokens=sum(item.estimated_tokens for item in recent),
            compacted_this_turn=compacted_this_turn,
        )

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Conservative local estimate for mixed Chinese and ASCII text."""
        cjk = len(re.findall(r"[\u3400-\u9fff]", text))
        non_cjk = max(0, len(text) - cjk)
        return max(1, cjk + math.ceil(non_cjk / 4) + 4)

    def _import_legacy_history(
        self,
        conversation: ConversationRecord,
        history: list[Message],
    ) -> None:
        for message in history[-20:]:
            self.store.append_conversation_message(
                conversation.conversation_id,
                role=message.role,
                content=message.content,
                estimated_tokens=self.estimate_tokens(message.content),
                metadata={"source": "legacy_client_history"},
                created_at=self._now(),
            )

    def _require(self, conversation_id: str) -> ConversationRecord:
        conversation = self.store.get_conversation(conversation_id)
        if conversation is None:
            raise KeyError(conversation_id)
        return conversation

    @staticmethod
    def _title_from_message(message: str) -> str:
        title = re.sub(r"\s+", " ", message).strip()
        return title[:48] or "新数据处理对话"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _encode_cursor(updated_at: str, conversation_id: str) -> str:
        payload = json.dumps(
            {"updated_at": updated_at, "conversation_id": conversation_id},
            separators=(",", ":"),
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[str | None, str | None]:
        if not cursor:
            return None, None
        try:
            if len(cursor) > 1024:
                raise ValueError
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(base64.b64decode(cursor + padding, altchars=b"-_", validate=True))
            updated_at = payload["updated_at"]
            conversation_id = payload["conversation_id"]
            if not isinstance(updated_at, str) or not updated_at:
                raise ValueError
            if not isinstance(conversation_id, str) or not conversation_id:
                raise ValueError
            return updated_at, conversation_id
        except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("无效的对话分页游标") from exc
