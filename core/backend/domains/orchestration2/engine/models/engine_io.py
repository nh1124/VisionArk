"""Engine runtime I/O models.

Defines the input/output types for the LLMEngine abstraction layer.
These live inside ``engine/models/`` so that the ``engine`` package
remains self-contained with no dependency on ``engine_runtime``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .message import Message, SubMessage


class RunOptions(BaseModel):
    """Per-run overrides for engine behaviour."""

    max_turns: int = 25
    max_tool_calls: int = 50
    allow_partial_on_error: bool = True


class EngineRunInput(BaseModel):
    """Everything the engine needs to execute one run."""

    run_id: str
    message: Message
    history: list[Message] = Field(default_factory=list)
    system_prompt: str | None = None
    tool_defs: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EngineRunResult(BaseModel):
    """Structured result returned from engine.run()."""

    run_id: str
    status: Literal["completed", "failed", "cancelled"]
    output_message: Message | None = None
    history: list[Message] = Field(default_factory=list)
    error: str | None = None


class EngineRunStatus(BaseModel):
    """Snapshot of a running engine invocation (for observability)."""

    run_id: str
    phase: Literal["running", "completed", "failed", "cancelled"]
    latest_message: Message | None = None
    latest_submessage: SubMessage | None = None
    tool_calls: int = 0
    tool_progress: dict[str, Any] = Field(default_factory=dict)
