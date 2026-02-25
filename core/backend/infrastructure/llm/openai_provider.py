"""LLMProvider implementation using the OpenAI API.

Implements the orchestration2 LLMProvider protocol using the OpenAI Python SDK.
Converts v2 Message/SubMessage types to OpenAI's chat format.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from openai import AsyncOpenAI

from domains.orchestration2.engine.interfaces.llm_provider import LLMProvider
from domains.orchestration2.engine.models.common import MessageRole, SubMessageKind
from domains.orchestration2.engine.models.execution import LLMResponse
from domains.orchestration2.engine.models.message import Message, SubMessage, ToolCallRef

logger = logging.getLogger(__name__)


class OpenAILLMProvider:
    """Implements orchestration2 LLMProvider using the OpenAI SDK."""

    def __init__(
        self,
        api_key: str,
        preferred_model: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = preferred_model or "gpt-4.1-mini"
        self._client = AsyncOpenAI(api_key=api_key, timeout=600.0)

    async def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate a completion from OpenAI using v2 Messages."""
        model_name = model or self._model

        # 1. Convert v2 messages → OpenAI format
        oai_messages = self._prepare_messages(messages, system)

        # 2. Tools
        oai_tools = self._convert_tools(tools) if tools else None

        # 3. Call OpenAI
        try:
            t0 = time.time()
            logger.info(
                "[orchestration2:OpenAI] Calling model=%s messages=%d tools=%d",
                model_name, len(oai_messages), len(tools) if tools else 0,
            )
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": oai_messages,
                "temperature": 0.2,
            }
            if oai_tools:
                kwargs["tools"] = oai_tools
                kwargs["tool_choice"] = "auto"

            response = await self._client.chat.completions.create(**kwargs)
            elapsed = time.time() - t0
            logger.info("[orchestration2:OpenAI] Done in %.2fs", elapsed)
        except Exception:
            logger.exception("[orchestration2:OpenAI] Generation error")
            raise

        # 4. Parse response → LLMResponse
        choice = response.choices[0] if response.choices else None
        if not choice or not choice.message:
            return LLMResponse(content="", tool_calls=[], finish_reason="stop")

        msg = choice.message
        content = msg.content or ""

        tool_calls: list[dict[str, Any]] = []
        if msg.tool_calls:
            import json
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                except json.JSONDecodeError:
                    args = {"raw": tc.function.arguments}
                tool_calls.append({
                    "name": tc.function.name,
                    "arguments": args,
                    "call_id": tc.id or str(uuid.uuid4()),
                })

        finish_reason = "tool_calls" if tool_calls else "stop"
        return LLMResponse(content=content, tool_calls=tool_calls, finish_reason=finish_reason)

    # ── Internal helpers ──────────────────────────────────────────────

    def _prepare_messages(
        self, messages: list[Message], system: str | None
    ) -> list[dict[str, Any]]:
        """Convert v2 Messages to OpenAI chat messages."""
        result: list[dict[str, Any]] = []
        if system:
            result.append({"role": "system", "content": system})

        for msg in messages:
            role_val = msg.role.value

            if role_val == MessageRole.SYSTEM.value:
                result.append({"role": "system", "content": msg.content})

            elif role_val == MessageRole.USER.value:
                if msg.content:
                    result.append({"role": "user", "content": msg.content})

            elif role_val == MessageRole.ASSISTANT.value:
                if msg.submessages:
                    # Process submessages for tool calls
                    text_parts = []
                    oai_tool_calls = []
                    for sub in msg.submessages:
                        if sub.kind in (SubMessageKind.TEXT, SubMessageKind.REASONING):
                            if sub.content:
                                text_parts.append(sub.content)
                        elif sub.kind == SubMessageKind.TOOL_CALL and sub.tool_call:
                            import json
                            oai_tool_calls.append({
                                "id": sub.tool_call.call_id or str(uuid.uuid4()),
                                "type": "function",
                                "function": {
                                    "name": sub.tool_call.tool_name,
                                    "arguments": json.dumps(sub.tool_call.arguments or {}),
                                },
                            })
                    assistant_msg: dict[str, Any] = {
                        "role": "assistant",
                        "content": "\n".join(text_parts) if text_parts else None,
                    }
                    if oai_tool_calls:
                        assistant_msg["tool_calls"] = oai_tool_calls
                    result.append(assistant_msg)
                elif msg.content:
                    result.append({"role": "assistant", "content": msg.content})

            elif role_val == MessageRole.TOOL.value:
                for sub in msg.submessages:
                    if sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                        result.append({
                            "role": "tool",
                            "tool_call_id": sub.tool_call.call_id or "",
                            "content": sub.content or "",
                        })

        return result

    @staticmethod
    def _convert_tools(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert orchestration2 tool definitions to OpenAI format."""
        oai_tools = []
        for defn in tool_defs:
            oai_tools.append({
                "type": "function",
                "function": {
                    "name": defn["name"],
                    "description": defn.get("description", ""),
                    "parameters": defn.get("parameters", {}),
                },
            })
        return oai_tools
