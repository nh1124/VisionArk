"""Search and research tools: Google Search, URL research, Places, Deep Research."""

from __future__ import annotations

import asyncio
import logging

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_api_key, get_gemini_client, make_result

logger = logging.getLogger(__name__)

# Polling settings for Gemini Interactions API (deep research)
_GEMINI_POLL_INTERVAL_SEC = 10
_GEMINI_POLL_TIMEOUT_SEC  = 1800  # 30 minutes max

# ── Model routing table ──────────────────────────────────────────────────────
# (provider, speed) -> model_id
_MODEL_MAP: dict[tuple[str, str], str] = {
    ("gemini",    "deep"): "deep-research-pro-preview-12-2025",
    ("gemini",    "fast"): "gemini-3.1-pro-preview",
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
            "  or with options: deep_research(query=\"...\", provider=\"openai\", speed=\"fast\") "
            "  or with timeout: deep_research(query=\"...\", timeout_sec=60) — returns a job_id if not finished in time."
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
                "timeout_sec": {
                    "type": "integer",
                    "description": (
                        "Maximum seconds to wait synchronously for the result (default: 300, range: 60–3600). "
                        "Applies to all providers. If the research is still running at timeout and "
                        "async_on_timeout is true, a job_id is returned so you can check progress "
                        "with deep_research_status()."
                    ),
                },
                "async_on_timeout": {
                    "type": "boolean",
                    "description": (
                        "When true (default), if timeout_sec is exceeded the job continues in the background "
                        "and a job_id is returned. When false, timeout returns an error."
                    ),
                },
                "result_path": {
                    "type": "string",
                    "description": (
                        "Optional file path where the research result will be saved "
                        "(relative to the user's artifacts directory). "
                        "Defaults to 'research/<job_id>.md'."
                    ),
                },
            },
            "required": ["query"],
        },
    )

    # ── Public entry point ────────────────────────────────────────────────────

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        query            = call.arguments.get("query", "").strip()
        provider         = (call.arguments.get("provider") or "auto").lower()
        speed            = (call.arguments.get("speed")    or "deep").lower()
        timeout_sec      = call.arguments.get("timeout_sec", 300)
        async_on_timeout = call.arguments.get("async_on_timeout", True)
        result_path_arg  = call.arguments.get("result_path")

        # ── Validate inputs ──────────────────────────────────────────────────
        if provider not in _VALID_PROVIDERS:
            return fail(
                call,
                f"Invalid provider '{provider}'. Valid options: {list(_VALID_PROVIDERS)}. "
                f"Currently configured providers with API keys: {await self._configured_providers(ctx)}.",
            )
        if speed not in _VALID_SPEEDS:
            return fail(call, f"Invalid speed '{speed}'. Valid options: {list(_VALID_SPEEDS)}.")

        try:
            timeout_sec = max(60, min(3600, int(timeout_sec)))
        except (TypeError, ValueError):
            timeout_sec = 300

        # ── Resolve 'auto' ────────────────────────────────────────────────────
        if provider == "auto":
            provider = (ctx.engine_kind or "gemini").lower()
            if provider not in ("gemini", "openai", "anthropic"):
                provider = "gemini"

        model = _MODEL_MAP[(provider, speed)]
        logger.info("[DeepResearch] provider=%s speed=%s model=%s", provider, speed, model)

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

        # ── Dispatch — no job created here; jobs are created lazily on timeout ─
        if provider == "gemini" and speed == "deep":
            return await self._research_gemini_deep(
                call, ctx, query, model, api_key, timeout_sec, async_on_timeout, result_path_arg
            )

        from domains.long_running.providers import do_gemini_fast, do_openai, do_anthropic
        if provider == "gemini":
            coro = do_gemini_fast(query, model, api_key)
        elif provider == "openai":
            coro = do_openai(query, model, api_key)
        else:
            coro = do_anthropic(query, model, api_key)

        return await self._run_with_timeout(
            call, ctx, provider, query, model, coro, timeout_sec, async_on_timeout, result_path_arg
        )

    # ── Gemini deep — poll Interactions API, create job lazily on timeout ─────

    async def _research_gemini_deep(
        self,
        call: ToolCallRef,
        ctx: ExecutionContext,
        query: str,
        model: str,
        api_key: str,
        timeout_sec: int = 300,
        async_on_timeout: bool = True,
        result_path_arg: str | None = None,
    ) -> ToolResult:
        """Gemini Deep Research via Interactions API.

        Sync phase: poll for up to timeout_sec.
          - Completes in time → save file, return text (no job created).
          - Timeout + async_on_timeout=True → create job(external_ref=interaction_id)
            → executor resumes polling via DeepResearchJobHandler.
          - Timeout + async_on_timeout=False → return error (no job created).
        """
        import json as _json
        import uuid
        from domains.orchestration2.tools.base import get_db, get_user_id
        from domains.long_running.services.job_service import LongRunningJobService
        from domains.long_running.models import JobCreateOptions
        from domains.long_running.utils import save_result_to_file

        db      = get_db(ctx)
        user_id = get_user_id(ctx)

        try:
            from google import genai

            client = genai.Client(api_key=api_key)

            # Start the interaction on Google's servers (runs asynchronously there)
            interaction = await asyncio.to_thread(
                client.interactions.create,
                input=query,
                agent=model,
                background=True,
            )
            interaction_id = interaction.id
            logger.info(
                "[DeepResearch/Gemini] started interaction=%s model=%s",
                interaction_id, model,
            )

            # ── Poll until done or timeout ────────────────────────────────────
            elapsed = 0
            while elapsed < timeout_sec:
                await asyncio.sleep(_GEMINI_POLL_INTERVAL_SEC)
                elapsed += _GEMINI_POLL_INTERVAL_SEC

                interaction = await asyncio.to_thread(client.interactions.get, interaction_id)
                status = interaction.status
                logger.debug(
                    "[DeepResearch/Gemini] poll id=%s status=%s elapsed=%ds",
                    interaction_id, status, elapsed,
                )

                if status == "completed":
                    outputs = getattr(interaction, "outputs", []) or []
                    text = outputs[-1].text if outputs else ""
                    if not text:
                        return fail(
                            call,
                            f"Gemini ({model}) completed but returned no text.",
                        )
                    # Sync success: save file directly, no job needed
                    result_path = await save_result_to_file(
                        user_id, str(uuid.uuid4()), text,
                        sub_dir="research", filename=result_path_arg,
                    )
                    logger.info(
                        "[DeepResearch/Gemini] sync completed interaction=%s result=%s",
                        interaction_id, result_path,
                    )
                    return make_result(call, text)

                elif status == "failed":
                    error = getattr(interaction, "error", "Unknown error")
                    return fail(call, f"Gemini ({model}) failed during execution: {error}.")

            # ── Timeout reached ───────────────────────────────────────────────
            if not async_on_timeout:
                return fail(
                    call,
                    f"Gemini ({model}) timed out after {timeout_sec}s "
                    f"(interaction={interaction_id}).",
                )

            # Create job NOW — executor will resume polling the running interaction
            try:
                opts = JobCreateOptions(
                    result_path=result_path_arg,
                    external_ref=interaction_id,
                    project_id=ctx.metadata.get("project_id"),
                    session_id=ctx.metadata.get("session_id"),
                )
                job = await LongRunningJobService.create_job(
                    db=db,
                    user_id=user_id,
                    tool_name="deep_research",
                    job_kind="research.gemini.deep",
                    input_payload={"query": query, "model": model},
                    provider="gemini",
                    model=model,
                    options=opts,
                )
            except Exception as exc:
                logger.error("[DeepResearch/Gemini] failed to create background job: %s", exc)
                return fail(call, f"Research timed out and background job creation failed: {exc}")

            logger.info(
                "[DeepResearch/Gemini] timeout, job %s created for background (interaction=%s)",
                job.id, interaction_id,
            )
            return make_result(
                call,
                _json.dumps({
                    "status": "running",
                    "job_id": job.id,
                    "result_path": result_path_arg,
                    "message": (
                        "Research is still in progress. "
                        f"Use deep_research_status(job_id=\"{job.id}\") to check progress."
                    ),
                }),
            )

        except Exception as e:
            return fail(
                call,
                f"Gemini ({model}) failed: {e}. "
                "Check that your Gemini API key is valid and the model is available.",
            )

    # ── All other providers — run inline, create job lazily on timeout ────────

    async def _run_with_timeout(
        self,
        call: ToolCallRef,
        ctx: ExecutionContext,
        provider: str,
        query: str,
        model: str,
        coro,
        timeout_sec: int,
        async_on_timeout: bool,
        result_path_arg: str | None,
    ) -> ToolResult:
        """Run a provider coroutine with a timeout.

        Sync success → save file, return text (no job created).
        Timeout + async_on_timeout=True → create job → ResearchInlineHandler re-runs from scratch.
        Timeout + async_on_timeout=False → return error (no job created).
        """
        import json as _json
        import uuid
        from domains.orchestration2.tools.base import get_db, get_user_id
        from domains.long_running.services.job_service import LongRunningJobService
        from domains.long_running.models import JobCreateOptions
        from domains.long_running.utils import save_result_to_file

        db      = get_db(ctx)
        user_id = get_user_id(ctx)

        try:
            text, _ = await asyncio.wait_for(coro, timeout=timeout_sec)
        except asyncio.TimeoutError:
            if not async_on_timeout:
                return fail(call, f"Deep research timed out after {timeout_sec}s.")
            # Create job — handler will re-run the query from scratch in background
            try:
                opts = JobCreateOptions(
                    result_path=result_path_arg,
                    project_id=ctx.metadata.get("project_id"),
                    session_id=ctx.metadata.get("session_id"),
                )
                job = await LongRunningJobService.create_job(
                    db=db,
                    user_id=user_id,
                    tool_name="deep_research",
                    job_kind="research.inline",
                    input_payload={"query": query, "model": model},
                    provider=provider,
                    model=model,
                    options=opts,
                )
            except Exception as exc:
                logger.error("[DeepResearch] failed to create background job: %s", exc)
                return fail(call, f"Research timed out and background job creation failed: {exc}")

            logger.info(
                "[DeepResearch] timeout, job %s created for background provider=%s",
                job.id, provider,
            )
            return make_result(
                call,
                _json.dumps({
                    "status": "running",
                    "job_id": job.id,
                    "result_path": result_path_arg,
                    "message": (
                        "Research is still in progress. "
                        f"Use deep_research_status(job_id=\"{job.id}\") to check progress."
                    ),
                }),
            )
        except Exception as exc:
            return fail(call, str(exc))

        if not text:
            return fail(call, "Deep research returned no content.")

        # Sync success: save file, no job needed
        result_path = await save_result_to_file(
            user_id, str(uuid.uuid4()), text,
            sub_dir="research", filename=result_path_arg,
        )
        logger.info("[DeepResearch] sync completed provider=%s result=%s", provider, result_path)
        return make_result(call, text)

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _configured_providers(self, ctx: ExecutionContext) -> list[str]:
        """Return list of providers for which a non-empty API key exists."""
        result = []
        for p in ("gemini", "openai", "anthropic"):
            key = await get_api_key(ctx, p)
            if key:
                result.append(p)
        return result


class DeepResearchStatusTool:
    """Check the status and progress of a background deep research job."""

    definition = ToolDef(
        name="deep_research_status",
        description=(
            "Check the status of a background deep_research job. "
            "Use this after deep_research() returns a job_id. "
            "HOW TO USE: deep_research_status(job_id=\"<uuid>\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job_id returned by deep_research() when async_on_timeout is true.",
                },
            },
            "required": ["job_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        import json as _json
        from domains.orchestration2.tools.base import get_db, get_user_id
        from domains.long_running.services.job_service import LongRunningJobService

        job_id  = call.arguments.get("job_id", "").strip()
        db      = get_db(ctx)
        user_id = get_user_id(ctx)

        if not job_id:
            return fail(call, "job_id is required.")

        job = await LongRunningJobService.get_job(db, job_id, user_id)
        if not job:
            return fail(call, f"Job '{job_id}' not found or access denied.")

        data: dict = {
            "job_id": job.id,
            "status": job.status,
            "tool_name": job.tool_name,
            "job_kind": job.job_kind,
            "progress": job.progress,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "result_path": job.result_path,
        }

        if job.status == "completed":
            data["result_summary"] = (
                job.result_payload.get("text", "")[:500] if job.result_payload else None
            )
        elif job.status in ("failed", "cancelled"):
            data["error_code"]    = job.error_code
            data["error_message"] = job.error_message

        return make_result(call, _json.dumps(data, ensure_ascii=False))


class DeepResearchCancelTool:
    """Cancel a running background deep research job."""

    definition = ToolDef(
        name="deep_research_cancel",
        description=(
            "Cancel a background deep_research job that is still running. "
            "HOW TO USE: deep_research_cancel(job_id=\"<uuid>\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "The job_id to cancel.",
                },
            },
            "required": ["job_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        import json as _json
        from domains.orchestration2.tools.base import get_db, get_user_id
        from domains.long_running.services.job_service import LongRunningJobService

        job_id  = call.arguments.get("job_id", "").strip()
        db      = get_db(ctx)
        user_id = get_user_id(ctx)

        if not job_id:
            return fail(call, "job_id is required.")

        cancelled = await LongRunningJobService.cancel_job(db, job_id, user_id)
        if cancelled:
            return make_result(call, _json.dumps({"status": "cancelled", "job_id": job_id}))
        else:
            return fail(
                call,
                f"Could not cancel job '{job_id}'. "
                "It may not exist, be already completed/failed, or not belong to you.",
            )
