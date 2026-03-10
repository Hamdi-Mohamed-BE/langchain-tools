import json
from fastapi import APIRouter, Depends, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.schemas.chat import ChatMessageRead, ChatMessageRequest, ChatMessageResponse, ChatUsageSummary
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService


router = APIRouter()


def _parse_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    value = authorization.strip()
    if not value:
        return None
    if value.lower().startswith("bearer "):
        token = value[7:].strip()
        return token or None
    return None


def _resolve_user_id(
    user_id: int | None,
    access_token: str | None = None,
    authorization: str | None = None,
) -> tuple[int | None, str | None]:
    token = access_token or _parse_bearer_token(authorization)

    if token:
        decoded = AuthService.decode_token(token)
        if not decoded:
            return None, "Invalid or expired token."
        subject = decoded.get("sub")
        try:
            resolved = int(subject)
        except (TypeError, ValueError):
            return None, "Invalid token subject."
        if resolved < 1:
            return None, "Invalid token subject."
        return resolved, None

    if user_id is None:
        return None, "Missing authentication. Provide bearer token or user_id."
    if user_id < 1:
        return None, "Field 'user_id' must be a positive integer."
    return user_id, None


def _parse_ws_payload(payload: dict) -> tuple[int | None, str | None, str | None, str | None]:
    user_id = payload.get("user_id")
    access_token = str(payload.get("access_token") or "").strip() or None
    message = str(payload.get("message") or "").strip()

    parsed_user_id: int | None = None
    if user_id is not None:
        try:
            parsed_user_id = int(user_id)
        except (TypeError, ValueError):
            return None, None, None, "Field 'user_id' must be a positive integer."

    if parsed_user_id is not None and parsed_user_id < 1:
        return None, None, None, "Field 'user_id' must be a positive integer."
    if not message:
        return None, None, None, "Field 'message' is required."

    return parsed_user_id, message, access_token, None


@router.post("/message", response_model=ChatMessageResponse)
async def message(payload: ChatMessageRequest, db: Session = Depends(get_db)) -> ChatMessageResponse:
    service = ChatService(db)
    reply = await service.handle_message(user_id=payload.user_id, message=payload.message)
    return ChatMessageResponse(reply=reply)


@router.websocket("/ws")
async def websocket_chat(websocket: WebSocket):
    await websocket.accept()
    db = SessionLocal()
    service = ChatService(db)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "text": "Invalid JSON payload."})
                continue

            user_id, message, access_token, error = _parse_ws_payload(payload if isinstance(payload, dict) else {})
            if error:
                await websocket.send_json({"type": "error", "text": error})
                continue

            resolved_user_id, auth_error = _resolve_user_id(user_id=user_id, access_token=access_token)
            if auth_error:
                await websocket.send_json({"type": "error", "text": auth_error})
                continue

            await websocket.send_json({"type": "status", "text": "Thinking..."})
            async for event in service.stream_message(user_id=resolved_user_id, message=message):
                await websocket.send_json(event)
            await websocket.send_json({"type": "done"})
    except WebSocketDisconnect:
        return
    finally:
        db.close()


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
    user_id: int | None = Query(default=None),
    limit: int = Query(30, ge=1, le=200),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    resolved_user_id, auth_error = _resolve_user_id(user_id=user_id, authorization=authorization)
    if auth_error:
        status = 401 if "token" in auth_error.lower() or "auth" in auth_error.lower() else 400
        raise HTTPException(status_code=status, detail=auth_error)

    service = ChatService(db)
    raw_messages = service.repo.get_recent_messages(user_id=resolved_user_id, limit=limit)

    # Sanitize non-user messages to strip any sensitive data or raw JSON saved historically.
    for msg in raw_messages:
        if msg.role != "user":
            msg.content = service._sanitize_assistant_text(msg.content)

    # Filter out messages that became empty after sanitization.
    return [m for m in raw_messages if (m.content or "").strip()]


@router.get("/usage/summary", response_model=ChatUsageSummary)
async def usage_summary(
    user_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
):
    service = ChatService(db)
    return service.repo.get_usage_summary(user_id=user_id)
