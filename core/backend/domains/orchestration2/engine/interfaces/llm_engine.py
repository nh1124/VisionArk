"""LLMEngine abstract base class.

Every LLM backend (Gemini, OpenAI, …) implements this interface so the
orchestration layer can delegate the full inference loop without knowing
provider-specific details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models.engine_io import EngineRunInput, EngineRunResult, EngineRunStatus, RunOptions


class LLMEngine(ABC):
    """Abstract base for LLM inference engines."""

    @property
    @abstractmethod
    def kind(self) -> str:
        """Short identifier for the engine type, e.g. 'gemini', 'openai'."""
        ...

    @abstractmethod
    async def run(
        self,
        run_input: EngineRunInput,
        options: RunOptions | None = None,
    ) -> EngineRunResult:
        """Execute a (potentially multi-turn) inference loop.

        The engine owns the full loop: LLM call → tool dispatch → history
        update → repeat until done or limits exceeded.
        """
        ...

    def get_status(self, run_id: str) -> EngineRunStatus | None:
        """Return the current status of an in-progress run.

        Default implementation returns ``None`` (not tracked).
        Subclasses may override for observability.
        """
        return None
