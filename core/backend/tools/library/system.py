from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from tools.base import BaseTool
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

class AskNodeArgs(BaseModel):
    target: str = Field(..., description="The ID of the target project/node (e.g., a UUID)")
    message: str = Field(..., description="The content of the message to send")

class AskNodeTool(BaseTool):
    name = "ask_node"
    description = (
        "Send a message or a sub-task to another project node. "
        "ATTENTION: Use this for cross-project coordination. Always use project_id (UUID) as the target."
        "HOW TO USE: 'ask_node(target=\"hub\", message=\"What are the findings for phase 1?\")'."
    )
    args_schema = AskNodeArgs

    async def run(self, target: str, message: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error: session or user_id missing"}
        
        try:
            from nodes.project.project_node import ProjectNode
            ctx = {'user_id': user_id, 'db_session': session, 'project_id': target}
            node = ProjectNode(ctx)
            resp = await node.process(message)
            return {"success": True, "message": f"Response from {target}: {resp}", "data": {"response": resp}}
        except Exception as e:
            return {"success": False, "message": f"Failed to ask node {target}: {e}"}

class DelegateTaskArgs(BaseModel):
    role: str = Field(..., description="The role of the member to delegate to (planner, researcher, ruler, advocate)")
    instruction: str = Field(..., description="Detailed instructions for the task")

class DelegateTaskTool(BaseTool):
    name = "delegate_to_member"
    description = (
        "Delegate a task to a specialized member agent (Planner, Researcher, Ruler, Advocate). "
        "ATTENTION: Ensure the instruction is specific and actionable. This is an internal delegation within the current project. "
        "HOW TO USE: 'delegate_to_member(role=\"researcher\", instruction=\"Search for recent papers on LLM optimization.\")'."
    )
    args_schema = DelegateTaskArgs

    async def run(self, role: str, instruction: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        user_id: str = kwargs.get("user_id")
        project_id: str = kwargs.get("project_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error: session or user_id missing"}

        try:
            members = kwargs.get("members", {})
            role_lower = role.lower()
            
            if role_lower in members:
                node = members[role_lower]
                resp = await node.process(instruction)
                return {"success": True, "message": f"Result from {role}:\n{resp}"}
            
            # Fallback/Legacy logic if members not in context (cross-compatibility)
            from nodes.members.planner import PlannerNode
            from nodes.members.researcher import ResearcherNode
            from nodes.members.ruler import RulerNode
            from nodes.members.advocate import AdvocateNode
            
            role_map = {
                "planner": PlannerNode,
                "researcher": ResearcherNode,
                "ruler": RulerNode,
                "advocate": AdvocateNode
            }
            
            if role_lower not in role_map:
                return {"success": False, "message": f"Invalid role: {role}. Available: {list(members.keys()) or list(role_map.keys())}"}
            
            NodeClass = role_map[role_lower]
            ctx = {'user_id': user_id, 'db_session': session, 'project_id': project_id}
            node = NodeClass(ctx, status_callback=self._status_callback)
            resp = await node.process(instruction)
            return {"success": True, "message": f"Result from {role}:\n{resp}"}
        except Exception as e:
            return {"success": False, "message": f"Delegation failed: {e}"}


