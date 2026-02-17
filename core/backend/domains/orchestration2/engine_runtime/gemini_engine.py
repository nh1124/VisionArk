"""GeminiEngine — LLMEngine implementation using Gemini SDK natively.

Operates on Gemini-native types (``Content``, ``Part``) internally.
orchestration2-typed ``Message`` objects are converted at the boundary
(input → native, native → output) so the multi-turn loop runs entirely
in the provider's native representation.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from google.genai import Client, types

from ..engine.models.common import MessageRole, SubMessageKind
from ..engine.models.execution import ExecutionContext, ToolResult
from ..engine.models.message import Message, SubMessage, ToolCallRef
from ..engine.interfaces.llm_engine import LLMEngine
from ..engine.models.engine_io import (
    EngineRunInput,
    EngineRunResult,
    EngineRunStatus,
    RunOptions,
)
from ..engine.registry.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

_DEFAULT_OPTIONS = RunOptions()


class GeminiEngine(LLMEngine):
    """Multi-turn inference engine using the Google Gemini SDK directly.

    The internal loop works with Gemini-native ``Content`` / ``Part``
    objects.  orchestration2 ``Message`` objects are only used at the
    in/out boundary of ``run()``.
    """

    def __init__(
        self,
        api_key: str,
        tool_registry: ToolRegistry,
        *,
        model: str | None = None,
    ) -> None:
        self._client = Client(
            api_key=api_key,
            http_options={"api_version": "v1alpha", "timeout": 600000},
        )
        self._model = model or "gemini-3-pro-preview"
        self._tools = tool_registry
        # In-memory run status tracking
        self._active_runs: dict[str, EngineRunStatus] = {}

    # ── LLMEngine interface ──────────────────────────────────────────

    @property
    def kind(self) -> str:
        return "gemini"

    async def run(
        self,
        run_input: EngineRunInput,
        options: RunOptions | None = None,
    ) -> EngineRunResult:
        """Execute a multi-turn inference loop using Gemini-native types."""
        opts = options or _DEFAULT_OPTIONS
        run_id = run_input.run_id

        self._active_runs[run_id] = EngineRunStatus(
            run_id=run_id, phase="running"
        )

        # ── Boundary: convert orchestration2 → native ────────────
        native_history = self._messages_to_contents(run_input.history)
        native_history = self._normalise_turns(native_history)
        system_content = self._make_system_instruction(run_input.system_prompt)
        gemini_tools = (
            self._convert_tools(run_input.tool_defs)
            if run_input.tool_defs
            else None
        )

        # Build execution context for tool dispatch
        ctx = self._build_execution_context(run_input)

        total_tool_calls = 0
        output_text: str = ""
        t0 = time.time()

        try:
            for turn in range(opts.max_turns):
                # ── 1. Call Gemini ────────────────────────────────
                config = types.GenerateContentConfig(
                    temperature=0.2,
                    tools=gemini_tools,
                    system_instruction=system_content,
                )
                if gemini_tools:
                    config.tool_config = types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode="AUTO"
                        )
                    )

                logger.debug(
                    "[GeminiEngine] run=%s turn=%d history=%d",
                    run_id, turn, len(native_history),
                )
                response = await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=native_history,
                    config=config,
                )

                # ── 2. Parse response parts ──────────────────────
                if (
                    not response.candidates
                    or not response.candidates[0].content
                    or not response.candidates[0].content.parts
                ):
                    # Empty response → treat as completion with empty text
                    output_text = ""
                    break

                response_content = response.candidates[0].content
                parts = response_content.parts

                text_parts = [p.text for p in parts if p.text]
                content_text = "".join(text_parts).strip()

                # Collect function_call parts
                fc_parts = [p for p in parts if p.function_call]

                # ── 3. Process function calls (native) ───────────
                if fc_parts:
                    # Append the model's response (with function_call parts)
                    # to native history as-is
                    native_history.append(response_content)

                    # Execute each tool and collect function_response parts
                    fr_parts: list[types.Part] = []

                    for fc_part in fc_parts:
                        if total_tool_calls >= opts.max_tool_calls:
                            logger.warning(
                                "[GeminiEngine] run=%s tool call limit (%d)",
                                run_id, opts.max_tool_calls,
                            )
                            return self._build_result(
                                run_id, "failed",
                                self._contents_to_messages(native_history),
                                error=f"Tool call limit ({opts.max_tool_calls}) exceeded",
                            )

                        fc = fc_part.function_call
                        call_id = str(uuid.uuid4())
                        call_ref = ToolCallRef(
                            tool_name=fc.name,
                            call_id=call_id,
                            arguments=dict(fc.args or {}),
                        )

                        # Update status
                        self._active_runs[run_id] = EngineRunStatus(
                            run_id=run_id,
                            phase="running",
                            tool_calls=total_tool_calls,
                            tool_progress={"current_tool": fc.name},
                        )

                        try:
                            # Direct tool invocation (no dispatcher)
                            _def, tool_impl = self._tools.get(fc.name)
                            
                            # Inject engine identity
                            ctx.engine_kind = self.kind
                            
                            result = await tool_impl.invoke(call_ref, ctx)

                        except Exception as exc:
                            logger.error(
                                "[GeminiEngine] tool '%s' error: %s",
                                fc.name, exc,
                            )
                            result = ToolResult(
                                tool_name=fc.name,
                                call_id=call_id,
                                output=f"Error: {exc}",
                                error=str(exc),
                            )

                        # Build native function_response Part
                        fr_parts.append(
                            types.Part.from_function_response(
                                name=fc.name,
                                response={"result": result.output},
                            )
                        )
                        # Inject engine-native parts (e.g. Gemini file URI)
                        if result.provider_parts:
                            for pp in result.provider_parts:
                                fr_parts.append(pp)
                        total_tool_calls += 1

                    # Append tool responses as a single "tool" turn
                    native_history.append(
                        types.Content(role="tool", parts=fr_parts)
                    )
                    continue  # → next turn

                # ── 4. No function calls → final text response ───
                output_text = content_text
                native_history.append(response_content)

                elapsed = time.time() - t0
                logger.info(
                    "[GeminiEngine] run=%s completed in %.2fs "
                    "(%d turns, %d tool_calls)",
                    run_id, elapsed, turn + 1, total_tool_calls,
                )

                # ── Boundary: convert native → orchestration2 ────
                out_history = self._contents_to_messages(native_history)
                # Use the last converted message — it contains the full
                # SubMessage chain (REASONING, TEXT, etc.)
                output_message = out_history[-1] if out_history else Message(
                    role=MessageRole.ASSISTANT,
                    content=output_text,
                )
                return EngineRunResult(
                    run_id=run_id,
                    status="completed",
                    output_message=output_message,
                    history=out_history,
                )

            # ── Exhausted max_turns ──────────────────────────────
            logger.warning(
                "[GeminiEngine] run=%s max_turns (%d) exhausted",
                run_id, opts.max_turns,
            )
            out_history = self._contents_to_messages(native_history)
            return EngineRunResult(
                run_id=run_id,
                status="failed",
                history=out_history,
                error=f"Turn limit ({opts.max_turns}) exceeded",
            )

        except Exception as exc:
            logger.exception("[GeminiEngine] run=%s unexpected error", run_id)
            if opts.allow_partial_on_error:
                out_history = self._contents_to_messages(native_history)
                return EngineRunResult(
                    run_id=run_id,
                    status="failed",
                    history=out_history,
                    error=str(exc),
                )
            raise

        finally:
            status = self._active_runs.get(run_id)
            if status:
                status.phase = "completed"
                status.tool_calls = total_tool_calls

    def get_status(self, run_id: str) -> EngineRunStatus | None:
        return self._active_runs.get(run_id)

    # ── Boundary converters: orchestration2 ↔ native ─────────────────

    @staticmethod
    def _messages_to_contents(messages: list[Message]) -> list[types.Content]:
        """Convert orchestration2 Messages → Gemini Content objects."""
        result: list[types.Content] = []

        for msg in messages:
            role = msg.role.value

            if role == MessageRole.SYSTEM.value:
                result.append(types.Content(
                    role="user",
                    parts=[types.Part.from_text(
                        text=f"**[SYSTEM NOTIFICATION]**:\n{msg.content}"
                    )],
                ))

            elif role == MessageRole.USER.value:
                if msg.content:
                    result.append(types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=msg.content)],
                    ))

            elif role == MessageRole.ASSISTANT.value:
                parts: list[types.Part] = []
                if msg.submessages:
                    for sub in msg.submessages:
                        if sub.kind in (SubMessageKind.TEXT, SubMessageKind.REASONING):
                            if sub.content:
                                parts.append(types.Part.from_text(text=sub.content))
                        elif sub.kind == SubMessageKind.TOOL_CALL and sub.tool_call:
                            fc = types.Part.from_function_call(
                                name=sub.tool_call.tool_name,
                                args=sub.tool_call.arguments or {},
                            )
                            pdata = sub.tool_call.provider_data
                            if pdata.get("thought_signature"):
                                fc.thought_signature = pdata["thought_signature"]
                            if pdata.get("thought") is not None:
                                fc.thought = pdata["thought"]
                            parts.append(fc)
                elif msg.content:
                    parts.append(types.Part.from_text(text=msg.content))
                if parts:
                    result.append(types.Content(role="model", parts=parts))

            elif role == MessageRole.TOOL.value:
                tool_parts: list[types.Part] = []
                for sub in msg.submessages:
                    if sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                        tool_parts.append(types.Part.from_function_response(
                            name=sub.tool_call.tool_name,
                            response={"result": sub.content},
                        ))
                if tool_parts:
                    result.append(types.Content(role="tool", parts=tool_parts))

        return result

    @staticmethod
    def _contents_to_messages(contents: list[types.Content]) -> list[Message]:
        """Convert Gemini Content objects → orchestration2 Messages.

        Performed at the output boundary so the orchestration layer
        receives its expected types.
        """
        result: list[Message] = []

        for content in contents:
            role = content.role
            parts = content.parts or []

            if role == "user":
                text = "".join(p.text for p in parts if p.text)
                result.append(Message(
                    role=MessageRole.USER,
                    content=text,
                ))

            elif role == "model":
                submessages: list[SubMessage] = []
                text_parts: list[str] = []

                for p in parts:
                    is_thought = getattr(p, "thought", None) is True

                    if p.text:
                        text_parts.append(p.text)
                        # Preserve as a typed SubMessage for traceability
                        submessages.append(SubMessage(
                            kind=(
                                SubMessageKind.REASONING
                                if is_thought
                                else SubMessageKind.TEXT
                            ),
                            content=p.text,
                        ))

                    if p.function_call:
                        # Capture provider-specific metadata
                        pdata: dict[str, Any] = {}
                        if getattr(p, "thought_signature", None):
                            pdata["thought_signature"] = p.thought_signature
                        if is_thought:
                            pdata["thought"] = True

                        submessages.append(SubMessage(
                            kind=SubMessageKind.TOOL_CALL,
                            content="",
                            tool_call=ToolCallRef(
                                tool_name=p.function_call.name,
                                call_id=str(uuid.uuid4()),
                                arguments=dict(p.function_call.args or {}),
                                provider_data=pdata,
                            ),
                        ))

                content_text = "".join(text_parts).strip()

                result.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=content_text,
                    submessages=submessages,
                ))

            elif role == "tool":
                tool_subs: list[SubMessage] = []
                for p in parts:
                    if p.function_response:
                        resp_content = ""
                        if p.function_response.response:
                            resp_content = str(
                                p.function_response.response.get("result", "")
                            )
                        tool_subs.append(SubMessage(
                            kind=SubMessageKind.TOOL_RESULT,
                            content=resp_content,
                            tool_call=ToolCallRef(
                                tool_name=p.function_response.name or "",
                                call_id=str(uuid.uuid4()),
                            ),
                        ))
                if tool_subs:
                    text = tool_subs[0].content if tool_subs else ""
                    result.append(Message(
                        role=MessageRole.TOOL,
                        content=text,
                        submessages=tool_subs,
                    ))

        return result

    # ── Native Gemini helpers ────────────────────────────────────────

    @staticmethod
    def _make_system_instruction(text: str | None) -> types.Content | None:
        if not text:
            return None
        return types.Content(
            role="system", parts=[types.Part.from_text(text=text)]
        )

    @staticmethod
    def _normalise_turns(
        history: list[types.Content],
    ) -> list[types.Content]:
        """Merge adjacent same-role turns and ensure user-first ordering."""
        if not history:
            return history

        merged: list[types.Content] = [history[0]]
        for turn in history[1:]:
            if turn.role == merged[-1].role:
                merged[-1] = types.Content(
                    role=turn.role,
                    parts=list(merged[-1].parts or []) + list(turn.parts or []),
                )
            else:
                merged.append(turn)

        if merged and merged[0].role != "user":
            merged.insert(
                0,
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text="(continue)")],
                ),
            )
        return merged

    @staticmethod
    def _convert_tools(
        tool_defs: list[dict[str, Any]],
    ) -> list[types.Tool]:
        """Convert orchestration2 tool definitions to Gemini format."""
        declarations = []
        for defn in tool_defs:
            params = defn.get("parameters", {})
            schema = GeminiEngine._convert_schema(params)
            declarations.append(
                types.FunctionDeclaration(
                    name=defn["name"],
                    description=defn.get("description", ""),
                    parameters=schema,
                )
            )
        return [types.Tool(function_declarations=declarations)]

    @staticmethod
    def _convert_schema(schema: dict[str, Any]) -> types.Schema:
        """Recursively convert JSON schema → Gemini Schema."""
        prop_type = schema.get("type", "string").upper()
        args: dict[str, Any] = {
            "type": prop_type,
            "description": schema.get("description", ""),
        }
        if prop_type == "ARRAY" and "items" in schema:
            args["items"] = GeminiEngine._convert_schema(schema["items"])
        if prop_type == "OBJECT" and "properties" in schema:
            args["properties"] = {
                k: GeminiEngine._convert_schema(v)
                for k, v in schema["properties"].items()
            }
            if "required" in schema:
                args["required"] = schema["required"]
        if "enum" in schema:
            args["enum"] = schema["enum"]
        return types.Schema(**args)

    @staticmethod
    def _build_execution_context(run_input: EngineRunInput) -> ExecutionContext:
        return ExecutionContext(
            run_id=run_input.run_id,
            agent_def=run_input.metadata.get("agent_def"),
            run_context=run_input.metadata.get("run_context"),
            store=run_input.metadata.get("store"),
            metadata=run_input.metadata,
        )
