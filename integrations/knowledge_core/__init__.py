from .service import KnowledgeCoreService
from .agent_tools import SearchKnowledgeTool, IngestKnowledgeTool

async def get_tools(user_id: str, db):
    """Return KnowledgeCore tools if the service is active for the user."""
    from sqlalchemy import select
    from shared.database import ServiceRegistry
    
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "knowledge_core",
        ServiceRegistry.is_active == True
    ))
    if result.scalars().first():
        return [SearchKnowledgeTool(), IngestKnowledgeTool()]
    return []

__all__ = ["KnowledgeCoreService", "get_tools"]
