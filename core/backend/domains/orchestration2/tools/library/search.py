"""Search and research tools: Google Search, URL research, Places, Deep Research."""

from __future__ import annotations

import logging

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_api_key, get_gemini_client, make_result

logger = logging.getLogger(__name__)

# ── Model routing table ──────────────────────────────────────────────────────
# (provider, speed) -> model_id
_MODEL_MAP: dict[tuple[str, str], str] = {
    ("gemini",    "deep"): "gemini-3.1-pro",
    ("gemini",    "fast"): "gemini-3-flash",
    ("openai",    "deep"): "o3-deep-research",
    ("openai",    "fast"): "o4-mini-deep-research",
    ("anthropic", "deep"): "claude-opus-4.6",
    ("anthropic", "fast"): "claude-3.5-haiku",
}

# OpenAI secondary fallback when the deep-research model is unavailable
_OPENAI_FALLBACK_MODEL = "gpt-4o"

_VALID_PROVIDERS = ("gemini", "openai", "anthropic", "auto")
_VALID_SPEEDS    = ("deep", "fast")


class GoogleSearchTool:
    definition = ToolDef(
        name="google_search",
        description=(
            "Search Google for real-time information using Gemini's native Google Search grounding. "
            "HOW TO USE: google_search(query=\"Latest stock price of GOOGL\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
            },
            "required": ["query"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        query = call.arguments.get("query", "")
        try:
            from google.genai import types

            client = await get_gemini_client(ctx)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            return make_result(call, resp.text or "No result from Google Search")
        except Exception as e:
            return fail(call, f"Google Search failed: {e}")


class ResearchURLTool:
    definition = ToolDef(
        name="research_url",
        description=(
            "Deeply analyze content from specific URLs using Gemini's native URL Context. "
            "HOW TO USE: research_url(urls=[\"https://example.com\"], query=\"Compare pricing\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of URLs to research",
                },
                "query": {"type": "string", "description": "Question or topic to research"},
            },
            "required": ["urls", "query"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        urls = call.arguments.get("urls", [])
        query = call.arguments.get("query", "")
        try:
            from google.genai import types

            client = await get_gemini_client(ctx)
            urls_str = " and ".join(urls)
            prompt = f"{query} from {urls_str}" if query else f"Summarize content from {urls_str}"

            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(tools=[{"url_context": {}}]),
            )

            result_text = ""
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            result_text += part.text

            if not result_text:
                return fail(call, "No content retrieved from URLs")
            return make_result(call, result_text)
        except Exception as e:
            return fail(call, f"URL research failed: {e}")


class SearchPlacesTool:
    definition = ToolDef(
        name="search_places",
        description=(
            "Search locations/businesses using Google Maps grounding. "
            "HOW TO USE: search_places(query=\"Best sushi restaurants in Tokyo\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Location/business search query"},
            },
            "required": ["query"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        query = call.arguments.get("query", "")
        try:
            from google.genai import types

            client = await get_gemini_client(ctx)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            return make_result(call, resp.text or "No places found")
        except Exception as e:
            return fail(call, f"Places search failed: {e}")


class DeepResearchTool:
    definition = ToolDef(
        name="deep_research",
        description=(
            "Perform extensive multi-step research using the best available research model. "
            "Supports Gemini (Google Search grounding), OpenAI (o3/o4-mini-deep-research via Responses API), "
            "and Anthropic (Claude Opus). "
            "HOW TO USE: deep_research(query=\"Quantum computing trends\") "
            "  or with options: deep_research(query=\"...\", provider=\"openai\", speed=\"fast\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Research topic or question",
                },
                "provider": {
                    "type": "string",
                    "enum": ["auto", "gemini", "openai", "anthropic"],
                    "description": (
                        "LLM provider to use for research. "
                        "'auto' (default) follows the currently active engine. "
                        "Explicit values override the active engine."
                    ),
                },
                "speed": {
                    "type": "string",
                    "enum": ["deep", "fast"],
                    "description": (
                        "'deep' (default) uses the highest-quality research model. "
                        "'fast' uses a lightweight, lower-latency model."
                    ),
                },
            },
            "required": ["query"],
        },
    )

    # ── Public entry point ────────────────────────────────────────────────────

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        query    = call.arguments.get("query", "").strip()
        provider = (call.arguments.get("provider") or "auto").lower()
        speed    = (call.arguments.get("speed")    or "deep").lower()

        # ── Validate inputs ──────────────────────────────────────────────────
        if provider not in _VALID_PROVIDERS:
            return fail(
                call,
                f"Invalid provider '{provider}'. Valid options: {list(_VALID_PROVIDERS)}. "
                f"Currently configured providers with API keys: {await self._configured_providers(ctx)}.",
            )

        if speed not in _VALID_SPEEDS:
            return fail(
                call,
                f"Invalid speed '{speed}'. Valid options: {list(_VALID_SPEEDS)}.",
            )

        # ── Resolve 'auto' to the active engine ──────────────────────────────
        if provider == "auto":
            provider = (ctx.engine_kind or "gemini").lower()
            # Normalize unknown kinds to gemini
            if provider not in ("gemini", "openai", "anthropic"):
                provider = "gemini"

        # ── Look up target model ─────────────────────────────────────────────
        model = _MODEL_MAP[(provider, speed)]
        logger.info("[DeepResearch] provider=%s speed=%s model=%s", provider, speed, model)

        # ── Validate API key is present before attempting the call ───────────
        api_key = await get_api_key(ctx, provider)
        if not api_key:
            configured = await self._configured_providers(ctx)
            return fail(
                call,
                f"Deep research with provider='{provider}' (model='{model}') is not possible: "
                f"no API key configured for '{provider}'. "
                f"Providers with a configured API key: {configured}. "
                f"Please add an API key in Settings → AI Configuration.",
            )

        # ── Dispatch to provider implementation ──────────────────────────────
        if provider == "gemini":
            return await self._research_gemini(call, ctx, query, model, api_key)
        elif provider == "openai":
            return await self._research_openai(call, query, model, api_key)
        else:  # anthropic
            return await self._research_anthropic(call, query, model, api_key)

    # ── Gemini ────────────────────────────────────────────────────────────────

    async def _research_gemini(
        self,
        call: ToolCallRef,
        ctx: ExecutionContext,
        query: str,
        model: str,
        api_key: str,
    ) -> ToolResult:
        try:
            from google.genai import Client, types

            client = Client(api_key=api_key, http_options={"api_version": "v1alpha"})
            response = client.models.generate_content(
                model=model,
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            text = response.text or ""
            if not text:
                return fail(call, f"Deep research with Gemini ({model}) returned no content.")
            return make_result(call, text)
        except Exception as e:
            return fail(
                call,
                f"Deep research with Gemini ({model}) failed: {e}. "
                "Check that your Gemini API key is valid and that the model is available for your account.",
            )

    # ── OpenAI ────────────────────────────────────────────────────────────────

    async def _research_openai(
        self,
        call: ToolCallRef,
        query: str,
        model: str,
        api_key: str,
    ) -> ToolResult:
        """Use OpenAI Responses API with web_search tool for deep research.

        o3-deep-research / o4-mini-deep-research are purpose-built for multi-step
        research and require at least one data source (web_search here).
        Falls back to gpt-4o + web_search_preview if the deep-research model is
        unavailable (e.g. Tier 1 accounts).
        """
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, timeout=600.0)

            async def _call_responses(m: str) -> str:
                response = await client.responses.create(
                    model=m,
                    input=query,
                    tools=[{"type": "web_search_preview"}],
                )
                # Extract final message text from output items
                parts: list[str] = []
                for item in response.output:
                    if getattr(item, "type", None) == "message":
                        for content in getattr(item, "content", []):
                            text = getattr(content, "text", None)
                            if text:
                                parts.append(text)
                return "\n\n".join(parts)

            # Try the requested deep-research model first
            try:
                text = await _call_responses(model)
            except Exception as primary_err:
                # If the model itself is unavailable (e.g. model_not_found),
                # fall back to gpt-4o + web_search_preview
                logger.warning(
                    "[DeepResearch] OpenAI model '%s' unavailable (%s), retrying with '%s'",
                    model, primary_err, _OPENAI_FALLBACK_MODEL,
                )
                try:
                    text = await _call_responses(_OPENAI_FALLBACK_MODEL)
                    model = _OPENAI_FALLBACK_MODEL   # update for logging
                except Exception as fallback_err:
                    return fail(
                        call,
                        f"Deep research with OpenAI failed. "
                        f"Primary model '{model}' error: {primary_err}. "
                        f"Fallback model '{_OPENAI_FALLBACK_MODEL}' error: {fallback_err}. "
                        "Ensure your OpenAI API key is valid and has sufficient tier access.",
                    )

            if not text:
                return fail(call, f"Deep research with OpenAI ({model}) returned no content.")

            logger.info("[DeepResearch] OpenAI responded with model=%s", model)
            return make_result(call, text)

        except Exception as e:
            return fail(
                call,
                f"Deep research with OpenAI ({model}) failed: {e}. "
                "Check that your OpenAI API key is valid and that the Responses API is accessible.",
            )

    # ── Anthropic ────────────────────────────────────────────────────────────

    async def _research_anthropic(
        self,
        call: ToolCallRef,
        query: str,
        model: str,
        api_key: str,
    ) -> ToolResult:
        """Use Anthropic Messages API for research.

        Note: Anthropic does not currently provide a native web search tool via
        its public API. This implementation uses the top Claude model with a
        research-focused system prompt. Results are based on the model's training
        data and do not include live web access.
        """
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
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            if not text:
                return fail(call, f"Deep research with Anthropic ({model}) returned no content.")
            return make_result(call, text)
        except Exception as e:
            return fail(
                call,
                f"Deep research with Anthropic ({model}) failed: {e}. "
                "Check that your Anthropic API key is valid and the model identifier is correct.",
            )

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _configured_providers(self, ctx: ExecutionContext) -> list[str]:
        """Return list of providers for which a non-empty API key exists."""
        result = []
        for p in ("gemini", "openai", "anthropic"):
            key = await get_api_key(ctx, p)
            if key:
                result.append(p)
        return result
