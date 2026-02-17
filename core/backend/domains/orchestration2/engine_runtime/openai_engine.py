"""OpenAIEngine — placeholder scaffold for future OpenAI integration."""

from __future__ import annotations

from .base import LLMEngine
from .models import EngineRunInput, EngineRunResult, EngineRunStatus, RunOptions


class OpenAIEngine(LLMEngine):
    """Scaffold for an OpenAI-backed LLM engine.

    Not yet implemented — raises ``NotImplementedError`` on use.
    """

    @property
    def kind(self) -> str:
        return "openai"

    async def run(
        self,
        run_input: EngineRunInput,
        options: RunOptions | None = None,
    ) -> EngineRunResult:
        raise NotImplementedError("OpenAIEngine is not yet implemented")

    def get_status(self, run_id: str) -> EngineRunStatus | None:
        return None
