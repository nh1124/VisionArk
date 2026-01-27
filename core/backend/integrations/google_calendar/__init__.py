from .client import GoogleCalendarClient, get_google_calendar_client
from .api import router as google_calendar_router
from .agent_tools import ListCalendarEventsTool, CreateCalendarEventTool
# Import handlers to register them with the SDK
from . import handlers

async def get_tools(user_id: str, db):
    """Return Google Calendar tools if the service is active for the user."""
    from sqlalchemy import select
    from models.database import ServiceRegistry
    
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "google_calendar",
        ServiceRegistry.is_active == True
    ))
    if result.scalars().first():
        return [ListCalendarEventsTool(), CreateCalendarEventTool()]
    return []

__all__ = ["GoogleCalendarClient", "get_google_calendar_client", "google_calendar_router", "get_tools"]
