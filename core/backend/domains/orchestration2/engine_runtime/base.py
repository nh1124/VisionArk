"""Backward-compat re-export — LLMEngine now lives in engine/interfaces."""

from ..engine.interfaces.llm_engine import LLMEngine  # noqa: F401

__all__ = ["LLMEngine"]
