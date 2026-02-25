"""AnthropicEngine — LLMEngine implementation using the Anthropic SDK.

Provides the same multi-turn inference loop as GeminiEngine but targets
the Anthropic Messages API.
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from anthropic import AsyncAnthropic

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


class AnthropicEngine(LLMEngine):
    """Multi-turn inference engine using the Anthropic SDK."""

    def __init__(
        self,
        api_key: str,
        tool_registry: ToolRegistry,
        *,
        model: str | None = None,
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key, timeout=600.0)
        self._model = model or "claude-opus-4-6-20260220"
        self._tools = tool_registry
        self._active_runs: dict[str, EngineRunStatus] = {}
        self._cancelled_runs: set[str] = set()

    # ── LLMEngine interface ──────────────────────────────────────────

    @property
    def kind(self) -> str:
        return "anthropic"

    async def run(
        self,
        run_input: EngineRunInput,
        options: RunOptions | None = None,
    ) -> EngineRunResult:
        """Execute a multi-turn inference loop using Anthropic."""
        opts = options or _DEFAULT_OPTIONS
        run_id = run_input.run_id

        self._active_runs[run_id] = EngineRunStatus(run_id=run_id, phase="running")

        # Convert messages and prepare tools
        ant_messages = self._messages_to_ant(run_input.history)
        system_prompt = run_input.system_prompt or ""
        ant_tools = self._convert_tools(run_input.tool_defs) if run_input.tool_defs else None

        ctx = self._build_execution_context(run_input)

        total_tool_calls = 0
        output_text = ""
        t0 = time.time()

        try:
            for turn in range(opts.max_turns):
                if run_id in self._cancelled_runs:
                    logger.info("[AnthropicEngine] run=%s cancelled at turn %d", run_id, turn)
                    self._cancelled_runs.discard(run_id)
                    return EngineRunResult(
                        run_id=run_id, status="cancelled",
                        history=self._ant_to_messages(ant_messages, system_prompt),
                        error="Cancelled by user",
                    )

                kwargs: dict[str, Any] = {
                    "model": self._model,
                    "messages": ant_messages,
                    "max_tokens": opts.max_output_tokens or 8192,
                    "temperature": 0.2,
                }
                if system_prompt:
                    kwargs["system"] = system_prompt
                if ant_tools:
                    kwargs["tools"] = ant_tools

                logger.debug("[AnthropicEngine] run=%s turn=%d messages=%d", run_id, turn, len(ant_messages))
                response = await self._client.messages.create(**kwargs)

                # Parse response blocks
                text_parts = []
                tool_use_blocks = []
                for block in response.content:
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_use_blocks.append(block)

                content_text = "\n".join(text_parts).strip()

                if content_text:
                    progress_cb = run_input.metadata.get("progress_cb")
                    if progress_cb:
                        try:
                            await progress_cb(phase="Thinking", message="Generated thought", meta={
                                "type": "turn_text", "text": content_text
                            })
                        except Exception as e:
                            logger.error(f"progress_cb error: {e}")

                # Process tool use
                if tool_use_blocks:
                    # Append assistant message with content blocks
                    assistant_content: list[dict[str, Any]] = []
                    if content_text:
                        assistant_content.append({"type": "text", "text": content_text})
                    for tb in tool_use_blocks:
                        assistant_content.append({
                            "type": "tool_use",
                            "id": tb.id,
                            "name": tb.name,
                            "input": tb.input if isinstance(tb.input, dict) else {},
                        })
                    ant_messages.append({"role": "assistant", "content": assistant_content})

                    # Execute tools and collect results
                    tool_results: list[dict[str, Any]] = []
                    for tb in tool_use_blocks:
                        if total_tool_calls >= opts.max_tool_calls:
                            return EngineRunResult(
                                run_id=run_id, status="failed",
                                history=self._ant_to_messages(ant_messages, system_prompt),
                                error=f"Tool call limit ({opts.max_tool_calls}) exceeded",
                            )

                        args = tb.input if isinstance(tb.input, dict) else {}
                        call_ref = ToolCallRef(
                            tool_name=tb.name,
                            call_id=tb.id or str(uuid.uuid4()),
                            arguments=args,
                        )

                        self._active_runs[run_id] = EngineRunStatus(
                            run_id=run_id, phase="running",
                            tool_calls=total_tool_calls,
                            tool_progress={"current_tool": tb.name},
                        )

                        progress_cb = run_input.metadata.get("progress_cb")
                        if progress_cb:
                            try:
                                await progress_cb(phase="Tool Execution", message=f"Running tool: {tb.name}", meta={
                                    "type": "tool_start", "tool": tb.name,
                                    "tool_call": {"name": tb.name, "args": args, "call_id": call_ref.call_id},
                                })
                            except Exception as e:
                                logger.error(f"progress_cb error: {e}")

                        try:
                            _def, tool_impl = self._tools.get(tb.name)
                            ctx.engine_kind = self.kind
                            result = await tool_impl.invoke(call_ref, ctx)
                        except Exception as exc:
                            logger.error("[AnthropicEngine] tool '%s' error: %s", tb.name, exc)
                            result = ToolResult(
                                tool_name=tb.name,
                                call_id=call_ref.call_id,
                                output=f"Error: {exc}",
                                error=str(exc),
                            )

                        if progress_cb:
                            try:
                                result_str = str(result.output)[:1000]
                                await progress_cb(phase="Tool Execution", message=f"Finished tool: {tb.name}", meta={
                                    "type": "tool_end", "call_id": call_ref.call_id,
                                    "tool": tb.name, "result": result_str,
                                    "is_success": not bool(result.error),
                                })
                            except Exception as e:
                                logger.error(f"progress_cb error: {e}")

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": tb.id,
                            "content": str(result.output),
                        })
                        total_tool_calls += 1

                    # Add tool results as user message
                    ant_messages.append({"role": "user", "content": tool_results})
                    continue  # Next turn

                # No tool calls → final text response
                output_text = content_text
                ant_messages.append({"role": "assistant", "content": output_text})

                elapsed = time.time() - t0
                logger.info(
                    "[AnthropicEngine] run=%s completed in %.2fs (%d turns, %d tool_calls)",
                    run_id, elapsed, turn + 1, total_tool_calls,
                )

                out_history = self._ant_to_messages(ant_messages, system_prompt)
                output_message = out_history[-1] if out_history else Message(
                    role=MessageRole.ASSISTANT, content=output_text,
                )
                return EngineRunResult(
                    run_id=run_id, status="completed",
                    output_message=output_message, history=out_history,
                )

            return EngineRunResult(
                run_id=run_id, status="failed",
                history=self._ant_to_messages(ant_messages, system_prompt),
                error=f"Turn limit ({opts.max_turns}) exceeded",
            )

        except Exception as exc:
            logger.exception("[AnthropicEngine] run=%s unexpected error", run_id)
            if opts.allow_partial_on_error:
                return EngineRunResult(
                    run_id=run_id, status="failed",
                    history=self._ant_to_messages(ant_messages, system_prompt),
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
        logger.info("[AnthropicEngine] cancel requested for run=%s", run_id)

    # ── Boundary converters ──────────────────────────────────────────

    @staticmethod
    def _messages_to_ant(messages: list[Message]) -> list[dict[str, Any]]:
        """Convert orchestration2 Messages → Anthropic messages."""
        result: list[dict[str, Any]] = []

        for msg in messages:
            role = msg.role.value

            if role == MessageRole.SYSTEM.value:
                result.append({"role": "user", "content": f"[System]: {msg.content}"})

            elif role == MessageRole.USER.value:
                if msg.content:
                    result.append({"role": "user", "content": msg.content})

            elif role == MessageRole.ASSISTANT.value:
                if msg.submessages:
                    blocks: list[dict[str, Any]] = []
                    for sub in msg.submessages:
                        if sub.kind in (SubMessageKind.TEXT, SubMessageKind.REASONING):
                            if sub.content:
                                blocks.append({"type": "text", "text": sub.content})
                        elif sub.kind == SubMessageKind.TOOL_CALL and sub.tool_call:
                            blocks.append({
                                "type": "tool_use",
                                "id": sub.tool_call.call_id or str(uuid.uuid4()),
                                "name": sub.tool_call.tool_name,
                                "input": sub.tool_call.arguments or {},
                            })
                    if blocks:
                        result.append({"role": "assistant", "content": blocks})
                elif msg.content:
                    result.append({"role": "assistant", "content": msg.content})

            elif role == MessageRole.TOOL.value:
                tool_results = []
                for sub in msg.submessages:
                    if sub.kind == SubMessageKind.TOOL_RESULT and sub.tool_call:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": sub.tool_call.call_id or "",
                            "content": sub.content or "",
                        })
                if tool_results:
                    result.append({"role": "user", "content": tool_results})

        # Ensure starts with user
        if result and result[0].get("role") != "user":
            result.insert(0, {"role": "user", "content": "(continue)"})

        # Merge adjacent same-role
        merged: list[dict[str, Any]] = []
        for item in result:
            if merged and merged[-1].get("role") == item.get("role"):
                prev = merged[-1]["content"]
                curr = item["content"]
                if isinstance(prev, str) and isinstance(curr, str):
                    merged[-1]["content"] = prev + "\n" + curr
                elif isinstance(prev, list) and isinstance(curr, list):
                    merged[-1]["content"] = prev + curr
                else:
                    merged.append(item)
            else:
                merged.append(item)

        return merged

    @staticmethod
    def _ant_to_messages(ant_messages: list[dict[str, Any]], system_prompt: str | None = None) -> list[Message]:
        """Convert Anthropic messages → orchestration2 Messages."""
        result: list[Message] = []

        for msg in ant_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "user":
                if isinstance(content, str):
                    result.append(Message(role=MessageRole.USER, content=content))
                elif isinstance(content, list):
                    # Could be tool_result blocks
                    tool_subs = []
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_result":
                            tool_subs.append(SubMessage(
                                kind=SubMessageKind.TOOL_RESULT,
                                content=block.get("content", ""),
                                tool_call=ToolCallRef(
                                    tool_name="",
                                    call_id=block.get("tool_use_id", ""),
                                ),
                            ))
                    if tool_subs:
                        result.append(Message(
                            role=MessageRole.TOOL,
                            content=tool_subs[0].content if tool_subs else "",
                            submessages=tool_subs,
                        ))
                    else:
                        text = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
                        result.append(Message(role=MessageRole.USER, content=text))

            elif role == "assistant":
                submessages: list[SubMessage] = []
                if isinstance(content, str):
                    submessages.append(SubMessage(kind=SubMessageKind.TEXT, content=content))
                    result.append(Message(role=MessageRole.ASSISTANT, content=content, submessages=submessages))
                elif isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                                submessages.append(SubMessage(kind=SubMessageKind.TEXT, content=block.get("text", "")))
                            elif block.get("type") == "tool_use":
                                submessages.append(SubMessage(
                                    kind=SubMessageKind.TOOL_CALL,
                                    content="",
                                    tool_call=ToolCallRef(
                                        tool_name=block.get("name", ""),
                                        call_id=block.get("id", ""),
                                        arguments=block.get("input", {}),
                                    ),
                                ))
                    result.append(Message(
                        role=MessageRole.ASSISTANT,
                        content="\n".join(text_parts).strip(),
                        submessages=submessages,
                    ))

        return result

    @staticmethod
    def _convert_tools(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert orchestration2 tool definitions to Anthropic format."""
        return [
            {
                "name": defn["name"],
                "description": defn.get("description", ""),
                "input_schema": defn.get("parameters", {"type": "object", "properties": {}}),
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
