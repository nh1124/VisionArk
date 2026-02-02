from typing import Optional, List, Dict, Any
from va_sdk import BaseTool, BaseModel
from .client import get_outlook_client
from datetime import datetime, timedelta

class ListOutlookEventsArgs(BaseModel):
    days: int = 7

class ListOutlookEventsTool(BaseTool):
    """Tool to list events from Outlook Calendar."""
    name = "list_outlook_events"
    description = "List events from a user's Outlook Calendar for a given time range."
    args_schema = ListOutlookEventsArgs
    
    async def run(self, **kwargs) -> Any:
        from tools.base import ToolResult
        user_id = kwargs.get("user_id")
        db = kwargs.get("db_session")
        days = kwargs.get("days", 7)
        
        client = await get_outlook_client(user_id, db)
        time_min = datetime.utcnow()
        time_max = time_min + timedelta(days=days)
        events = await client.list_events(time_min=time_min, time_max=time_max)
        return ToolResult(
            content=f"Found {len(events)} events in Outlook calendar.",
            data={"events": events}
        )
