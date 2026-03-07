import json
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.chat import ChatMessageRead, ChatMessageRequest, ChatMessageResponse, ChatUsageSummary
from app.services.chat_service import ChatService


router = APIRouter()


@router.post("/message", response_model=ChatMessageResponse)
async def message(payload: ChatMessageRequest, db: Session = Depends(get_db)) -> ChatMessageResponse:
    service = ChatService(db)
    reply = await service.handle_message(user_id=payload.user_id, message=payload.message)
    return ChatMessageResponse(reply=reply)


@router.get("/stream")
async def stream(
    user_id: int = Query(...),
    message: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    service = ChatService(db)

    async def event_generator():
        yield "data: " + json.dumps({"type": "status", "text": "Thinking..."}) + "\n\n"
        async for event in service.stream_message(user_id=user_id, message=message):
            yield "data: " + json.dumps(event) + "\n\n"
        yield "data: " + json.dumps({"type": "done"}) + "\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/history", response_model=list[ChatMessageRead])
async def history(
    user_id: int = Query(...),
    limit: int = Query(30, ge=1, le=200),
    db: Session = Depends(get_db),
):
    service = ChatService(db)
    return service.repo.get_recent_messages(user_id=user_id, limit=limit)


@router.get("/usage/summary", response_model=ChatUsageSummary)
async def usage_summary(
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = ChatService(db)
    return service.repo.get_usage_summary(user_id=user_id)
