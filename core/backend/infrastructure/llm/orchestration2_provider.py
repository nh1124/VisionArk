"""LLMProvider implementation for orchestration2.

Implements the orchestration2 LLMProvider protocol using the Google Gemini SDK.
Converts v2 Message/SubMessage types to Gemini's native format — no legacy types.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from google.genai import Client, types

from domains.orchestration2.engine.interfaces.llm_provider import LLMProvider
from domains.orchestration2.engine.models.common import MessageRole, SubMessageKind
from domains.orchestration2.engine.models.execution import LLMResponse
from domains.orchestration2.engine.models.message import Message, SubMessage, ToolCallRef

logger = logging.getLogger(__name__)


class GeminiLLMProvider:
    """Implements orchestration2 LLMProvider using the Google Gemini SDK.

    Accepts orchestration2 v2 Message objects directly and converts them
    to Gemini's native Content format. Returns LLMResponse.
    """

    def __init__(
        self,
        api_key: str,
        preferred_model: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = preferred_model or "gemini-3.1-pro-preview"
        self._client = Client(
            api_key=api_key,
            http_options={"api_version": "v1alpha", "timeout": 600000},
        )

    async def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse:
        """Generate a completion from Gemini using v2 Messages."""
        model_name = model or self._model

        # 1. Convert v2 messages → Gemini Content
        history = self._prepare_history(messages)

        # 2. System instruction
        system_content = self._make_system_instruction(system)

        # 3. Tools
        gemini_tools = self._convert_tools(tools) if tools else None

        # 4. Config
        config = types.GenerateContentConfig(
            temperature=1.0,
            tools=gemini_tools,
            system_instruction=system_content,
        )
        if gemini_tools:
            config.tool_config = types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(mode="AUTO")
            )

        # 5. Call Gemini
        try:
            t0 = time.time()
            logger.info(
                "[orchestration2:Gemini] Calling model=%s history=%d tools=%d",
                model_name,
                len(history),
                len(tools) if tools else 0,
            )
            response = await self._client.aio.models.generate_content(
                model=model_name,
                contents=history,
                config=config,
            )
            elapsed = time.time() - t0
            logger.info("[orchestration2:Gemini] Done in %.2fs", elapsed)
        except Exception:
            logger.exception("[orchestration2:Gemini] Generation error")
            raise

        # 6. Parse response → LLMResponse
        if (
            not response.candidates
            or not response.candidates[0].content
            or not response.candidates[0].content.parts
        ):
            return LLMResponse(content="", tool_calls=[], finish_reason="stop")

        parts = response.candidates[0].content.parts
        text_parts = [p.text for p in parts if p.text]
        content = "".join(text_parts).strip()

        tool_calls: list[dict[str, Any]] = []
        for p in parts:
            if p.function_call:
                tc_entry: dict[str, Any] = {
                    "name": p.function_call.name,
                    "arguments": dict(p.function_call.args or {}),
                    "call_id": str(uuid.uuid4()),
                }
                # Capture Gemini-specific metadata for faithful replay
                provider_data: dict[str, Any] = {}
                if getattr(p, "thought_signature", None):
                    provider_data["thought_signature"] = p.thought_signature
                if getattr(p, "thought", None) is not None:
                    provider_data["thought"] = p.thought
                if provider_data:
                    tc_entry["provider_data"] = provider_data
                tool_calls.append(tc_entry)

        finish_reason = "tool_calls" if tool_calls else "stop"

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            finish_reason=finish_reason,
        )

    # ── Internal helpers ──────────────────────────────────────────────

    def _make_system_instruction(
        self, instruction: str | None
    ) -> types.Content | None:
        if not instruction:
            return None
        return types.Content(
            role="system", parts=[types.Part.from_text(text=instruction)]
        )

    def _prepare_history(self, messages: list[Message]) -> list[types.Content]:
        """Convert v2 Messages to Gemini Content objects.

        Also normalises the result for Gemini-specific constraints:
        - Conversation must start with a ``user`` turn.
        - ``model`` (function_call) turns must come immediately after a
          ``user`` or ``tool`` turn.
        - Adjacent turns with the same role are merged into one Content.
        """
        raw: list[types.Content] = []

        for msg in messages:
            role_val = msg.role.value

            if role_val == MessageRole.SYSTEM.value:
                raw.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_text(
                                text=f"**[SYSTEM NOTIFICATION]**:\n{msg.content}"
                            )
                        ],
                    )
                )

            elif role_val == MessageRole.USER.value:
                parts = []
                if msg.content:
                    parts.append(types.Part.from_text(text=msg.content))
                if parts:
                    raw.append(types.Content(role="user", parts=parts))

            elif role_val == MessageRole.ASSISTANT.value:
                if msg.submessages:
                    self._convert_assistant_submessages(msg.submessages, raw)
                elif msg.content:
                    raw.append(
                        types.Content(
                            role="model",
                            parts=[types.Part.from_text(text=msg.content)],
                        )
                    )

            elif role_val == MessageRole.TOOL.value:
                # Tool result messages — convert submessages
                tool_parts = []
                for sub in msg.submessages:
                    if sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                        tool_parts.append(
                            types.Part.from_function_response(
                                name=sub.tool_call.tool_name,
                                response={"result": sub.content},
                            )
                        )
                if tool_parts:
                    raw.append(types.Content(role="tool", parts=tool_parts))

        return self._normalise_turns(raw)

    @staticmethod
    def _normalise_turns(
        history: list[types.Content],
    ) -> list[types.Content]:
        """Ensure Gemini turn-ordering constraints are satisfied.

        1. Merge adjacent turns that share the same role.
        2. Guarantee the conversation starts with a ``user`` turn.
        """
        if not history:
            return history

        # Merge adjacent same-role turns
        merged: list[types.Content] = [history[0]]
        for turn in history[1:]:
            if turn.role == merged[-1].role:
                merged[-1] = types.Content(
                    role=turn.role,
                    parts=list(merged[-1].parts or []) + list(turn.parts or []),
                )
            else:
                merged.append(turn)

        # Ensure conversation starts with a user turn
        if merged and merged[0].role != "user":
            merged.insert(
                0,
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="(continue)")],
                ),
            )

        return merged

    def _convert_assistant_submessages(
        self,
        submessages: list[SubMessage],
        history: list[types.Content],
    ) -> None:
        """Convert assistant SubMessages into Gemini model + tool turns."""
        model_parts: list[types.Part] = []
        pending_tool_calls: list[SubMessage] = []

        for sub in submessages:
            if sub.kind == SubMessageKind.TEXT or sub.kind == SubMessageKind.REASONING:
                if sub.content:
                    model_parts.append(types.Part.from_text(text=sub.content))

            elif sub.kind == SubMessageKind.TOOL_CALL and sub.tool_call:
                fc_part = types.Part.from_function_call(
                    name=sub.tool_call.tool_name,
                    args=sub.tool_call.arguments or {},
                )
                # Restore Gemini-specific metadata (thought_signature) so
                # replayed function_call parts pass Gemini's validation.
                pdata = sub.tool_call.provider_data
                if pdata.get("thought_signature"):
                    fc_part.thought_signature = pdata["thought_signature"]
                if pdata.get("thought") is not None:
                    fc_part.thought = pdata["thought"]
                model_parts.append(fc_part)
                pending_tool_calls.append(sub)

            elif sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                # Flush model parts before tool response
                if model_parts:
                    history.append(
                        types.Content(role="model", parts=model_parts)
                    )
                    model_parts = []

                # Tool response turn
                history.append(
                    types.Content(
                        role="tool",
                        parts=[
                            types.Part.from_function_response(
                                name=sub.tool_call.tool_name,
                                response={"result": sub.content},
                            )
                        ],
                    )
                )

        # Flush remaining model parts
        if model_parts:
            history.append(types.Content(role="model", parts=model_parts))

    def _convert_tools(
        self, tool_defs: list[dict[str, Any]]
    ) -> list[types.Tool]:
        """Convert orchestration2 tool definitions to Gemini format."""
        declarations = []
        for defn in tool_defs:
            params = defn.get("parameters", {})
            schema = self._convert_schema(params)
            declarations.append(
                types.FunctionDeclaration(
                    name=defn["name"],
                    description=defn.get("description", ""),
                    parameters=schema,
                )
            )
        return [types.Tool(function_declarations=declarations)]

    def _convert_schema(self, schema: dict[str, Any]) -> types.Schema:
        """Recursively convert JSON schema to Gemini Schema."""
        prop_type = schema.get("type", "string").upper()
        args: dict[str, Any] = {
            "type": prop_type,
            "description": schema.get("description", ""),
        }

        if prop_type == "ARRAY" and "items" in schema:
            args["items"] = self._convert_schema(schema["items"])

        if prop_type == "OBJECT" and "properties" in schema:
            args["properties"] = {
                k: self._convert_schema(v)
                for k, v in schema["properties"].items()
            }
            if "required" in schema:
                args["required"] = schema["required"]

        if "enum" in schema:
            args["enum"] = schema["enum"]

        return types.Schema(**args)
