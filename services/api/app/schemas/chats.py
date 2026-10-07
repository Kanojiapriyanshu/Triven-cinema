from typing import Any

from pydantic import BaseModel, Field


class ChatUpsertRequest(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=120)
    created_at: int = Field(..., ge=0)
    updated_at: int = Field(..., ge=0)
    workspace: dict[str, Any]


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int
    workspace: dict[str, Any]


class ChatListResponse(BaseModel):
    chats: list[ChatSessionResponse]
    count: int
    max_saved: int
