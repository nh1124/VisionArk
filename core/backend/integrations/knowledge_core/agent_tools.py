from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from integrations.knowledge_core.service import KnowledgeCoreService
from sqlalchemy.ext.asyncio import AsyncSession

class SearchKnowledgeArgs(BaseModel):
    query: str = Field(..., description="The search query")
    limit: int = Field(5, description="Maximum number of results to return")

class SearchKnowledgeTool(BaseTool):
    name = "search_knowledge"
    description = (
        "Search the personal knowledge base and memories for relevant facts or prior context. "
        "HOW TO USE: 'search_knowledge(query=\"Who is the lead engineer?\", limit=3)'."
    )
    args_schema = SearchKnowledgeArgs

    async def run(self, query: str, limit: int = 5, **kwargs) -> Any:
        from tools.base import ToolResult
        user_id: str = kwargs.get("user_id")
        db_session: AsyncSession = kwargs.get("db_session")
        context_name: str = kwargs.get("context_name", "general")
        if not user_id or not db_session: return ToolResult(content="Context error", is_success=False)
        
        try:
            service = KnowledgeCoreService(db_session, user_id)
            ctx = await service.get_context(query=query, agent_id=context_name)
            if not ctx:
                return ToolResult(content="No knowledge found for the query.")
            return ToolResult(content=ctx.get("summary", "Found context."), data=ctx)
        except Exception as e:
            return ToolResult(content=f"Knowledge search failed: {e}", is_success=False)

class IngestKnowledgeArgs(BaseModel):
    content: str = Field(..., description="The fact or information to save")
    label: Optional[str] = Field(None, description="Optional label or topic for the knowledge")

class IngestKnowledgeTool(BaseTool):
    name = "ingest_knowledge"
    description = (
        "Store a new fact, preference, or observation into the long-term memory. "
        "ATTENTION: Avoid redundant storage of already known information. "
        "HOW TO USE: 'ingest_knowledge(content=\"The user prefers dark mode for all dashboards.\", label=\"Preference\")'."
    )
    args_schema = IngestKnowledgeArgs

    async def run(self, content: str, label: Optional[str] = None, **kwargs) -> Any:
        from tools.base import ToolResult
        user_id: str = kwargs.get("user_id")
        db_session: AsyncSession = kwargs.get("db_session")
        context_name: str = kwargs.get("context_name", "general")
        if not user_id or not db_session: return ToolResult(content="Context error", is_success=False)
        
        try:
            service = KnowledgeCoreService(db_session, user_id)
            txt = f"[{label}] {content}" if label else content
            record_id = await service.ingest_message(txt, "assistant", "global", context_name)
            return ToolResult(content=f"Successfully ingested knowledge with ID: {record_id}")
        except Exception as e:
            return ToolResult(content=f"Knowledge ingestion failed: {e}", is_success=False)
