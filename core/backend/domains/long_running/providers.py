"""Standalone provider coroutines for deep research.

Pure async functions with no tool/job knowledge.
Used by both DeepResearchTool (sync path) and LRJ handlers (background path).
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_OPENAI_FALLBACK_MODEL = "gpt-4o"


async def do_gemini_fast(query: str, model: str, api_key: str) -> tuple[str, str]:
    """Gemini generate_content + Google Search grounding. Returns (text, model_used)."""
    try:
        from google.genai import Client, types

        client = Client(api_key=api_key, http_options={"api_version": "v1alpha"})
        response = client.models.generate_content(
            model=model,
            contents=query,
            config=types.GenerateContentConfig(
                tools=[
                    types.Tool(google_search=types.GoogleSearch()),
                    {"url_context": {}},
                ]
            ),
        )
        text = response.text or ""
        if not text:
            raise RuntimeError(f"Gemini/{model} returned no content.")
        return text, model
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Gemini/{model} failed: {exc}. "
            "Check that your Gemini API key is valid and the model is available."
        ) from exc


async def do_openai(query: str, model: str, api_key: str) -> tuple[str, str]:
    """OpenAI Responses API with web_search_preview. Falls back to gpt-4o."""
    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, timeout=600.0)

        async def _call(m: str) -> str:
            response = await client.responses.create(
                model=m,
                input=query,
                tools=[{"type": "web_search_preview"}],
            )
            parts: list[str] = []
            for item in response.output:
                if getattr(item, "type", None) == "message":
                    for content in getattr(item, "content", []):
                        t = getattr(content, "text", None)
                        if t:
                            parts.append(t)
            return "\n\n".join(parts)

        try:
            text = await _call(model)
        except Exception as primary_err:
            logger.warning(
                "[research/openai] model '%s' unavailable (%s), retrying with '%s'",
                model, primary_err, _OPENAI_FALLBACK_MODEL,
            )
            try:
                text = await _call(_OPENAI_FALLBACK_MODEL)
                model = _OPENAI_FALLBACK_MODEL
            except Exception as fallback_err:
                raise RuntimeError(
                    f"OpenAI research failed. "
                    f"Primary '{model}': {primary_err}. "
                    f"Fallback '{_OPENAI_FALLBACK_MODEL}': {fallback_err}."
                ) from fallback_err

        if not text:
            raise RuntimeError(f"OpenAI/{model} returned no content.")
        return text, model
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"OpenAI/{model} failed: {exc}. "
            "Check that your OpenAI API key is valid."
        ) from exc


async def do_anthropic(query: str, model: str, api_key: str) -> tuple[str, str]:
    """Anthropic Messages API for research (training data, no live web access)."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=(
                "You are an expert research analyst. Conduct thorough, structured research "
                "on the given topic. Provide detailed analysis, key findings, relevant context, "
                "and actionable insights. Clearly note the knowledge cutoff date and any "
                "limitations of your response (e.g., no live web access)."
            ),
            messages=[{"role": "user", "content": query}],
        )
        text = "".join(block.text for block in response.content if hasattr(block, "text"))
        if not text:
            raise RuntimeError(f"Anthropic/{model} returned no content.")
        return text, model
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"Anthropic/{model} failed: {exc}. "
            "Check that your Anthropic API key is valid."
        ) from exc


async def get_api_key_for_provider(db, user_id: str, provider: str) -> Optional[str]:
    """Fetch the user's API key for a given provider from UserSettings."""
    from sqlalchemy import select
    from shared.database import UserSettings

    res = await db.execute(select(UserSettings).where(UserSettings.user_id == user_id))
    settings = res.scalars().first()
    if not settings:
        return None
    try:
        from infrastructure.llm.model_router import get_api_key_for_provider as _get
        return _get(settings, provider) or None
    except Exception:
        # Fallback: direct attribute lookup
        return getattr(settings, f"{provider}_api_key", None) or None
