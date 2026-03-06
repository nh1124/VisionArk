"""Delegation and member-listing tools for the orchestration2 engine."""

from __future__ import annotations

import json
import logging
from typing import Any

from domains.orchestration2.services.delegation_service import DelegationService
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
            "By default the delegation runs synchronously, but mode='async' can return immediately."
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
                "mode": {
                    "type": "string",
                    "enum": ["sync", "async"],
                    "description": "Delegation mode. sync waits for completion; async returns delegation_id immediately.",
                },
                "request_id": {
                    "type": "string",
                    "description": "Optional idempotency key. Repeated calls with same key reuse existing delegation.",
                },
                "context_scope": {
                    "type": "string",
                    "description": "Optional context scope hint (e.g. 'session').",
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
        mode = (call.arguments.get("mode") or "sync").strip().lower()
        request_id = call.arguments.get("request_id")
        context_scope = call.arguments.get("context_scope")

        if not child_agent or not task:
            return fail(call, "child_agent and task are required")
        if mode not in {"sync", "async"}:
            return fail(call, "mode must be 'sync' or 'async'")

        logger.info(
            "DelegateTaskTool: delegating to '%s' (run_id=%s)", child_agent, ctx.run_id
        )

        try:
            service = DelegationService(self._engine, ctx.metadata.get("db_session"))
            result = await service.delegate(
                parent_run_id=ctx.run_id,
                child_agent=child_agent,
                task=task,
                timeout_sec=timeout_sec,
                mode=mode,
                request_id=request_id,
                context_scope=context_scope,
                runtime_metadata=ctx.metadata,
            )

            if mode == "async":
                return make_result(
                    call,
                    json.dumps(result, ensure_ascii=False),
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


class WaitForDelegationTool:
    definition = ToolDef(
        name="wait_for_delegation",
        description=(
            "Block until a delegated child run finishes and return its result. "
            "Use after delegate_task(mode='async')."
        ),
        parameters={
            "type": "object",
            "properties": {
                "delegation_id": {
                    "type": "string",
                    "description": "Delegation ID returned by delegate_task(mode='async').",
                },
                "timeout_sec": {
                    "type": "integer",
                    "description": "Optional timeout in seconds.",
                },
                "ack": {
                    "type": "boolean",
                    "description": "If true, marks the result as acknowledged after receipt.",
                },
            },
            "required": ["delegation_id"],
        },
    )

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        delegation_id = str(call.arguments.get("delegation_id") or "").strip()
        timeout_sec = call.arguments.get("timeout_sec")
        ack = bool(call.arguments.get("ack", False))
        if not delegation_id:
            return fail(call, "delegation_id is required")

        try:
            service = DelegationService(self._engine, ctx.metadata.get("db_session"))
            result = await service.wait_for_delegation(
                delegation_id=delegation_id,
                timeout_sec=timeout_sec,
                ack=ack,
            )
            payload = {
                "delegation_id": result.delegation_id,
                "child_run_id": result.child_run_id,
                "status": result.status.value,
                "output": result.output_message.content if result.output_message else "",
                "error": result.error,
                "delivery_status": (
                    result.delivery_status.value
                    if hasattr(result.delivery_status, "value")
                    else str(result.delivery_status)
                ),
                "delivery_cursor": result.delivery_cursor,
            }
            return make_result(call, json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logger.exception("WaitForDelegationTool error: %s", exc)
            return fail(call, f"wait_for_delegation error: {exc}")


class ReceiveDelegationResultsTool:
    definition = ToolDef(
        name="receive_delegation_results",
        description=(
            "Receive delegated results since a cursor for the current parent run. "
            "Supports ack to prevent duplicate delivery."
        ),
        parameters={
            "type": "object",
            "properties": {
                "since_cursor": {
                    "type": "integer",
                    "description": "Return results with delivery_cursor greater than this value.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 20).",
                },
                "ack": {
                    "type": "boolean",
                    "description": "If true, acknowledge returned results.",
                },
            },
            "required": [],
        },
    )

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        since_cursor = int(call.arguments.get("since_cursor", 0) or 0)
        limit = int(call.arguments.get("limit", 20) or 20)
        ack = bool(call.arguments.get("ack", False))
        limit = max(1, min(limit, 100))

        try:
            service = DelegationService(self._engine, ctx.metadata.get("db_session"))
            payload = await service.receive_results(
                parent_run_id=ctx.run_id,
                since_cursor=since_cursor,
                limit=limit,
                ack=ack,
            )
            return make_result(call, json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logger.exception("ReceiveDelegationResultsTool error: %s", exc)
            return fail(call, f"receive_delegation_results error: {exc}")


class ListDelegationsTool:
    definition = ToolDef(
        name="list_delegations",
        description=(
            "List delegation requests for the current parent run. "
            "Useful for checking pending/completed child tasks."
        ),
        parameters={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of delegations to return (default: 20, max: 100).",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "completed", "failed", "timeout"],
                    "description": "Optional status filter.",
                },
                "child_agent": {
                    "type": "string",
                    "description": "Optional child agent name filter (e.g. researcher).",
                },
                "include_output": {
                    "type": "boolean",
                    "description": "If true, includes output text for completed delegations.",
                },
            },
            "required": [],
        },
    )

    def __init__(self, engine: Any) -> None:
        self._engine = engine

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        limit = int(call.arguments.get("limit", 20) or 20)
        status = str(call.arguments.get("status") or "").strip().lower() or None
        child_agent = str(call.arguments.get("child_agent") or "").strip() or None
        include_output = bool(call.arguments.get("include_output", False))
        if status and status not in {"pending", "completed", "failed", "timeout"}:
            return fail(call, "status must be one of: pending, completed, failed, timeout")

        try:
            service = DelegationService(self._engine, ctx.metadata.get("db_session"))
            payload = await service.list_delegations(
                parent_run_id=ctx.run_id,
                limit=limit,
                status=status,
                child_agent=child_agent,
                include_output=include_output,
            )
            return make_result(call, json.dumps(payload, ensure_ascii=False))
        except Exception as exc:
            logger.exception("ListDelegationsTool error: %s", exc)
            return fail(call, f"list_delegations error: {exc}")


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
