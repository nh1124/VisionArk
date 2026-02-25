"""LLMProvider implementation using the Anthropic API.

Implements the orchestration2 LLMProvider protocol using the Anthropic Python SDK.
Converts v2 Message/SubMessage types to Anthropic's messages format.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from anthropic import AsyncAnthropic

from domains.orchestration2.engine.interfaces.llm_provider import LLMProvider
from domains.orchestration2.engine.models.common import MessageRole, SubMessageKind
from domains.orchestration2.engine.models.execution import LLMResponse
from domains.orchestration2.engine.models.message import Message, SubMessage, ToolCallRef

logger = logging.getLogger(__name__)


class AnthropicLLMProvider:
    """Implements orchestration2 LLMProvider using the Anthropic SDK."""

    def __init__(
        self,
        api_key: str,
        preferred_model: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = preferred_model or "claude-sonnet-4-20250514"
        self._client = AsyncAnthropic(api_key=api_key, timeout=600.0)

    async def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate a completion from Anthropic using v2 Messages."""
        model_name = model or self._model

        # 1. Convert v2 messages → Anthropic format
        ant_messages = self._prepare_messages(messages)

        # 2. Tools
        ant_tools = self._convert_tools(tools) if tools else None

        # 3. Call Anthropic
        try:
            t0 = time.time()
            logger.info(
                "[orchestration2:Anthropic] Calling model=%s messages=%d tools=%d",
                model_name, len(ant_messages), len(tools) if tools else 0,
            )
            kwargs: dict[str, Any] = {
                "model": model_name,
                "messages": ant_messages,
                "max_tokens": 8192,
                "temperature": 0.2,
            }
            if system:
                kwargs["system"] = system
            if ant_tools:
                kwargs["tools"] = ant_tools

            response = await self._client.messages.create(**kwargs)
            elapsed = time.time() - t0
            logger.info("[orchestration2:Anthropic] Done in %.2fs", elapsed)
        except Exception:
            logger.exception("[orchestration2:Anthropic] Generation error")
            raise

        # 4. Parse response → LLMResponse
        content_text = ""
        tool_calls: list[dict[str, Any]] = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "name": block.name,
                    "arguments": block.input if isinstance(block.input, dict) else {},
                    "call_id": block.id or str(uuid.uuid4()),
                })

        finish_reason = "tool_calls" if tool_calls else "stop"
        return LLMResponse(
            content=content_text.strip(),
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )

    # ── Internal helpers ──────────────────────────────────────────────

    def _prepare_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        """Convert v2 Messages to Anthropic messages format.

        Anthropic requires alternating user/assistant turns.
        System messages are passed separately via the `system` parameter.
        """
        result: list[dict[str, Any]] = []

        for msg in messages:
            role_val = msg.role.value

            if role_val == MessageRole.SYSTEM.value:
                # Anthropic system messages are handled separately;
                # inject as a user message for context if inline
                result.append({
                    "role": "user",
                    "content": f"[System Notification]: {msg.content}",
                })

            elif role_val == MessageRole.USER.value:
                if msg.content:
                    result.append({"role": "user", "content": msg.content})

            elif role_val == MessageRole.ASSISTANT.value:
                if msg.submessages:
                    content_blocks: list[dict[str, Any]] = []
                    for sub in msg.submessages:
                        if sub.kind in (SubMessageKind.TEXT, SubMessageKind.REASONING):
                            if sub.content:
                                content_blocks.append({"type": "text", "text": sub.content})
                        elif sub.kind == SubMessageKind.TOOL_CALL and sub.tool_call:
                            content_blocks.append({
                                "type": "tool_use",
                                "id": sub.tool_call.call_id or str(uuid.uuid4()),
                                "name": sub.tool_call.tool_name,
                                "input": sub.tool_call.arguments or {},
                            })
                    if content_blocks:
                        result.append({"role": "assistant", "content": content_blocks})
                elif msg.content:
                    result.append({"role": "assistant", "content": msg.content})

            elif role_val == MessageRole.TOOL.value:
                tool_results: list[dict[str, Any]] = []
                for sub in msg.submessages:
                    if sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": sub.tool_call.call_id or "",
                            "content": sub.content or "",
                        })
                if tool_results:
                    result.append({"role": "user", "content": tool_results})

        # Ensure conversation starts with a user turn
        if result and result[0]["role"] != "user":
            result.insert(0, {"role": "user", "content": "(continue)"})

        # Merge adjacent same-role messages
        merged: list[dict[str, Any]] = []
        for msg_item in result:
            if merged and merged[-1]["role"] == msg_item["role"]:
                prev_content = merged[-1]["content"]
                new_content = msg_item["content"]
                if isinstance(prev_content, str) and isinstance(new_content, str):
                    merged[-1]["content"] = prev_content + "\n" + new_content
                elif isinstance(prev_content, list) and isinstance(new_content, list):
                    merged[-1]["content"] = prev_content + new_content
                else:
                    # Mixed types — wrap string in text block
                    if isinstance(prev_content, str):
                        merged[-1]["content"] = [{"type": "text", "text": prev_content}]
                    if isinstance(new_content, str):
                        merged[-1]["content"].append({"type": "text", "text": new_content})
                    elif isinstance(new_content, list):
                        merged[-1]["content"].extend(new_content)
            else:
                merged.append(msg_item)

        return merged

    @staticmethod
    def _convert_tools(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert orchestration2 tool definitions to Anthropic format."""
        ant_tools = []
        for defn in tool_defs:
            ant_tools.append({
                "name": defn["name"],
                "description": defn.get("description", ""),
                "input_schema": defn.get("parameters", {"type": "object", "properties": {}}),
            })
        return ant_tools
