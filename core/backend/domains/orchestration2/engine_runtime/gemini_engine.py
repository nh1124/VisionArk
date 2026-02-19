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

# ── Output guard constants ───────────────────────────────────────────
_REASONING_CHAR_LIMIT = 5000
_TEXT_CHAR_LIMIT = 15000  # guard for non-reasoning text output per part
_REPETITION_THRESHOLD = 3  # collapse after N identical/near-identical lines


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
                    max_output_tokens=opts.max_output_tokens,
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
                    "(%d turns, %d tool_calls, output=%d chars)",
                    run_id, elapsed, turn + 1, total_tool_calls,
                    len(output_text),
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
    def _guard_reasoning(text: str) -> str:
        """Apply output guards to reasoning text: truncation + repetition collapse."""
        original_len = len(text)

        # 1a. Collapse single-line repetition
        lines = text.splitlines()
        if len(lines) > _REPETITION_THRESHOLD:
            collapsed: list[str] = []
            streak_line: str | None = None
            streak_count = 0

            for line in lines:
                stripped = line.strip()
                if stripped == streak_line:
                    streak_count += 1
                else:
                    if streak_count >= _REPETITION_THRESHOLD:
                        collapsed.append(
                            f"(repeated {streak_count} times, collapsed)"
                        )
                    elif streak_line is not None:
                        for _ in range(streak_count - 1):
                            collapsed.append(streak_line)
                    collapsed.append(line)
                    streak_line = stripped
                    streak_count = 1

            # flush final streak
            if streak_count >= _REPETITION_THRESHOLD:
                collapsed.append(
                    f"(repeated {streak_count} times, collapsed)"
                )
            else:
                for _ in range(streak_count - 1):
                    collapsed.append(streak_line or "")

            text = "\n".join(collapsed)

        # 1b. Collapse multi-line block repetition
        # Split into paragraphs (blocks separated by blank lines) and
        # detect when the same block appears consecutively.
        blocks = text.split("\n\n")
        if len(blocks) > _REPETITION_THRESHOLD:
            deduped: list[str] = []
            prev_block: str | None = None
            block_repeat = 0

            for block in blocks:
                normalized = block.strip()
                if normalized == prev_block and normalized:
                    block_repeat += 1
                else:
                    if block_repeat >= _REPETITION_THRESHOLD:
                        deduped.append(
                            f"(block repeated {block_repeat} times, collapsed)"
                        )
                    elif prev_block is not None:
                        for _ in range(block_repeat - 1):
                            deduped.append(prev_block)
                    deduped.append(block)
                    prev_block = normalized
                    block_repeat = 1

            if block_repeat >= _REPETITION_THRESHOLD:
                deduped.append(
                    f"(block repeated {block_repeat} times, collapsed)"
                )
            else:
                for _ in range(block_repeat - 1):
                    deduped.append(prev_block or "")

            text = "\n\n".join(deduped)

        # 2. Truncate if over char limit
        if len(text) > _REASONING_CHAR_LIMIT:
            text = text[:_REASONING_CHAR_LIMIT] + "\n(reasoning truncated)"

        if len(text) < original_len:
            logger.debug(
                "Reasoning guard: %d -> %d chars", original_len, len(text)
            )

        return text

    @staticmethod
    def _guard_text(text: str) -> str:
        """Apply output guards to non-reasoning text: block repetition + truncation."""
        original_len = len(text)

        # 0. Collapse single-line repetition (e.g. "(continue)\n" repeated 100x)
        lines = text.splitlines()
        if len(lines) > _REPETITION_THRESHOLD:
            collapsed: list[str] = []
            streak_line: str | None = None
            streak_count = 0

            for line in lines:
                stripped = line.strip()
                if stripped == streak_line:
                    streak_count += 1
                else:
                    if streak_count >= _REPETITION_THRESHOLD:
                        collapsed.append(
                            f"(repeated {streak_count} times, collapsed)"
                        )
                    elif streak_line is not None:
                        for _ in range(streak_count - 1):
                            collapsed.append(streak_line)
                    collapsed.append(line)
                    streak_line = stripped
                    streak_count = 1

            # flush final streak
            if streak_count >= _REPETITION_THRESHOLD:
                collapsed.append(
                    f"(repeated {streak_count} times, collapsed)"
                )
            else:
                for _ in range(streak_count - 1):
                    collapsed.append(streak_line or "")

            text = "\n".join(collapsed)

        # 1. Collapse multi-line block repetition
        blocks = text.split("\n\n")
        if len(blocks) > _REPETITION_THRESHOLD:
            deduped: list[str] = []
            prev_block: str | None = None
            block_repeat = 0

            for block in blocks:
                normalized = block.strip()
                if normalized == prev_block and normalized:
                    block_repeat += 1
                else:
                    if block_repeat >= _REPETITION_THRESHOLD:
                        deduped.append(
                            f"(block repeated {block_repeat} times, collapsed)"
                        )
                    elif prev_block is not None:
                        for _ in range(block_repeat - 1):
                            deduped.append(prev_block)
                    deduped.append(block)
                    prev_block = normalized
                    block_repeat = 1

            if block_repeat >= _REPETITION_THRESHOLD:
                deduped.append(
                    f"(block repeated {block_repeat} times, collapsed)"
                )
            else:
                for _ in range(block_repeat - 1):
                    deduped.append(prev_block or "")

            text = "\n\n".join(deduped)

        # 2. Truncate if over char limit
        if len(text) > _TEXT_CHAR_LIMIT:
            logger.warning(
                "Text output guard: truncating %d -> %d chars",
                len(text), _TEXT_CHAR_LIMIT,
            )
            text = (
                text[:_TEXT_CHAR_LIMIT]
                + "\n\n(output truncated — exceeded safe limit)"
            )

        if len(text) < original_len:
            logger.debug(
                "Text guard: %d -> %d chars", original_len, len(text)
            )

        return text

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
                        content_str = p.text
                        # Apply output guards
                        if is_thought:
                            content_str = GeminiEngine._guard_reasoning(
                                content_str
                            )
                        else:
                            content_str = GeminiEngine._guard_text(
                                content_str
                            )
                        text_parts.append(content_str)
                        # Preserve as a typed SubMessage for traceability
                        submessages.append(SubMessage(
                            kind=(
                                SubMessageKind.REASONING
                                if is_thought
                                else SubMessageKind.TEXT
                            ),
                            content=content_str,
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
        """Ensure valid alternating turns for the Gemini API.

        Instead of merging consecutive same-role turns (which corrupts
        content boundaries between orchestration steps), insert a
        lightweight separator turn of the opposite role.
        """
        if not history:
            return history

        # Use a single space — invisible to the model and unlikely to be
        # echoed back as a repetition pattern (unlike "(continue)" which
        # the model would treat as content and repeat in a loop).
        _SEP = types.Part.from_text(text=" ")

        result: list[types.Content] = [history[0]]
        for turn in history[1:]:
            if turn.role == result[-1].role:
                # Insert a separator of the opposite role
                sep_role = "user" if turn.role == "model" else "model"
                result.append(
                    types.Content(role=sep_role, parts=[_SEP])
                )
            result.append(turn)

        if result and result[0].role != "user":
            result.insert(
                0,
                types.Content(
                    role="user",
                    parts=[_SEP],
                ),
            )
        return result

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
