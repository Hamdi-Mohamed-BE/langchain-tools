from collections import deque

from app.schemas.chat import ChatContextMessage


class ContextManager:
    def __init__(self, max_messages: int = 5) -> None:
        self.max_messages = max_messages

    def trim_messages(self, messages: list[ChatContextMessage]) -> list[ChatContextMessage]:
        recent = deque(messages, maxlen=self.max_messages)
        return list(recent)

    def summarize_old_messages(self, messages: list[ChatContextMessage]) -> str:
        if len(messages) <= self.max_messages:
            return ""
        older = messages[:-self.max_messages]
        return " | ".join([m.content[:60] for m in older])
