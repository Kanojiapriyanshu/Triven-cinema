from fastapi import APIRouter, HTTPException, Request

from app.core.config import settings
from app.schemas.chats import ChatListResponse, ChatSessionResponse, ChatUpsertRequest
from app.services.auth_service import auth_user_from_request
from app.services.chat_service import ChatError, delete_chat, list_chats, save_chat


router = APIRouter()


def _workspace_id(request: Request) -> str:
    user = auth_user_from_request(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return str(user["workspace_id"])


@router.get("", response_model=ChatListResponse)
def list_workspace_chats(request: Request) -> ChatListResponse:
    chats = list_chats(_workspace_id(request))
    return ChatListResponse(
        chats=[ChatSessionResponse.model_validate(chat) for chat in chats],
        count=len(chats),
        max_saved=settings.chat_history_limit,
    )


@router.put("/{chat_id}", response_model=ChatSessionResponse)
def upsert_workspace_chat(chat_id: str, payload: ChatUpsertRequest, request: Request) -> ChatSessionResponse:
    try:
        chat = save_chat(
            _workspace_id(request),
            chat_id,
            title=payload.title,
            workspace=payload.workspace,
            created_at=payload.created_at,
            updated_at=payload.updated_at,
        )
    except ChatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatSessionResponse.model_validate(chat)


@router.delete("/{chat_id}")
def delete_workspace_chat(chat_id: str, request: Request) -> dict:
    removed = delete_chat(_workspace_id(request), chat_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Chat not found.")
    return {"deleted": True, "id": chat_id}
