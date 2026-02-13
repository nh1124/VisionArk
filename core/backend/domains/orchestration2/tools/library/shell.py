"""Shell tool: queue system commands for human approval."""

from __future__ import annotations

import logging

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_project_id, get_user_id, make_result

logger = logging.getLogger(__name__)


class RunSafeShellTool:
    definition = ToolDef(
        name="run_safe_shell",
        description=(
            "Queue a system command for human approval before execution. "
            "Commands are NOT executed immediately."
        ),
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to execute"},
                "cwd": {"type": "string", "description": "Working directory relative to project root"},
                "timeout": {"type": "integer", "description": "Execution timeout in seconds"},
            },
            "required": ["command"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        command = call.arguments.get("command", "")
        cwd = call.arguments.get("cwd")
        timeout = call.arguments.get("timeout", 30)
        user_id = get_user_id(ctx)
        project_id = get_project_id(ctx)

        try:
            from shared.database import get_engine, get_session
            from domains.identity.approval import ApprovalService

            engine = get_engine()
            db = get_session(engine)

            try:
                payload = {"command": command, "cwd": cwd, "timeout": timeout}
                request = ApprovalService.create_request(
                    db, project_id, user_id, "run_safe_shell", payload
                )

                return make_result(
                    call,
                    f"COMMAND QUEUED FOR APPROVAL:\n\n"
                    f"**Command:** `{command}`\n"
                    f"**Request ID:** `{request.id}`\n\n"
                    "Please approve this action in the UI to proceed.",
                )
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Failed to queue shell command: {e}")
            return fail(call, f"Failed to queue command: {e}")
