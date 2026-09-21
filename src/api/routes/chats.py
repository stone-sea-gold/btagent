"""Chat history API routes."""

from fastapi import APIRouter
from pydantic import BaseModel

from src.api.dependencies import get_services

router = APIRouter()


class ChatSave(BaseModel):
    id: str
    messages: list[dict]
    title: str | None = None


@router.get("")
def list_chats():
    services = get_services()
    return {"chats": services.chat_store.list_chats()}


@router.get("/{chat_id}")
def get_chat(chat_id: str):
    services = get_services()
    chat = services.chat_store.get_chat(chat_id)
    if chat is None:
        return {"found": False}
    return {"found": True, "chat": chat}


@router.post("")
def save_chat(data: ChatSave):
    services = get_services()
    services.chat_store.save_chat(data.id, data.messages, data.title)
    return {"status": "saved", "id": data.id}


@router.delete("/{chat_id}")
def delete_chat(chat_id: str):
    services = get_services()
    services.chat_store.delete_chat(chat_id)
    return {"status": "deleted"}
