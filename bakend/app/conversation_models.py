from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ConversationMessageRecord(BaseModel):
    message_id: int
    conversation_id: str
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    estimated_tokens: int
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ConversationRecord(BaseModel):
    workspace_id: str | None = None
    conversation_id: str
    title: str
    archived: bool = False
    summary: str = ""
    summary_version: int = 0
    summarized_through_sequence: int = 0
    created_at: str
    updated_at: str


class ConversationListItem(BaseModel):
    workspace_id: str | None = None
    conversation_id: str
    title: str
    archived: bool = False
    created_at: str
    updated_at: str
    message_count: int = 0
    last_message_preview: str = ""
    last_message_role: Literal["user", "assistant"] | None = None


class ConversationPage(BaseModel):
    conversations: list[ConversationListItem] = Field(default_factory=list)
    next_cursor: str | None = None
    has_more: bool = False


class ConversationUpdateRequest(BaseModel):
    workspace_id: str | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None


class ConversationMemoryStatus(BaseModel):
    summary_version: int = 0
    summarized_messages: int = 0
    recent_messages: int = 0
    estimated_recent_tokens: int = 0
    compacted_this_turn: bool = False


class ConversationSnapshot(BaseModel):
    conversation: ConversationRecord
    memory: ConversationMemoryStatus
    messages: list[ConversationMessageRecord] = Field(default_factory=list)
    recent_messages: list[ConversationMessageRecord] = Field(default_factory=list)
    has_more: bool = False
    before_sequence: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)
