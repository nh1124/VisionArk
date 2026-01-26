from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool, NoArgs
from sqlalchemy.ext.asyncio import AsyncSession
from integrations.lbs.agent_tools import update_user_condition, get_current_condition, reset_user_condition

class GetCurrentConditionTool(BaseTool):
    name = "get_current_condition"
    description = (
        "Retrieve the user's current reported physical and mental energy metrics (0-10). "
        "HOW TO USE: 'get_current_condition()'."
    )
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id: return {"success": False, "message": "Context error"}
        
        try:
            # Reusing the existing function for now as it's already well-implemented
            from integrations.lbs.agent_tools import get_current_condition as get_cond
            res = await get_cond(db_session=db_session, user_id=user_id)
            return {"success": True, "message": f"Condition: {res}", "data": res}
        except Exception as e:
            return {"success": False, "message": f"Failed to get condition: {e}"}

class UpdateUserConditionArgs(BaseModel):
    cognitive_fatigue: int = Field(..., description="Cognitive fatigue level (0-5)")
    notes: Optional[str] = Field(None, description="Notes about the user's condition")
    target_date: Optional[str] = Field(None, description="Target date for the condition update")

class UpdateUserConditionTool(BaseTool):
    name = "update_user_condition"
    description = (
        "Update the user's reported cognitive fatigue level. "
        "ATTENTION: Use this when the user explicitly provides condition updates. "
        "HOW TO USE: 'update_user_condition(cognitive_fatigue=4, notes=\"Feeling refreshed after sleep.\", target_date=\"2025-01-01\")'."
    )
    args_schema = UpdateUserConditionArgs

    async def run(self, cognitive_fatigue: int, **kwargs) -> Any:
        db_session: AsyncSession = kwargs.pop("db_session", None)
        user_id: str = kwargs.pop("user_id", None)
        if not db_session or not user_id: return {"success": False, "message": "Context error"}
        
        try:
            from integrations.lbs.agent_tools import update_user_condition as upd_cond
            res = await upd_cond(db_session=db_session, user_id=user_id, cognitive_fatigue=cognitive_fatigue, **kwargs)
            return {"success": True, "message": "Condition updated", "data": res}
        except Exception as e:
            return {"success": False, "message": f"Failed to update condition: {e}"}
