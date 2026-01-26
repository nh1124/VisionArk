from .client import LineClient, get_line_client
from .api import router as line_router
from .agent_tools import SendLineMessageTool
# Import handlers to register them with the SDK
from . import handlers 

async def get_tools(user_id: str, db):
    """Return LINE tools if the service is active for the user."""
    from sqlalchemy import select
    from models.database import ServiceRegistry
    
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "line",
        ServiceRegistry.is_active == True
    ))
    if result.scalars().first():
        return [SendLineMessageTool()]
    return []

__all__ = ["LineClient", "get_line_client", "line_router", "get_tools"]
