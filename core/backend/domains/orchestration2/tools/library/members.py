"""Member management tools: list, create, update, delete project members."""

from __future__ import annotations

import uuid

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, make_result


class ListMembersTool:
    definition = ToolDef(
        name="list_members",
        description="List all dynamic member agents for the current project.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        project_id = get_project_id(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent

            result = await db.execute(
                select(ProjectAgent).where(
                    ProjectAgent.project_id == project_id,
                    ProjectAgent.agent_type == "MEMBER",
                    ProjectAgent.status == "active",
                )
            )
            members = result.scalars().all()

            if not members:
                return make_result(call, "No dynamic members found for this project.")

            lines = [f"Found {len(members)} members:"]
            for m in members:
                lines.append(f"- {m.role_name} ({m.display_name}): tools={m.tools or []}")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list members: {e}")


class ManageMemberTool:
    definition = ToolDef(
        name="manage_member",
        description="Create, update, or delete a dynamic member agent for this project.",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: create, update, or delete"},
                "role_name": {"type": "string", "description": "Slug name of the member (e.g., 'writer')"},
                "display_name": {"type": "string", "description": "Human-readable name"},
                "description": {"type": "string", "description": "1-2 sentence summary of expertise"},
                "system_prompt": {"type": "string", "description": "Custom instructions for this member"},
                "tools": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tool names allowed for this member",
                },
            },
            "required": ["action", "role_name"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        action = call.arguments.get("action", "")
        role_name = call.arguments.get("role_name", "").lower().strip()
        db = get_db(ctx)
        project_id = get_project_id(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent

            if action == "create":
                res = await db.execute(
                    select(ProjectAgent).where(
                        ProjectAgent.project_id == project_id,
                        ProjectAgent.role_name == role_name,
                        ProjectAgent.agent_type == "MEMBER",
                    )
                )
                if res.scalars().first():
                    return fail(call, f"Member '{role_name}' already exists. Use 'update' instead.")

                new_agent = ProjectAgent(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    agent_type="MEMBER",
                    role_name=role_name,
                    display_name=call.arguments.get("display_name") or role_name.title(),
                    description=call.arguments.get("description"),
                    system_prompt=call.arguments.get("system_prompt") or f"You are a helpful '{role_name}' assistant.",
                    tools=call.arguments.get("tools") or [],
                    status="active",
                    version=1,
                )
                db.add(new_agent)
                await db.commit()
                return make_result(call, f"Created member: {role_name}")

            elif action == "update":
                res = await db.execute(
                    select(ProjectAgent).where(
                        ProjectAgent.project_id == project_id,
                        ProjectAgent.role_name == role_name,
                        ProjectAgent.agent_type == "MEMBER",
                    )
                )
                agent = res.scalars().first()
                if not agent:
                    return fail(call, f"Member '{role_name}' not found.")

                if call.arguments.get("display_name"):
                    agent.display_name = call.arguments["display_name"]
                if call.arguments.get("description"):
                    agent.description = call.arguments["description"]
                if call.arguments.get("system_prompt"):
                    agent.system_prompt = call.arguments["system_prompt"]
                if call.arguments.get("tools"):
                    agent.tools = call.arguments["tools"]

                await db.commit()
                return make_result(call, f"Updated member: {role_name}")

            elif action == "delete":
                res = await db.execute(
                    select(ProjectAgent).where(
                        ProjectAgent.project_id == project_id,
                        ProjectAgent.role_name == role_name,
                        ProjectAgent.agent_type == "MEMBER",
                    )
                )
                agent = res.scalars().first()
                if not agent:
                    return fail(call, f"Member '{role_name}' not found.")

                await db.delete(agent)
                await db.commit()
                return make_result(call, f"Deleted member: {role_name}")

            else:
                return fail(call, f"Unknown action: {action}")

        except Exception as e:
            await db.rollback()
            return fail(call, f"Member operation failed: {e}")


class UpdateAgentDescriptionTool:
    definition = ToolDef(
        name="update_agent_description",
        description="Update the short description for an agent.",
        parameters={
            "type": "object",
            "properties": {
                "description": {"type": "string", "description": "New 1-2 sentence description"},
                "target_id": {"type": "string", "description": "UUID of agent to update (null = self)"},
            },
            "required": ["description"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        description = call.arguments.get("description", "")
        target_id = call.arguments.get("target_id")
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent

            if target_id:
                res = await db.execute(select(ProjectAgent).where(ProjectAgent.id == target_id))
            else:
                agent_id = ctx.metadata.get("agent_id")
                if not agent_id:
                    return fail(call, "Missing agent_id to update self.")
                res = await db.execute(select(ProjectAgent).where(ProjectAgent.id == agent_id))

            agent = res.scalars().first()
            if not agent:
                return fail(call, "Agent not found.")

            agent.description = description
            await db.commit()
            return make_result(call, f"Updated description for {agent.display_name or agent.role_name}.")
        except Exception as e:
            await db.rollback()
            return fail(call, f"Failed to update description: {e}")
