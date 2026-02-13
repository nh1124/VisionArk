"""System tools: agent management, project operations, timers."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, get_user_id, make_result


class ListAgentsTool:
    definition = ToolDef(
        name="list_agents",
        description="List all available agents (System, Members, Peer Projects) for communication.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent, Project

            res_s = await db.execute(select(ProjectAgent).filter(ProjectAgent.agent_type == "SYSTEM", ProjectAgent.status == "active"))
            systems = res_s.scalars().all()

            res_m = await db.execute(select(ProjectAgent).filter(ProjectAgent.project_id == project_id, ProjectAgent.agent_type == "MEMBER", ProjectAgent.status == "active"))
            members = res_m.scalars().all()

            res_p = await db.execute(
                select(ProjectAgent).join(Project, ProjectAgent.project_id == Project.id).filter(
                    Project.user_id == user_id,
                    ProjectAgent.agent_type == "PROJECT",
                    ProjectAgent.status == "active",
                )
            )
            peers = res_p.scalars().all()

            lines = [f"Found {len(systems) + len(members) + len(peers)} available agents:"]
            for a in systems + members + peers:
                lines.append(f"- [{a.agent_type}] {a.id}: {a.display_name} ({a.role_name}) - {a.description or 'No description'}")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list agents: {e}")


class GetAgentProfileTool:
    definition = ToolDef(
        name="get_agent_profile",
        description="Retrieve detailed profile and capabilities for a specific agent ID.",
        parameters={
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "UUID of the agent to inspect"},
            },
            "required": ["agent_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        agent_id = call.arguments.get("agent_id", "")
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent

            res = await db.execute(select(ProjectAgent).filter(ProjectAgent.id == agent_id))
            agent = res.scalars().first()
            if not agent:
                return fail(call, f"Agent {agent_id} not found.")

            info = (
                f"Agent: {agent.display_name} ({agent.role_name})\n"
                f"Type: {agent.agent_type}\n"
                f"Description: {agent.description or 'None'}\n"
                f"Tools: {agent.tools or []}\n"
                f"Status: {agent.status}"
            )
            return make_result(call, info)
        except Exception as e:
            return fail(call, f"Failed to get agent profile: {e}")


class AskAgentTool:
    definition = ToolDef(
        name="ask_agent",
        description="Send a message or sub-task to another agent.",
        parameters={
            "type": "object",
            "properties": {
                "target_agent_id": {"type": "string", "description": "UUID of the target agent"},
                "message": {"type": "string", "description": "Message or instruction to send"},
                "blocking": {"type": "boolean", "description": "Wait for response (true) or fire-and-forget (false)"},
            },
            "required": ["target_agent_id", "message"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        target_id = call.arguments.get("target_agent_id", "")
        message = call.arguments.get("message", "")
        blocking = call.arguments.get("blocking", False)

        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        session_id = ctx.metadata.get("session_id")

        try:
            from infrastructure.queue.manager import QueueManager

            manager = QueueManager()
            await manager.enqueue(
                user_id=user_id,
                message=message,
                context={
                    "session_id": session_id,
                    "project_id": project_id,
                    "original_message": message,
                    "target_agent_id": target_id,
                },
            )
            return make_result(call, f"Message sent to agent {target_id}." + (" (non-blocking)" if not blocking else ""))
        except Exception as e:
            return fail(call, f"Failed to send message to agent: {e}")


class BroadcastSystemMessageTool:
    definition = ToolDef(
        name="broadcast_system_message",
        description="Send a notification to all active Project Hubs.",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Notification message"},
            },
            "required": ["message"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        message = call.arguments.get("message", "")
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import ProjectAgent, Project
            from infrastructure.queue.manager import QueueManager

            res = await db.execute(
                select(ProjectAgent).join(Project, ProjectAgent.project_id == Project.id).filter(
                    Project.user_id == user_id,
                    ProjectAgent.agent_type == "PROJECT",
                    ProjectAgent.status == "active",
                )
            )
            project_agents = res.scalars().all()

            manager = QueueManager()
            count = 0
            for agent in project_agents:
                await manager.enqueue(
                    user_id=user_id,
                    message=f"[SYSTEM BROADCAST] {message}",
                    context={"project_id": agent.project_id, "target_agent_id": agent.id},
                )
                count += 1

            return make_result(call, f"Broadcast sent to {count} project agents.")
        except Exception as e:
            return fail(call, f"Broadcast failed: {e}")


class ListUserProjectsTool:
    definition = ToolDef(
        name="list_user_projects",
        description="List all user projects with status and priority.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        user_id = get_user_id(ctx)
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import Project

            res = await db.execute(select(Project).filter(Project.user_id == user_id).order_by(Project.priority))
            projects = res.scalars().all()

            lines = [f"Found {len(projects)} projects:"]
            for p in projects:
                lines.append(f"- [{p.status}] {p.name} (id: {p.id}, priority: {p.priority})")

            return make_result(call, "\n".join(lines))
        except Exception as e:
            return fail(call, f"Failed to list projects: {e}")


class UpdateProjectTool:
    definition = ToolDef(
        name="update_project",
        description="Update project metadata (name, status, priority).",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "New project name"},
                "status": {"type": "string", "description": "New status: active, paused, archived"},
                "priority": {"type": "integer", "description": "Priority 1-5"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            from sqlalchemy import select
            from shared.database import Project

            res = await db.execute(select(Project).filter(Project.id == project_id))
            project = res.scalars().first()
            if not project:
                return fail(call, "Project not found.")

            if "name" in call.arguments:
                project.name = call.arguments["name"]
            if "status" in call.arguments:
                project.status = call.arguments["status"]
            if "priority" in call.arguments:
                project.priority = call.arguments["priority"]

            await db.commit()
            return make_result(call, f"Project '{project.name}' updated.")
        except Exception as e:
            return fail(call, f"Failed to update project: {e}")


class GetProjectHealthTool:
    definition = ToolDef(
        name="get_project_health",
        description="Analyze project health (agents, activity, status).",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            from sqlalchemy import select, func
            from shared.database import ProjectAgent, ChatMessage, ChatSession

            agents_res = await db.execute(select(func.count()).select_from(ProjectAgent).filter(ProjectAgent.project_id == project_id))
            agent_count = agents_res.scalar() or 0

            sessions_res = await db.execute(select(func.count()).select_from(ChatSession).filter(ChatSession.project_id == project_id))
            session_count = sessions_res.scalar() or 0

            info = (
                f"Project Health Report:\n"
                f"- Agents: {agent_count}\n"
                f"- Sessions: {session_count}\n"
                f"- Status: active"
            )
            return make_result(call, info)
        except Exception as e:
            return fail(call, f"Health check failed: {e}")


class SetTimerTool:
    definition = ToolDef(
        name="set_timer",
        description="Set a timer to notify the user after specified minutes.",
        parameters={
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Minutes until notification"},
                "message": {"type": "string", "description": "Notification message"},
            },
            "required": ["minutes", "message"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        minutes = call.arguments.get("minutes", 1)
        message = call.arguments.get("message", "Timer expired")
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)
        db = get_db(ctx)

        try:
            from shared.database import ScheduledTask

            task = ScheduledTask(
                id=str(uuid.uuid4()),
                user_id=user_id,
                project_id=project_id,
                task_type="TIMER",
                payload={"message": message},
                scheduled_at=datetime.utcnow() + timedelta(minutes=minutes),
                status="pending",
            )
            db.add(task)
            await db.flush()

            return make_result(call, f"Timer set for {minutes} minutes: {message}")
        except Exception as e:
            return fail(call, f"Failed to set timer: {e}")


class RaiseContinueTool:
    definition = ToolDef(
        name="raise_continue",
        description="Signal the reasoning loop to continue processing.",
        parameters={"type": "object", "properties": {}, "required": []},
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        return make_result(call, "Continue signal acknowledged.")
