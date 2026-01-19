from typing import Any, Optional, Dict, List, Literal
from pydantic import BaseModel, Field
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from tools.base import BaseTool, NoArgs
from models.database import AgentProfile

class ListMembersTool(BaseTool):
    name = "list_members"
    description = "List all dynamic member agents registered for the current project."
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        node_id: str = kwargs.get("node_id")
        if not session or not node_id:
            return {"success": False, "message": "Missing context (session or node_id)"}

        try:
            result = await session.execute(select(AgentProfile).where(
                AgentProfile.node_id == node_id,
                AgentProfile.is_active == True
            ))
            profiles = result.scalars().all()
            
            if not profiles:
                return {"success": True, "message": "No dynamic members found for this project.", "data": {"members": []}}

            members_list = []
            for p in profiles:
                members_list.append({
                    "role_name": p.role_name,
                    "display_name": p.display_name,
                    "tools": p.tools or [],
                    "has_custom_prompt": bool(p.system_prompt)
                })

            msg = f"Found {len(members_list)} members:\n"
            for m in members_list:
                msg += f"- {m['role_name']} ({m['display_name']}): tools={m['tools']}\n"
            
            return {"success": True, "message": msg, "data": {"members": members_list}}
        except Exception as e:
            return {"success": False, "message": f"Failed to list members: {e}"}

class ManageMemberArgs(BaseModel):
    action: Literal["create", "update", "delete"] = Field(..., description="Action to perform")
    role_name: str = Field(..., description="The slug name of the member (e.g., 'writer')")
    display_name: Optional[str] = Field(None, description="Human readable name")
    system_prompt: Optional[str] = Field(None, description="The custom instructions for this member")
    tools: Optional[List[str]] = Field(None, description="List of tool names allowed for this member")

class ManageMemberTool(BaseTool):
    name = "manage_member"
    description = "Create, update, or delete a dynamic member agent for this project."
    args_schema = ManageMemberArgs

    async def run(self, action: str, role_name: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("session")
        node_id: str = kwargs.get("node_id")
        if not session or not node_id:
            return {"success": False, "message": "Missing context"}

        role_name = role_name.lower().strip()
        
        try:
            if action == "create":
                # Check exists
                res = await session.execute(select(AgentProfile).where(AgentProfile.node_id == node_id, AgentProfile.role_name == role_name))
                if res.scalars().first():
                    return {"success": False, "message": f"Member '{role_name}' already exists. Use 'update' instead."}
                
                new_profile = AgentProfile(
                    id=str(uuid.uuid4()),
                    node_id=node_id,
                    role_name=role_name,
                    display_name=kwargs.get("display_name") or role_name.title(),
                    system_prompt=kwargs.get("system_prompt") or f"You are a helpful '{role_name}' assistant.",
                    tools=kwargs.get("tools") or [],
                    is_active=True,
                    version=1
                )
                session.add(new_profile)
                await session.commit()
                return {"success": True, "message": f"✅ Created member: {role_name}"}

            elif action == "update":
                res = await session.execute(select(AgentProfile).where(AgentProfile.node_id == node_id, AgentProfile.role_name == role_name))
                profile = res.scalars().first()
                if not profile:
                    return {"success": False, "message": f"Member '{role_name}' not found."}
                
                if "display_name" in kwargs and kwargs["display_name"]:
                    profile.display_name = kwargs["display_name"]
                if "system_prompt" in kwargs and kwargs["system_prompt"]:
                    profile.system_prompt = kwargs["system_prompt"]
                if "tools" in kwargs and kwargs["tools"]:
                    profile.tools = kwargs["tools"]
                
                await session.commit()
                return {"success": True, "message": f"✅ Updated member: {role_name}"}

            elif action == "delete":
                res = await session.execute(select(AgentProfile).where(AgentProfile.node_id == node_id, AgentProfile.role_name == role_name))
                profile = res.scalars().first()
                if not profile:
                    return {"success": False, "message": f"Member '{role_name}' not found."}
                
                await session.delete(profile)
                await session.commit()
                return {"success": True, "message": f"🗑️ Deleted member: {role_name}"}

        except Exception as e:
            if session: await session.rollback()
            return {"success": False, "message": f"Operation failed: {e}"}
