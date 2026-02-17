"""Engine runtime — LLM-native inference engines for orchestration2.

Canonical locations:
- ``LLMEngine`` → ``engine.interfaces.llm_engine``
- ``EngineRunInput`` etc. → ``engine.models.engine_io``
- ``EngineRunInput`` etc. → ``engine.models.engine_io``

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
from .gemini_engine import GeminiEngine
from .openai_engine import OpenAIEngine

__all__ = [
    "LLMEngine",
    "GeminiEngine",
    "OpenAIEngine",
    "EngineRunInput",
    "EngineRunResult",
    "RunOptions",
]
