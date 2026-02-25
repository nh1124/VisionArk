"""Model router: parse provider:model specs and resolve API keys."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.database import UserSettings


# Known model prefixes for auto-detection (legacy compatibility)
_PREFIX_MAP = {
    "gpt-": "openai",
    "o1-": "openai",
    "o3-": "openai",
    "o4-": "openai",
    "claude-": "anthropic",
    "gemini-": "gemini",
}


def parse_model_spec(spec: str | None) -> tuple[str, str | None]:
    """Parse 'provider:model' → (provider_id, model_id).

    Falls back to prefix-based detection, then defaults to 'gemini'.

    Examples:
        >>> parse_model_spec("openai:gpt-4.1-mini")
        ("openai", "gpt-4.1-mini")
        >>> parse_model_spec("gemini-2.5-flash")
        ("gemini", "gemini-2.5-flash")
        >>> parse_model_spec("claude-sonnet-4-20250514")
        ("anthropic", "claude-sonnet-4-20250514")
        >>> parse_model_spec(None)
        ("gemini", None)
    """
    if not spec:
        return "gemini", None

    if ":" in spec:
        provider, model = spec.split(":", 1)
        if provider in ("gemini", "openai", "anthropic"):
            return provider, model

    # Legacy: infer provider from model name prefix
    for prefix, provider in _PREFIX_MAP.items():
        if spec.startswith(prefix):
            return provider, spec

    return "gemini", spec


def get_api_key_for_provider(settings: "UserSettings", provider_id: str) -> Optional[str]:
    """Return the decrypted API key for the given provider."""
    if settings is None:
        return None
    key_map = {
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }
    return key_map.get(provider_id)


def get_configured_providers(settings: "UserSettings") -> list[str]:
    """Return list of provider IDs that have API keys configured."""
    if settings is None:
        return []
    providers = []
    if settings.gemini_api_key:
        providers.append("gemini")
    if settings.openai_api_key:
        providers.append("openai")
    if settings.anthropic_api_key:
        providers.append("anthropic")
    return providers
