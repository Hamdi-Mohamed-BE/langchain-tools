from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ChatMessageRequest(BaseModel):
    user_id: int
    message: str


class ChatMessageResponse(BaseModel):
    reply: str


class ChatMessageRead(BaseModel):
    role: str
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChatContextMessage(BaseModel):
    role: str
    content: str


class ChatUsageSummary(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    currency: str = "USD"
    records: int
    scope: str
