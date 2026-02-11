from .client import LBSClient, TaskStatus, get_lbs_client
from .api import router as lbs_router
async def get_tools(user_id: str, db):
    """Return LBS tools if the service is active for the user."""
    from sqlalchemy import select
    from shared.database import ServiceRegistry
    from .agent_tools import (
        ListTasksTool, CreateTaskTool, UpdateTaskTool, DeleteTaskTool,
        CompleteLBSTaskTool, GetLBSScheduleTool, GetLoadOnDayTool,
        GetLoadInPeriodTool, ManageTaskExceptionTool, ListExceptionsTool
    )
    
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "lbs",
        ServiceRegistry.is_active == True
    ))
    if result.scalars().first():
        return [
            ListTasksTool(), CreateTaskTool(), UpdateTaskTool(), DeleteTaskTool(),
            CompleteLBSTaskTool(), GetLBSScheduleTool(), GetLoadOnDayTool(),
            GetLoadInPeriodTool(), ManageTaskExceptionTool(), ListExceptionsTool()
        ]
    return []

__all__ = ["LBSClient", "TaskStatus", "lbs_router", "get_lbs_client", "get_tools"]
