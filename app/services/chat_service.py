import asyncio
import re
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
    _SECRET_PATTERNS = [
        re.compile(r"(?i)(api[_-]?key|token|authorization|bearer|secret|password)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.]{8,})['\"]?"),
        re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"),
        re.compile(r"\bsk-[A-Za-z0-9]{16,}\b"),
        re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
    ]

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
        raw_reply, _usage = await self.llm.generate_response_with_usage(
            user_message=message,
            context=context,
            tools=tools,
        )
        reply = self._sanitize_assistant_text(raw_reply)

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

        # Use non-streaming invoke so the full response (including tool calls)
        # is resolved internally.  We then sanitize once and drip-feed the clean
        # text to the client to keep the typing animation alive.
        raw_reply, _usage = await self.llm.generate_response_with_usage(
            user_message=message,
            context=context,
            tools=tools,
        )

        full_response = self._sanitize_assistant_text(raw_reply)
        if full_response:
            # Drip-feed the sanitized text in small chunks for a typing effect.
            chunk_size = 12
            for i in range(0, len(full_response), chunk_size):
                yield {"type": "token", "text": full_response[i : i + chunk_size]}
                await asyncio.sleep(0.02)
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
            "ToolPolicy: For new plans, call generate_and_save_workout_plan. That tool forces structured output "
            "for days and exercises, then enriches generated exercises with YouTube videos, then saves to DB. "
            "If any exercise video_url is null at save time, the system auto-fetches the first matching YouTube video by exercise name. "
            "Use modify_user_workout_plan for precise exercise swaps. "
            "Use refresh_exercise_videos when the user asks to refresh, update, or fix exercise videos. "
            "When listing exercises from the saved plan, always include the video_url for each exercise as a YouTube link so the user can watch. "
            "Do not delete/regenerate the entire plan unless the user explicitly asks for a full reset."
        )

        context_parts.append(
            "SafetyPolicy: Never reveal API keys, bearer tokens, auth headers, raw JSON payloads, or internal tool traces. "
            "Return user-facing plain text only."
        )

        return context_parts

    def _sanitize_assistant_text(self, text: str) -> str:
        sanitized = (text or "").strip()
        if not sanitized:
            return ""

        # Remove fenced blocks to avoid exposing raw payloads/tool traces.
        sanitized = re.sub(r"```[\s\S]*?```", "", sanitized)

        # Remove likely JSON objects/arrays from output while keeping narrative text.
        sanitized = re.sub(r"\{\s*\"[\s\S]*?\}\s*", "", sanitized)
        sanitized = re.sub(r"\[\s*\{[\s\S]*?\}\s*\]\s*", "", sanitized)

        # Remove residual JSON-like noise left after stripping (commas, brackets, quoted keys, etc.).
        sanitized = re.sub(r'"[a-z_]+"\s*:\s*"[^"]*"', "", sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'"[a-z_]+"\s*:\s*\d+', "", sanitized, flags=re.IGNORECASE)
        # Empty bracket/brace pairs and clusters.
        sanitized = re.sub(r"[\[\]{}]{2,}", "", sanitized)
        sanitized = re.sub(r"\[\]", "", sanitized)
        # Lines that are only structural characters (commas, brackets, braces, whitespace).
        sanitized = re.sub(r"(?m)^[\s,\[\]{}]+$", "", sanitized)
        # Inline runs of commas/brackets that survived (e.g. ",,,,,").
        sanitized = re.sub(r"[,\s]*[\[\]{}][,\s\[\]{}]*", lambda m: "" if not any(c.isalpha() for c in m.group()) else m.group(), sanitized)

        # Redact token-like secrets and credentials.
        for pattern in self._SECRET_PATTERNS:
            sanitized = pattern.sub("[REDACTED]", sanitized)

        # Remove lines that look like tool internal status/protocol dumps.
        kept_lines: list[str] = []
        for line in sanitized.splitlines():
            lowered = line.casefold().strip()
            if lowered.startswith("tools used:"):
                continue
            if lowered.startswith("toolpolicy:"):
                continue
            if lowered.startswith("safetypolicy:"):
                continue
            if lowered.startswith("context:"):
                continue
            # Skip lines that became empty or only punctuation after stripping.
            stripped = re.sub(r"[\s,.:;]+", "", lowered)
            if not stripped:
                continue
            kept_lines.append(line)

        collapsed = "\n".join(kept_lines).strip()
        collapsed = re.sub(r"\n{3,}", "\n\n", collapsed)
        return collapsed or "I generated your plan successfully."
