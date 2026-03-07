from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.chat_usage import ChatUsage


class ChatRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_message(self, user_id: int, role: str, content: str) -> ChatMessage:
        message = ChatMessage(user_id=user_id, role=role, content=content)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_recent_messages(self, user_id: int, limit: int = 5) -> list[ChatMessage]:
        messages = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        return list(reversed(messages))

    def create_usage_event(
        self,
        user_id: int,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        estimated_cost_usd: float,
    ) -> ChatUsage:
        usage = ChatUsage(
            user_id=user_id,
            model=model or "unknown",
            input_tokens=max(0, int(input_tokens)),
            output_tokens=max(0, int(output_tokens)),
            total_tokens=max(0, int(total_tokens)),
            estimated_cost_usd=max(0.0, float(estimated_cost_usd)),
        )
        self.db.add(usage)
        self.db.commit()
        self.db.refresh(usage)
        return usage

    def get_usage_summary(self, user_id: int | None = None) -> dict:
        query = self.db.query(
            func.coalesce(func.sum(ChatUsage.input_tokens), 0),
            func.coalesce(func.sum(ChatUsage.output_tokens), 0),
            func.coalesce(func.sum(ChatUsage.total_tokens), 0),
            func.coalesce(func.sum(ChatUsage.estimated_cost_usd), 0.0),
            func.count(ChatUsage.id),
        )
        if user_id is not None:
            query = query.filter(ChatUsage.user_id == user_id)

        input_tokens, output_tokens, total_tokens, estimated_cost_usd, records = query.one()
        return {
            "input_tokens": int(input_tokens or 0),
            "output_tokens": int(output_tokens or 0),
            "total_tokens": int(total_tokens or 0),
            "estimated_cost_usd": float(estimated_cost_usd or 0.0),
            "records": int(records or 0),
            "currency": "USD",
            "scope": "user" if user_id is not None else "system",
        }
