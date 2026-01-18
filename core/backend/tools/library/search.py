from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from tools.base import BaseTool
from tools.utils import get_gemini_client
from google.genai import types
from sqlalchemy.ext.asyncio import AsyncSession

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
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("session")
        if not user_id or not session: return {"success": False, "message": "Context error"}
        
        try:
            client = await get_gemini_client(user_id, session)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=query, 
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            return {"success": True, "message": resp.text or "No result from Google Search"}
        except Exception as e:
            return {"success": False, "message": f"Google Search failed: {e}"}

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
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("session")
        if not user_id or not session: return {"success": False, "message": "Context error"}
        
        try:
            client = await get_gemini_client(user_id, session)
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
                return {"success": False, "message": "No content retrieved from URLs"}
            
            return {"success": True, "message": result_text}
        except Exception as e:
            return {"success": False, "message": f"URL research failed: {e}"}

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
        user_id: str = kwargs.get("user_id")
        session: AsyncSession = kwargs.get("session")
        if not user_id or not session: return {"success": False, "message": "Context error"}
        
        try:
            client = await get_gemini_client(user_id, session)
            resp = client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=query, 
                config=types.GenerateContentConfig(tools=[types.Tool(google_maps=types.GoogleMaps())])
            )
            return {"success": True, "message": resp.text or "No result from Google Maps"}
        except Exception as e:
            return {"success": False, "message": f"Search places failed: {e}"}
