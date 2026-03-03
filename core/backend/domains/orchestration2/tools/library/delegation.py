"""Delegation and member-listing tools for the orchestration2 engine."""

from __future__ import annotations

import logging
from typing import Any

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, make_result

logger = logging.getLogger(__name__)


class DelegateTaskTool:
    definition = ToolDef(
        name="delegate_task",
        description=(
            "Delegate a subtask to a specialized sub-agent. "
            "Use this when a task requires expertise outside your current role. "
            "Available agents: 'researcher' (research & information gathering), "
            "'writer' (document creation & authoring), 'reviewer' (research & review). "
            "The delegated task runs synchronously and returns the result."
        ),
        parameters={
            "type": "object",
            "properties": {
                "child_agent": {
                    "type": "string",
                    "description": "Name of sub-agent: 'researcher', 'writer', or 'reviewer'",
                },
                "task": {
                    "type": "string",
                    "description": "Detailed task description for the sub-agent",
                },
                "timeout_sec": {
                    "type": "integer",
                    "description": "Max wait time in seconds (default: 120)",
                },
            },
            "required": ["child_agent", "task"],
        },
    )

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        child_agent = call.arguments.get("child_agent", "")
        task = call.arguments.get("task", "")
        timeout_sec = call.arguments.get("timeout_sec")

        if not child_agent or not task:
            return fail(call, "child_agent and task are required")

        logger.info(
            "DelegateTaskTool: delegating to '%s' (run_id=%s)", child_agent, ctx.run_id
        )

        try:
            result = await self._engine.delegate_task(
                ctx.run_id, child_agent, task, timeout_sec=timeout_sec
            )
            if result.status == "completed":
                content = (
                    result.output_message.content
                    if result.output_message
                    else "(no output)"
                )
                return make_result(
                    call,
                    f"[Delegation result from '{child_agent}']\n{content}",
                )
            else:
                return fail(
                    call,
                    f"Sub-agent '{child_agent}' failed: {result.error or 'Unknown error'}",
                )
        except Exception as exc:
            logger.exception("DelegateTaskTool error: %s", exc)
            return fail(call, f"Delegation error: {exc}")


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
