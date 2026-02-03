from va_sdk import BaseTool, BaseModel, IntegrationContext
from integrations.knowledge_core.service import KnowledgeCoreService
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional
from pydantic import Field

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

    async def run(self, query: str, limit: int = 5, ctx: IntegrationContext = None, **kwargs) -> Any:
        from tools.base import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        
        try:
            service = KnowledgeCoreService(ctx.db, ctx.user_id)
            context_name = kwargs.get("context_name", "general")
            res = await service.get_context(query=query, agent_id=context_name)
            if not res:
                return ToolResult(content="No knowledge found for the query.")
            return ToolResult(content=res.get("summary", "Found context."), data=res)
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

    async def run(self, content: str, label: Optional[str] = None, ctx: IntegrationContext = None, **kwargs) -> Any:
        from tools.base import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        
        try:
            service = KnowledgeCoreService(ctx.db, ctx.user_id)
            context_name = kwargs.get("context_name", "general")
            txt = f"[{label}] {content}" if label else content
            record_id = await service.ingest_message(txt, "assistant", "global", context_name)
            return ToolResult(content=f"Successfully ingested knowledge with ID: {record_id}")
        except Exception as e:
            return ToolResult(content=f"Knowledge ingestion failed: {e}", is_success=False)
