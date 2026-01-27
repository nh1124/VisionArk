from .client import OutlookClient, get_outlook_client
from .api import router as outlook_router
from .agent_tools import ListOutlookEventsTool
from . import handlers

async def get_tools(user_id: str, db):
    """Return Outlook tools if the service is active for the user."""
    from sqlalchemy import select
    from models.database import ServiceRegistry
    
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "outlook",
        ServiceRegistry.is_active == True
    ))
    if result.scalars().first():
        return [ListOutlookEventsTool()]
    return []

__all__ = ["OutlookClient", "get_outlook_client", "outlook_router", "get_tools"]
