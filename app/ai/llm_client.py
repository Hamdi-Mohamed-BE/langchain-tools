from collections.abc import AsyncGenerator
from typing import Any, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings


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
            "You are an AI gym coach. Keep responses concise, safe, and actionable. "
            "If tools are available, use them whenever they help execute user actions. "
            "Prefer compact summaries over verbose details."
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
            # Execute tools through create_agent, then stream final text as chunks.
            final = await self.generate_response(user_message=user_message, context=context, tools=tools)
            for token in final.split():
                yield token + " "
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

    @staticmethod
    def _extract_agent_text(result: Any) -> str:
        messages = result.get("messages", []) if isinstance(result, dict) else []
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                return LLMClient._content_to_text(msg.content)

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

