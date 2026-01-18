from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool, NoArgs
from sqlalchemy.ext.asyncio import AsyncSession
from tools.lbs_tools import update_user_condition, get_current_condition, reset_user_condition

class GetCurrentConditionTool(BaseTool):
    name = "get_current_condition"
    description = (
        "Retrieve the user's current reported physical and mental energy metrics (0-10). "
        "HOW TO USE: 'get_current_condition()'."
    )
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id: return {"success": False, "message": "Context error"}
        
        try:
            # Reusing the existing function for now as it's already well-implemented
            from tools.lbs_tools import get_current_condition as get_cond
            res = await get_cond(session=session, user_id=user_id)
            return {"success": True, "message": f"Condition: {res}", "data": res}
        except Exception as e:
            return {"success": False, "message": f"Failed to get condition: {e}"}

class UpdateUserConditionArgs(BaseModel):
    physical: Optional[int] = Field(None, description="Physical energy level (0-10)")
    mental: Optional[int] = Field(None, description="Mental energy level (0-10)")
    notes: Optional[str] = Field(None, description="Notes about the user's condition")

class UpdateUserConditionTool(BaseTool):
    name = "update_user_condition"
    description = (
        "Update the user's reported physical and mental energy levels. "
        "ATTENTION: Use this when the user explicitly provides condition updates. "
        "HOW TO USE: 'update_user_condition(physical=8, mental=9, notes=\"Feeling refreshed after sleep.\")'."
    )
    args_schema = UpdateUserConditionArgs

    async def run(self, **args) -> Any:
        session: AsyncSession = args.pop("session", None)
        user_id: str = args.pop("user_id", None)
        if not session or not user_id: return {"success": False, "message": "Context error"}
        
        try:
            from tools.lbs_tools import update_user_condition as upd_cond
            res = await upd_cond(session=session, user_id=user_id, **args)
            return {"success": True, "message": "Condition updated", "data": res}
        except Exception as e:
            return {"success": False, "message": f"Failed to update condition: {e}"}
