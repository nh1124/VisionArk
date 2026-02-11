from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from domains.orchestration.tools.base import BaseTool
from domains.orchestration.tools.utils import get_gemini_client, resolve_project_artifacts_dir
from shared.paths import secure_path_join, get_project_dir
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

class GoogleSearchArgs(BaseModel):
    query: str = Field(..., description="The search query")

class GoogleSearchTool(BaseTool):
    name = "google_search"
    description = (
        "Search Google for real-time information using Gemini's native Google Search grounding. "
        "HOW TO USE: 'google_search(query=\"Latest stock price of GOOGL\")'."
    )
    args_schema = GoogleSearchArgs

    async def run(self, query: str, **kwargs) -> Any:
        from domains.orchestration.tools.base import ToolResult
        user_id: str = kwargs.get("user_id")
        db_session: AsyncSession = kwargs.get("db_session")
        if not user_id or not db_session: return ToolResult(content="Context error", is_success=False)
        
        try:
            client = await get_gemini_client(user_id, db_session)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=query, 
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            return ToolResult(content=resp.text or "No result from Google Search")
        except Exception as e:
            return ToolResult(content=f"Google Search failed: {e}", is_success=False)

class ResearchURLArgs(BaseModel):
    urls: List[str] = Field(..., description="List of URLs to research")
    query: str = Field(..., description="Specific question or topic to research across those URLs")

class ResearchURLTool(BaseTool):
    name = "research_url"
    description = (
        "Deeply analyze and research content from specific URLs using Gemini's native URL Context. "
        "ATTENTION: Provide a clear query to guide the analysis. If query is None, it defaults to a summary. "
        "HOW TO USE: 'research_url(urls=[\"https://example.com\"], query=\"Compare the pricing mentioned.\")'."
    )
    args_schema = ResearchURLArgs

    async def run(self, urls: List[str], query: str, **kwargs) -> Any:
        from domains.orchestration.tools.base import ToolResult
        user_id: str = kwargs.get("user_id")
        db_session: AsyncSession = kwargs.get("db_session")
        if not user_id or not db_session: return ToolResult(content="Context error", is_success=False)
        
        try:
            client = await get_gemini_client(user_id, db_session)
            # Combine URLs into the instruction as suggested by docs
            urls_str = " and ".join(urls)
            prompt = f"{query} from {urls_str}" if query else f"Summarize the content from {urls_str}"
            
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"url_context": {}}]
                )
            )
            
            result_text = ""
            for candidate in response.candidates:
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            result_text += part.text
            
            if not result_text:
                return ToolResult(content="No content retrieved from URLs", is_success=False)
            
            return ToolResult(content=result_text)
        except Exception as e:
            return ToolResult(content=f"URL research failed: {e}", is_success=False)

class SearchPlacesArgs(BaseModel):
    query: str = Field(..., description="The place search query")

class SearchPlacesTool(BaseTool):
    name = "search_places"
    description = (
        "Search for locations, businesses, or points of interest using Google Maps grounding. "
        "HOW TO USE: 'search_places(query=\"Coffee shops in Shibuya open now\")'."
    )
    args_schema = SearchPlacesArgs

    async def run(self, query: str, **kwargs) -> Any:
        from domains.orchestration.tools.base import ToolResult
        user_id: str = kwargs.get("user_id")
        db_session: AsyncSession = kwargs.get("db_session")
        if not user_id or not db_session: return ToolResult(content="Context error", is_success=False)
        
        try:
            client = await get_gemini_client(user_id, db_session)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=query, 
                config=types.GenerateContentConfig(tools=[types.Tool(google_maps=types.GoogleMaps())])
            )
            return ToolResult(content=resp.text or "No result from Google Maps")
        except Exception as e:
            return ToolResult(content=f"Search places failed: {e}", is_success=False)

class DeepResearchArgs(BaseModel):
    query: str = Field(..., description="The complex research query or topic to investigate deeply")

class DeepResearchTool(BaseTool):
    name = "deep_research"
    description = (
        "Perform extensive, multi-step research on a complex topic using Gemini's native Deep Research agent. "
        "This tool autonomously plans, searches, and synthesizes a comprehensive report. "
        "USE THIS for complex investigations that require more than a simple search. "
        "HOW TO USE: 'deep_research(query=\"Research the impact of 6G on IoT security by 2030.\")'."
    )
    args_schema = DeepResearchArgs

    async def run(self, query: str, **kwargs) -> Any:
        from domains.orchestration.tools.base import ToolResult
        user_id: str = kwargs.get("user_id")
        db_session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        if not user_id or not db_session: return ToolResult(content="Context error", is_success=False)
        
        try:
            client = await get_gemini_client(user_id, db_session)
            
            if self.status_callback:
                await self.status_callback("Initiating Deep Research (this may take several minutes)...", "processing")

            # Interactions API for Deep Research
            interaction = client.interactions.create(
                model="gemini-3-pro",
                agent="deep-research-pro-preview-12-2025",
                contents=query,
                config={"background": False}
            )
            
            report_content = interaction.text or "Deep Research completed with no output."
            
            # Save to Artifact
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"research/report_{timestamp}.md"
            
            artifacts_dir = await resolve_project_artifacts_dir(user_id, project_id, db_session)
            p = secure_path_join(artifacts_dir, filename)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(report_content, encoding='utf-8')
            
            # Get relative path from project root
            root_dir = get_project_dir(user_id, project_id)
            actual_rel = p.relative_to(root_dir).as_posix()
            
            return ToolResult(
                content=f"Deep Research completed. Report saved to {actual_rel}", 
                data={
                    "path": actual_rel,
                    "content": report_content
                }
            )
        except Exception as e:
            return ToolResult(content=f"Deep Research failed: {e}", is_success=False)
