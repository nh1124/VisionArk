"""OpenAIEngine — LLMEngine implementation using the OpenAI SDK.

Provides the same multi-turn inference loop as GeminiEngine but targets
the OpenAI Chat Completions API.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from openai import AsyncOpenAI

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


class OpenAIEngine(LLMEngine):
    """Multi-turn inference engine using the OpenAI SDK."""

    def __init__(
        self,
        api_key: str,
        tool_registry: ToolRegistry,
        *,
        model: str | None = None,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key, timeout=1800.0)
        self._model = model or "gpt-4.1-mini"
        self._tools = tool_registry
        self._active_runs: dict[str, EngineRunStatus] = {}
        self._cancelled_runs: set[str] = set()

    # ── LLMEngine interface ──────────────────────────────────────────

    @property
    def kind(self) -> str:
        return "openai"

    async def run(
        self,
        run_input: EngineRunInput,
        options: RunOptions | None = None,
    ) -> EngineRunResult:
        """Execute a multi-turn inference loop using OpenAI."""
        opts = options or _DEFAULT_OPTIONS
        run_id = run_input.run_id

        self._active_runs[run_id] = EngineRunStatus(run_id=run_id, phase="running")

        # Convert orchestration2 Messages → OpenAI chat messages
        oai_messages = self._messages_to_oai(run_input.history, run_input.system_prompt)
        oai_tools = self._convert_tools(run_input.tool_defs) if run_input.tool_defs else None

        # Build execution context for tool dispatch
        ctx = self._build_execution_context(run_input)

        total_tool_calls = 0
        output_text = ""
        t0 = time.time()

        try:
            for turn in range(opts.max_turns):
                # Cooperative cancel check
                if run_id in self._cancelled_runs:
                    logger.info("[OpenAIEngine] run=%s cancelled at turn %d", run_id, turn)
                    self._cancelled_runs.discard(run_id)
                    return EngineRunResult(
                        run_id=run_id, status="cancelled",
                        history=self._oai_to_messages(oai_messages),
                        error="Cancelled by user",
                    )

                # Call OpenAI
                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "messages": oai_messages,
                    "temperature": 0.2,
                    "max_tokens": opts.max_output_tokens,
                }
                if oai_tools:
                    kwargs["tools"] = oai_tools
                    kwargs["tool_choice"] = "auto"

                logger.debug("[OpenAIEngine] run=%s turn=%d messages=%d", run_id, turn, len(oai_messages))
                response = await self._client.chat.completions.create(**kwargs)

                choice = response.choices[0] if response.choices else None
                if not choice or not choice.message:
                    output_text = ""
                    break

                msg = choice.message
                content_text = msg.content or ""

                if content_text:
                    progress_cb = run_input.metadata.get("progress_cb")
                    if progress_cb:
                        try:
                            await progress_cb(phase="Thinking", message="Generated thought", meta={
                                "type": "turn_text", "text": content_text
                            })
                        except Exception as e:
                            logger.error(f"progress_cb error: {e}")

                # Process tool calls
                if msg.tool_calls:
                    # Append assistant message to history
                    assistant_msg: dict[str, Any] = {"role": "assistant", "content": content_text or None}
                    tc_list = []
                    for tc in msg.tool_calls:
                        tc_list.append({
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        })
                    assistant_msg["tool_calls"] = tc_list
                    oai_messages.append(assistant_msg)

                    for tc in msg.tool_calls:
                        if total_tool_calls >= opts.max_tool_calls:
                            return EngineRunResult(
                                run_id=run_id, status="failed",
                                history=self._oai_to_messages(oai_messages),
                                error=f"Tool call limit ({opts.max_tool_calls}) exceeded",
                            )

                        try:
                            args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                        except json.JSONDecodeError:
                            args = {}

                        call_ref = ToolCallRef(
                            tool_name=tc.function.name,
                            call_id=tc.id or str(uuid.uuid4()),
                            arguments=args,
                        )

                        self._active_runs[run_id] = EngineRunStatus(
                            run_id=run_id, phase="running",
                            tool_calls=total_tool_calls,
                            tool_progress={"current_tool": tc.function.name},
                        )

                        progress_cb = run_input.metadata.get("progress_cb")
                        if progress_cb:
                            try:
                                await progress_cb(phase="Tool Execution", message=f"Running tool: {tc.function.name}", meta={
                                    "type": "tool_start", "tool": tc.function.name,
                                    "tool_call": {"name": tc.function.name, "args": args, "call_id": call_ref.call_id},
                                })
                            except Exception as e:
                                logger.error(f"progress_cb error: {e}")

                        try:
                            _def, tool_impl = self._tools.get(tc.function.name)
                            ctx.engine_kind = self.kind
                            result = await tool_impl.invoke(call_ref, ctx)
                        except Exception as exc:
                            logger.error("[OpenAIEngine] tool '%s' error: %s", tc.function.name, exc)
                            result = ToolResult(
                                tool_name=tc.function.name,
                                call_id=call_ref.call_id,
                                output=f"Error: {exc}",
                                error=str(exc),
                            )

                        if progress_cb:
                            try:
                                result_str = str(result.output)[:1000]
                                await progress_cb(phase="Tool Execution", message=f"Finished tool: {tc.function.name}", meta={
                                    "type": "tool_end", "call_id": call_ref.call_id,
                                    "tool": tc.function.name, "result": result_str,
                                    "is_success": not bool(result.error),
                                })
                            except Exception as e:
                                logger.error(f"progress_cb error: {e}")

                        oai_messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": str(result.output),
                        })
                        total_tool_calls += 1

                    continue  # Next turn

                # No tool calls → final text response
                output_text = content_text
                oai_messages.append({"role": "assistant", "content": output_text})

                elapsed = time.time() - t0
                logger.info(
                    "[OpenAIEngine] run=%s completed in %.2fs (%d turns, %d tool_calls)",
                    run_id, elapsed, turn + 1, total_tool_calls,
                )

                out_history = self._oai_to_messages(oai_messages)
                output_message = out_history[-1] if out_history else Message(
                    role=MessageRole.ASSISTANT, content=output_text,
                )
                return EngineRunResult(
                    run_id=run_id, status="completed",
                    output_message=output_message, history=out_history,
                )

            # Exhausted max_turns
            return EngineRunResult(
                run_id=run_id, status="failed",
                history=self._oai_to_messages(oai_messages),
                error=f"Turn limit ({opts.max_turns}) exceeded",
            )

        except Exception as exc:
            logger.exception("[OpenAIEngine] run=%s unexpected error", run_id)
            if opts.allow_partial_on_error:
                return EngineRunResult(
                    run_id=run_id, status="failed",
                    history=self._oai_to_messages(oai_messages),
                    error=str(exc),
                )
            raise

        finally:
            self._cancelled_runs.discard(run_id)
            status = self._active_runs.get(run_id)
            if status:
                status.phase = "completed"
                status.tool_calls = total_tool_calls

    def get_status(self, run_id: str) -> EngineRunStatus | None:
        return self._active_runs.get(run_id)

    def cancel(self, run_id: str) -> None:
        self._cancelled_runs.add(run_id)
        logger.info("[OpenAIEngine] cancel requested for run=%s", run_id)

    # ── Boundary converters ──────────────────────────────────────────

    @staticmethod
    def _messages_to_oai(messages: list[Message], system_prompt: str | None = None) -> list[dict[str, Any]]:
        """Convert orchestration2 Messages → OpenAI chat messages."""
        result: list[dict[str, Any]] = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})

        for msg in messages:
            role = msg.role.value

            if role == MessageRole.SYSTEM.value:
                result.append({"role": "system", "content": msg.content})

            elif role == MessageRole.USER.value:
                if msg.content:
                    result.append({"role": "user", "content": msg.content})

            elif role == MessageRole.ASSISTANT.value:
                if msg.submessages:
                    text_parts = []
                    oai_tool_calls = []
                    for sub in msg.submessages:
                        if sub.kind in (SubMessageKind.TEXT, SubMessageKind.REASONING):
                            if sub.content:
                                text_parts.append(sub.content)
                        elif sub.kind == SubMessageKind.TOOL_CALL and sub.tool_call:
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

            elif role == MessageRole.TOOL.value:
                for sub in msg.submessages:
                    if sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                        result.append({
                            "role": "tool",
                            "tool_call_id": sub.tool_call.call_id or "",
                            "content": sub.content or "",
                        })

        return result

    @staticmethod
    def _oai_to_messages(oai_messages: list[dict[str, Any]]) -> list[Message]:
        """Convert OpenAI chat messages → orchestration2 Messages."""
        result: list[Message] = []
        for msg in oai_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "") or ""

            if role == "system":
                result.append(Message(role=MessageRole.SYSTEM, content=content))
            elif role == "user":
                result.append(Message(role=MessageRole.USER, content=content))
            elif role == "assistant":
                submessages: list[SubMessage] = []
                if content:
                    submessages.append(SubMessage(kind=SubMessageKind.TEXT, content=content))
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    try:
                        args = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        args = {}
                    submessages.append(SubMessage(
                        kind=SubMessageKind.TOOL_CALL,
                        content="",
                        tool_call=ToolCallRef(
                            tool_name=func.get("name", ""),
                            call_id=tc.get("id", ""),
                            arguments=args,
                        ),
                    ))
                result.append(Message(
                    role=MessageRole.ASSISTANT,
                    content=content,
                    submessages=submessages,
                ))
            elif role == "tool":
                result.append(Message(
                    role=MessageRole.TOOL,
                    content=content,
                    submessages=[SubMessage(
                        kind=SubMessageKind.TOOL_RESULT,
                        content=content,
                        tool_call=ToolCallRef(
                            tool_name="",
                            call_id=msg.get("tool_call_id", ""),
                        ),
                    )],
                ))

        return result

    @staticmethod
    def _convert_tools(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert orchestration2 tool definitions to OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": defn["name"],
                    "description": defn.get("description", ""),
                    "parameters": defn.get("parameters", {}),
                },
            }
            for defn in tool_defs
        ]

    @staticmethod
    def _build_execution_context(run_input: EngineRunInput) -> ExecutionContext:
        return ExecutionContext(
            run_id=run_input.run_id,
            agent_def=run_input.metadata.get("agent_def"),
            run_context=run_input.metadata.get("run_context"),
            store=run_input.metadata.get("store"),
            metadata=run_input.metadata,
        )
