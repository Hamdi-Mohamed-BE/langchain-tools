from collections.abc import AsyncGenerator

from sqlalchemy.orm import Session

from app.ai.agent_tools import build_agent_tools
from app.ai.context_manager import ContextManager
from app.ai.llm_client import LLMClient, UsageStats
from app.core.config import settings
from app.repositories.chat_repo import ChatRepository
from app.schemas.chat import ChatContextMessage
from app.services.exercise_service import ExerciseService
from app.tools.db_tools import build_compact_workout_snapshot


class ChatService:
    # Approximate Gemini per-1M token pricing for a lightweight session estimate.
    _DEFAULT_INPUT_USD_PER_1M = 0.30
    _DEFAULT_OUTPUT_USD_PER_1M = 2.50

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = ChatRepository(db)
        self.context_manager = ContextManager(max_messages=5)
        self.llm = LLMClient()
        self.exercise_service = ExerciseService()

    async def handle_message(self, user_id: int, message: str) -> str:
        self.repo.create_message(user_id=user_id, role="user", content=message)

        recent = self.repo.get_recent_messages(user_id=user_id, limit=8)
        context_messages = [ChatContextMessage(role=m.role, content=m.content) for m in recent]
        trimmed = self.context_manager.trim_messages(context_messages)

        context_parts = self._build_optimized_context(user_id=user_id, message=message, trimmed_messages=trimmed)

        context = "\n".join(context_parts)
        tool_events: list[tuple[str, str]] = []

        def collect_tool_event(tool_name: str, detail: str) -> None:
            tool_events.append((tool_name, detail))

        tools = build_agent_tools(self.db, user_id, self.exercise_service, tool_logger=collect_tool_event)
        reply, _usage = await self.llm.generate_response_with_usage(
            user_message=message,
            context=context,
            tools=tools,
        )

        usage_event = self._build_usage_event(_usage)
        if usage_event:
            self.repo.create_usage_event(
                user_id=user_id,
                model=str(usage_event.get("model", "unknown")),
                input_tokens=int(usage_event.get("input_tokens", 0)),
                output_tokens=int(usage_event.get("output_tokens", 0)),
                total_tokens=int(usage_event.get("total_tokens", 0)),
                estimated_cost_usd=float(usage_event.get("estimated_cost_usd", 0.0)),
            )

        if tool_events:
            used = ", ".join(sorted({name for name, _ in tool_events}))
            reply = f"Tools used: {used}\n\n{reply}"

        self.repo.create_message(user_id=user_id, role="assistant", content=reply)
        return reply

    async def stream_message(self, user_id: int, message: str) -> AsyncGenerator[dict, None]:
        self.repo.create_message(user_id=user_id, role="user", content=message)

        recent = self.repo.get_recent_messages(user_id=user_id, limit=8)
        context_messages = [ChatContextMessage(role=m.role, content=m.content) for m in recent]
        trimmed = self.context_manager.trim_messages(context_messages)
        context_parts = self._build_optimized_context(user_id=user_id, message=message, trimmed_messages=trimmed)
        context = "\n".join(context_parts)
        tool_events: list[tuple[str, str]] = []

        def collect_tool_event(tool_name: str, detail: str) -> None:
            tool_events.append((tool_name, detail))

        tools = build_agent_tools(self.db, user_id, self.exercise_service, tool_logger=collect_tool_event)

        final, usage = await self.llm.generate_response_with_usage(
            user_message=message,
            context=context,
            tools=tools,
        )

        if tool_events:
            used = ", ".join(sorted({name for name, _ in tool_events}))
            final = f"Tools used: {used}\n\n{final}"

        for tool_name, detail in tool_events:
            yield {"type": "tool", "tool": tool_name, "text": detail}

        usage_event = self._build_usage_event(usage)
        if usage_event:
            self.repo.create_usage_event(
                user_id=user_id,
                model=str(usage_event.get("model", "unknown")),
                input_tokens=int(usage_event.get("input_tokens", 0)),
                output_tokens=int(usage_event.get("output_tokens", 0)),
                total_tokens=int(usage_event.get("total_tokens", 0)),
                estimated_cost_usd=float(usage_event.get("estimated_cost_usd", 0.0)),
            )
            yield usage_event

        assembled = []
        for token in final.split():
            text = token + " "
            assembled.append(text)
            yield {"type": "token", "text": text}

        full_response = "".join(assembled).strip()
        if full_response:
            self.repo.create_message(user_id=user_id, role="assistant", content=full_response)

    def _build_usage_event(self, usage: UsageStats | None) -> dict | None:
        if not usage:
            return None

        input_tokens = int(usage.get("input_tokens", 0))
        output_tokens = int(usage.get("output_tokens", 0))
        total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens))

        input_rate, output_rate = self._resolve_model_rates(settings.resolved_gemini_model)
        estimated_cost = ((input_tokens * input_rate) + (output_tokens * output_rate)) / 1_000_000

        return {
            "type": "usage",
            "model": settings.resolved_gemini_model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": round(estimated_cost, 6),
            "currency": "USD",
            "is_estimate": True,
        }

    def _resolve_model_rates(self, model_name: str) -> tuple[float, float]:
        normalized = (model_name or "").lower()
        if "2.5" in normalized and "flash" in normalized:
            return 0.30, 2.50
        if "2.0" in normalized and "flash" in normalized:
            return 0.10, 0.40
        return self._DEFAULT_INPUT_USD_PER_1M, self._DEFAULT_OUTPUT_USD_PER_1M

    def _build_optimized_context(
        self,
        user_id: int,
        message: str,
        trimmed_messages: list[ChatContextMessage],
    ) -> list[str]:
        context_parts = [f"{m.role}: {m.content}" for m in trimmed_messages]

        # Always include compact workout state so the assistant stays aware without verbose payloads.
        context_parts.append(build_compact_workout_snapshot(self.db, user_id))

        # Keep explicit instruction so the model knows that actions should go through tools.
        context_parts.append(
            "ToolPolicy: AI chooses exercise names for each session, then call lookup_youtube_shorts_exercises "
            "with those names to fetch videos before saving plan. Use generate_and_save_workout_plan for full plans. "
            "For updates, use modify_user_workout_plan with old exercise name + day + new exercise name; "
            "do not delete/regenerate whole plan unless user explicitly asks for full reset."
        )

        return context_parts
