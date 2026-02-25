"""Provider registry: factory for LLMProvider instances."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from domains.orchestration2.engine.interfaces.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


def resolve_provider(provider_id: str, api_key: str, model: str | None = None) -> "LLMProvider":
    """Return the correct LLMProvider instance for the given provider."""
    if provider_id == "openai":
        from .openai_provider import OpenAILLMProvider
        return OpenAILLMProvider(api_key=api_key, preferred_model=model)
    elif provider_id == "anthropic":
        from .anthropic_provider import AnthropicLLMProvider
        return AnthropicLLMProvider(api_key=api_key, preferred_model=model)
    else:
        from .orchestration2_provider import GeminiLLMProvider
        return GeminiLLMProvider(api_key=api_key, preferred_model=model)
