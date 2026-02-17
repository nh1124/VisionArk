"""Engine runtime — LLM-native inference engines for orchestration2.

Canonical locations:
- ``LLMEngine`` → ``engine.interfaces.llm_engine``
- ``EngineRunInput`` etc. → ``engine.models.engine_io``
- ``ToolDispatcher`` → ``engine.registry.tool_dispatcher``

This package re-exports for backward compatibility and hosts the
concrete engine implementations (Gemini, OpenAI, …).
"""

from ..engine.interfaces.llm_engine import LLMEngine
from ..engine.models.engine_io import (
    EngineRunInput,
    EngineRunResult,
    EngineRunStatus,
    RunOptions,
)
from ..engine.registry.tool_dispatcher import EngineToolAdapter, ToolDispatcher
from .gemini_engine import GeminiEngine
from .openai_engine import OpenAIEngine

__all__ = [
    "LLMEngine",
    "GeminiEngine",
    "OpenAIEngine",
    "EngineRunInput",
    "EngineRunResult",
    "EngineRunStatus",
    "RunOptions",
    "ToolDispatcher",
    "EngineToolAdapter",
]
