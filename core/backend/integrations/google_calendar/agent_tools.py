from va_sdk import BaseTool, ToolResult, IntegrationContext, BaseModel
from .client import get_google_calendar_client
from datetime import datetime
from typing import Any, Optional
from pydantic import Field

class ListCalendarEventsArgs(BaseModel):
    calendar_id: str = "primary"
    days: int = 7

class ListCalendarEventsTool(BaseTool):
    """Tool to list events from Google Calendar."""
    name = "list_calendar_events"
    description = "List events from a user's Google Calendar for a given time range."
    args_schema = ListCalendarEventsArgs
    
    async def run(self, ctx: IntegrationContext, **kwargs) -> Any:
        from va_sdk import ToolResult
        user_id = ctx.user_id
        db = ctx.db
        calendar_id = kwargs.get("calendar_id", "primary")
        days = kwargs.get("days", 7)
        
        client = await get_google_calendar_client(user_id, db)
        time_min = datetime.utcnow()
        from datetime import timedelta
        time_max = time_min + timedelta(days=days)
        
        events = await client.list_events(calendar_id, time_min=time_min, time_max=time_max)
        return ToolResult(
            content=f"Found {len(events)} events in calendar {calendar_id}.",
            data={"events": events}
        )

class CreateCalendarEventArgs(BaseModel):
    summary: str
    start_time: str
    end_time: str
    calendar_id: str = "primary"
    description: Optional[str] = None

class CreateCalendarEventTool(BaseTool):
    """Tool to create an event on Google Calendar."""
    name = "create_calendar_event"
    description = "Create a new event on the user's Google Calendar."
    args_schema = CreateCalendarEventArgs
    
    async def run(self, ctx: IntegrationContext, **kwargs) -> Any:
        from va_sdk import ToolResult
        user_id = ctx.user_id
        db = ctx.db
        summary = kwargs.get("summary")
        start_time = kwargs.get("start_time")
        end_time = kwargs.get("end_time")
        calendar_id = kwargs.get("calendar_id", "primary")
        description = kwargs.get("description")

        client = await get_google_calendar_client(user_id, db)
        event_data = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": f"{start_time}Z"},
            "end": {"dateTime": f"{end_time}Z"},
        }
        event = await client.create_event(calendar_id, event_data)
        return ToolResult(
            content=f"Created event '{summary}' in calendar {calendar_id}.",
            data={"event": event}
        )
