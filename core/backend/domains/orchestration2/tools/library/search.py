"""Search and research tools: Google Search, URL research, Places, Deep Research."""

from __future__ import annotations

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_gemini_client, make_result, resolve_artifacts_dir


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
            "Perform extensive multi-step research using Gemini Deep Research. "
            "HOW TO USE: deep_research(query=\"Comprehensive analysis of quantum computing trends\")"
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Research topic or question"},
            },
            "required": ["query"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        query = call.arguments.get("query", "")
        try:
            from google.genai import types

            client = await get_gemini_client(ctx)
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())]
                ),
            )
            return make_result(call, response.text or "No research results")
        except Exception as e:
            return fail(call, f"Deep research failed: {e}")
