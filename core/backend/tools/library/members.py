from typing import Any, Optional, Dict, List, Literal
from pydantic import BaseModel, Field
import uuid
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from tools.base import BaseTool, NoArgs
from models.database import Node

class ListMembersTool(BaseTool):
    name = "list_members"
    description = "List all dynamic member agents registered for the current project."
    args_schema = NoArgs

    async def run(self, **kwargs) -> Any:
        from tools.base import ToolResult
        db_session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        if not db_session or not project_id:
            return ToolResult(content="Missing context (session or project_id)", is_success=False)
        
        try:
            result = await db_session.execute(select(Node).where(
                Node.project_id == project_id,
                Node.node_type == "MEMBER",
                Node.status == "active"
            ))
            member_nodes = result.scalars().all()
            
            if not member_nodes:
                return ToolResult(content="No dynamic members found for this project.", data={"members": []})

            members_list = []
            for n in member_nodes:
                members_list.append({
                    "id": n.id,
                    "role_name": n.role_name,
                    "display_name": n.display_name,
                    "tools": n.tools or [],
                    "has_custom_prompt": bool(n.system_prompt)
                })

            msg = f"Found {len(members_list)} members:\n"
            for m in members_list:
                msg += f"- {m['role_name']} ({m['display_name']}): tools={m['tools']}\n"
            
            return ToolResult(content=msg, data={"members": members_list})
        except Exception as e:
            return ToolResult(content=f"Failed to list members: {e}", is_success=False)

class ManageMemberArgs(BaseModel):
    action: Literal["create", "update", "delete"] = Field(..., description="Action to perform")
    role_name: str = Field(..., description="The slug name of the member (e.g., 'writer')")
    display_name: Optional[str] = Field(None, description="Human readable name")
    description: Optional[str] = Field(None, description="1-2 sentence summary of the member's expertise")
    system_prompt: Optional[str] = Field(None, description="The custom instructions for this member")
    tools: Optional[List[str]] = Field(None, description="List of tool names allowed for this member")

class ManageMemberTool(BaseTool):
    name = "manage_member"
    description = "Create, update, or delete a dynamic member agent for this project."
    args_schema = ManageMemberArgs

    async def run(self, action: str, role_name: str, **kwargs) -> Any:
        from tools.base import ToolResult
        db_session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        if not db_session or not project_id:
            return ToolResult(content="Missing context (session or project_id)", is_success=False)

        role_name = role_name.lower().strip()
        
        try:
            if action == "create":
                # Check exists
                res = await db_session.execute(select(Node).where(
                    Node.project_id == project_id, 
                    Node.role_name == role_name,
                    Node.node_type == "MEMBER"
                ))
                if res.scalars().first():
                    return ToolResult(content=f"Member '{role_name}' already exists. Use 'update' instead.", is_success=False)
                
                new_node = Node(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    node_type="MEMBER",
                    role_name=role_name,
                    display_name=kwargs.get("display_name") or role_name.title(),
                    description=kwargs.get("description"),
                    system_prompt=kwargs.get("system_prompt") or f"You are a helpful '{role_name}' assistant.",
                    tools=kwargs.get("tools") or [],
                    status="active",
                    version=1
                )
                db_session.add(new_node)
                await db_session.commit()
                return ToolResult(content=f"✅ Created member: {role_name}")

            elif action == "update":
                res = await db_session.execute(select(Node).where(
                    Node.project_id == project_id, 
                    Node.role_name == role_name,
                    Node.node_type == "MEMBER"
                ))
                node = res.scalars().first()
                if not node:
                    return ToolResult(content=f"Member '{role_name}' not found.", is_success=False)
                
                if "display_name" in kwargs and kwargs["display_name"]:
                    node.display_name = kwargs["display_name"]
                if "description" in kwargs and kwargs["description"]:
                    node.description = kwargs["description"]
                if "system_prompt" in kwargs and kwargs["system_prompt"]:
                    node.system_prompt = kwargs["system_prompt"]
                if "tools" in kwargs and kwargs["tools"]:
                    node.tools = kwargs["tools"]
                
                await db_session.commit()
                return ToolResult(content=f"✅ Updated member: {role_name}")

            elif action == "delete":
                res = await db_session.execute(select(Node).where(
                    Node.project_id == project_id, 
                    Node.role_name == role_name,
                    Node.node_type == "MEMBER"
                ))
                node = res.scalars().first()
                if not node:
                    return ToolResult(content=f"Member '{role_name}' not found.", is_success=False)
                
                await db_session.delete(node)
                await db_session.commit()
                return ToolResult(content=f"🗑️ Deleted member: {role_name}")

        except Exception as e:
            if db_session: await db_session.rollback()
            return ToolResult(content=f"Operation failed: {e}", is_success=False)

class UpdateNodeDescriptionArgs(BaseModel):
    description: str = Field(..., description="The new 1-2 sentence description for this node")
    target_id: Optional[str] = Field(None, description="The UUID of the node to update. Pass None (null) to update your own description.")

class UpdateNodeDescriptionTool(BaseTool):
    name = "update_node_description"
    description = (
        "Update the 'Short Description' for a node. "
        "Use this to refine your own expertise summary (pass target_id=None) or update another node's description "
        "to help the Project Node delegate more effectively."
    )
    args_schema = UpdateNodeDescriptionArgs

    async def run(self, description: str, target_id: Optional[str] = None, **kwargs) -> Any:
        from tools.base import ToolResult
        db_session: AsyncSession = kwargs.get("db_session")
        project_id: str = kwargs.get("project_id")
        current_node_id: str = kwargs.get("node_id")
        
        if not db_session or not project_id:
            return ToolResult(content="Missing context (session or project_id)", is_success=False)

        try:
            if target_id:
                # Update target node by ID
                res = await db_session.execute(select(Node).where(Node.id == target_id))
                node = res.scalars().first()
                if not node:
                    return ToolResult(content=f"Node with ID '{target_id}' not found.", is_success=False)
            else:
                # Update self
                if not current_node_id:
                    return ToolResult(content="Missing node_id to update self.", is_success=False)
                res = await db_session.execute(select(Node).where(Node.id == current_node_id))
                node = res.scalars().first()
                if not node:
                    return ToolResult(content="Current node record not found.", is_success=False)

            node.description = description
            await db_session.commit()
            return ToolResult(content=f"✅ Updated description for {node.display_name or node.role_name or 'unnamed node'}.")

        except Exception as e:
            if db_session: await db_session.rollback()
            return ToolResult(content=f"Failed to update description: {e}", is_success=False)
