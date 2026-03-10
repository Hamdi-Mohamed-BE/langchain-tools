from collections.abc import AsyncGenerator
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings
from app.schemas.workout import WorkoutPlanDraft


class LLMClient:
    def __init__(self) -> None:
        self.llm = ChatGoogleGenerativeAI(
            model=settings.resolved_gemini_model,
            google_api_key=settings.google_api_key,
            temperature=0.4,
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are FitCoach AI — a motivating, knowledgeable personal trainer. "
            "Speak in a friendly, encouraging tone with energy — use occasional emojis (💪🔥🏋️) "
            "but stay professional. Structure responses with clear headings and bullet points. "
            "When presenting workout plans, use numbered lists with exercise details. "
            "Give brief, actionable advice. Celebrate user progress. "
            "If tools are available, use them to execute user actions — never expose tool internals. "
            "Keep responses under 300 words unless the user asks for detail."
            "if user shares a plan always respect it and generate based on his thoughts"
        )

    async def generate_response(
        self,
        user_message: str,
        context: str = "",
        tools: list[BaseTool] | None = None,
    ) -> str:
        text, _usage = await self.generate_response_with_usage(
            user_message=user_message,
            context=context,
            tools=tools,
        )
        return text

    async def generate_response_with_usage(
        self,
        user_message: str,
        context: str = "",
        tools: list[BaseTool] | None = None,
    ) -> tuple[str, "UsageStats | None"]:
        system_prompt = self._system_prompt()
        messages = [HumanMessage(content=f"Context: {context}\n\nUser: {user_message}")]

        if not tools:
            base_messages = [SystemMessage(content=system_prompt), *messages]
            response = await self.llm.ainvoke(base_messages)
            return self._content_to_text(response.content), self._extract_usage_from_message(response)

        agent = create_agent(
            model=self.llm,
            tools=tools,
            system_prompt=system_prompt,
        )
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": f"Context: {context}\n\nUser: {user_message}"}]}
        )
        return self._extract_agent_text(result), self._extract_usage_from_agent_result(result)

    async def stream_response(
        self,
        user_message: str,
        context: str = "",
        tools: list[BaseTool] | None = None,
    ) -> AsyncGenerator[str, None]:
        if tools:
            system_prompt = self._system_prompt()
            agent = create_agent(
                model=self.llm,
                tools=tools,
                system_prompt=system_prompt,
            )

            async for event in agent.astream_events(
                {"messages": [{"role": "user", "content": f"Context: {context}\n\nUser: {user_message}"}]},
                version="v2",
            ):
                if event.get("event") != "on_chat_model_stream":
                    continue

                data = event.get("data")
                if not isinstance(data, dict):
                    continue

                chunk = data.get("chunk")

                # Skip chunks that are tool-call arguments (JSON noise).
                tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
                if tool_call_chunks:
                    continue
                tool_calls = getattr(chunk, "tool_calls", None)
                if tool_calls:
                    continue

                content = getattr(chunk, "content", "")
                text = self._content_to_text(content)
                if text:
                    yield text
            return

        messages = [
            SystemMessage(
                content=(
                    "You are an AI gym coach. Stream a practical response in short chunks."
                )
            ),
            HumanMessage(content=f"Context: {context}\n\nUser: {user_message}"),
        ]

        async for chunk in self.llm.astream(messages):
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                yield text

    def generate_structured_workout_plan(
        self,
        goal: str,
        days_per_week: int,
        context: str = "",
    ) -> WorkoutPlanDraft:
        planner = self.llm.with_structured_output(WorkoutPlanDraft)
        prompt = (
            "Create a personalized weekly workout plan. "
            "Return valid structured data only. "
            "Rules: include exactly the requested number of days; "
            "each day must contain distinct exercises; "
            "sets must be 1-8 and reps must be a compact range like 6-10 or 10-15."
        )
        message = (
            f"Goal: {goal}\n"
            f"Days per week: {days_per_week}\n"
            f"Context: {context or 'none'}"
        )
        result = planner.invoke(
            [
                SystemMessage(content=prompt),
                HumanMessage(content=message),
            ]
        )
        if isinstance(result, WorkoutPlanDraft):
            return result
        return WorkoutPlanDraft.model_validate(result)

    @staticmethod
    def _extract_agent_text(result: Any) -> str:
        messages = result.get("messages", []) if isinstance(result, dict) else []

        # Walk backwards to find the last AIMessage that is a plain text reply
        # (not a tool-call invocation).
        for msg in reversed(messages):
            if not isinstance(msg, AIMessage):
                continue
            # Skip messages that are tool-call requests (contain JSON args, not user text).
            if getattr(msg, "tool_calls", None):
                continue
            text = LLMClient._content_to_text(msg.content)
            if text.strip():
                return text

        output = result.get("output") if isinstance(result, dict) else None
        if output is not None:
            return str(output)
        return "I could not produce a response."

    @staticmethod
    def _extract_usage_from_agent_result(result: Any) -> "UsageStats | None":
        if isinstance(result, dict):
            messages = result.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage):
                    usage = LLMClient._extract_usage_from_message(msg)
                    if usage:
                        return usage
        return None

    @staticmethod
    def _extract_usage_from_message(message: Any) -> "UsageStats | None":
        usage = getattr(message, "usage_metadata", None)
        if isinstance(usage, dict):
            parsed = LLMClient._parse_usage_dict(usage)
            if parsed:
                return parsed

        response_meta = getattr(message, "response_metadata", None)
        if isinstance(response_meta, dict):
            token_usage = response_meta.get("token_usage")
            if isinstance(token_usage, dict):
                parsed = LLMClient._parse_usage_dict(token_usage)
                if parsed:
                    return parsed
        return None

    @staticmethod
    def _parse_usage_dict(raw: dict[str, Any]) -> "UsageStats | None":
        input_tokens = LLMClient._coerce_int(
            raw.get("input_tokens")
            or raw.get("prompt_tokens")
            or raw.get("prompt_token_count")
        )
        output_tokens = LLMClient._coerce_int(
            raw.get("output_tokens")
            or raw.get("completion_tokens")
            or raw.get("candidates_token_count")
        )
        total_tokens = LLMClient._coerce_int(
            raw.get("total_tokens")
            or raw.get("total_token_count")
        )
        if total_tokens == 0:
            total_tokens = input_tokens + output_tokens

        if input_tokens == 0 and output_tokens == 0 and total_tokens == 0:
            return None
        return UsageStats(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )

    @staticmethod
    def _coerce_int(value: Any) -> int:
        try:
            if value is None:
                return 0
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: list[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "".join(chunks).strip() or str(content)
        return str(content)


class UsageStats(TypedDict):
    input_tokens: int
    output_tokens: int
    total_tokens: int

