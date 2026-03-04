"""Native device execution tools — internal library.

These tools use the Run Center (AgentRun / RunExecution) to dispatch
jobs to connected native devices via the daemon.

Key design: ctx.run_id is a direct field on ExecutionContext and maps
1:1 to orchestration_runs.run_id / agent_runs.id, so no session_id
lookup is needed — the AgentRun created by worker.py is always
addressable via ctx.run_id.
"""

from __future__ import annotations

import asyncio
import logging

from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_project_id, get_user_id, make_result

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3   # seconds between status polls
_POLL_TIMEOUT  = 300 # max seconds to wait for a sync run


def _err(call: ToolCallRef, msg: str) -> ToolResult:
    return ToolResult(tool_name=call.tool_name, call_id=call.call_id, output=msg, error=msg)


# ── ListNativeDevices ─────────────────────────────────────────────────────────

class ListNativeDevicesTool:
    definition = ToolDef(
        name="list_native_devices",
        description=(
            "List the user's registered native devices (desktops, servers, mobiles). "
            "Returns device_id, display_name, platform, status, is_enabled, and capabilities for each device. "
            "Use this tool before run_native_job to choose the target_device_id."
        ),
        parameters={
            "type": "object",
            "properties": {
                "enabled_only": {
                    "type": "boolean",
                    "description": "If true, return only enabled devices.",
                    "default": False,
                },
                "online_only": {
                    "type": "boolean",
                    "description": "If true, return only online devices.",
                    "default": False,
                },
                "capability": {
                    "type": "string",
                    "description": "Filter devices that have this capability (e.g. 'run_shell', 'file_rw').",
                },
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        enabled_only = call.arguments.get("enabled_only", False)
        online_only = call.arguments.get("online_only", False)
        capability = call.arguments.get("capability")

        db = get_db(ctx)
        user_id = get_user_id(ctx)
        try:
            from sqlalchemy import select
            from shared.database import NativeDevice
            res = await db.execute(
                select(NativeDevice).where(NativeDevice.user_id == user_id)
            )
            devices = res.scalars().all()

            data = []
            for d in devices:
                if enabled_only and not d.is_enabled:
                    continue
                if online_only and d.status != "online":
                    continue
                caps = d.capabilities or []
                if capability and capability not in caps:
                    continue
                data.append({
                    "device_id": d.id,
                    "display_name": d.display_name,
                    "device_kind": d.device_kind,
                    "platform": d.platform,
                    "client_version": d.client_version,
                    "capabilities": caps,
                    "is_enabled": d.is_enabled,
                    "status": d.status,
                    "last_seen_at": d.last_seen_at.isoformat() if d.last_seen_at else None,
                })

            if not data:
                return make_result(call, "No matching native devices found.")

            import json
            summary = (
                f"{len(data)} device(s) found"
                + (f" (enabled_only={enabled_only}" if enabled_only else "")
                + (f", online_only={online_only}" if online_only else "")
                + (f", capability={capability}" if capability else "")
                + (")" if enabled_only or online_only or capability else "")
            )
            result_data = {"devices": data, "count": len(data), "summary": summary}
            return make_result(call, json.dumps(result_data, ensure_ascii=False))
        except Exception as e:
            logger.error("list_native_devices failed: %s", e)
            return _err(call, f"Failed to list devices: {e}")
        



# ── RunNativeJob ──────────────────────────────────────────────────────────────

class RunNativeJobTool:
    definition = ToolDef(
        name="run_native_job",
        description=(
            "Execute a native tool on a user's device (desktop, server, or mobile) "
            "and return the result synchronously. "
            "First call list_native_devices to find an appropriate device_id. "
            "Available tools include: shell commands, file operations, app control, "
            "window management, mouse/keyboard input, and screen capture. "
            "The daemon on the target device executes the tool and this call waits "
            "for the result (subject to user approval for high-risk executions). "
            "Returns the actual execution result from the daemon."
        ),
        parameters={
            "type": "object",
            "properties": {
                "job_type": {
                    "type": "string",
                    "description": (
                        "Tool/job type identifier.  Use 'local.<tool>' for daemon tools.\n"
                        "Available daemon tools:\n"
                        "  File/Shell: run_shell, read_file, write_file, list_dir, move_file, delete_file\n"
                        "  Environment: get_native_environment (OS/CPU/memory/disk/monitors/timezone/is_admin)\n"
                        "  Window: get_active_window (foreground window title/pid/exe/bounds)\n"
                        "  Process: list_running_apps (all running processes)\n"
                        "  App: open_app, launch_app (with startup verification)\n"
                        "  Window Control: focus_window, close_window\n"
                        "  Mouse: mouse_move, mouse_click, mouse_drag\n"
                        "  Keyboard: keyboard_type, keyboard_hotkey\n"
                        "  Screen: capture_screen, capture_window, find_on_screen\n"
                        "Example: 'local.focus_window', 'local.mouse_click', 'local.keyboard_hotkey'"
                    ),
                },
                "payload": {
                    "type": "object",
                    "description": (
                        "Tool arguments passed to the daemon executor. Schemas per tool:\n"
                        "  run_shell:   {cmd, cwd?, timeout?}\n"
                        "  read_file:   {path}\n"
                        "  write_file:  {path, content}\n"
                        "  list_dir:    {path}\n"
                        "  move_file:   {src, dst}\n"
                        "  delete_file: {path}\n"
                        "  open_app:    {name}\n"
                        "  get_native_environment: {}\n"
                        "  get_active_window:      {}\n"
                        "  list_running_apps:      {}\n"
                        "  launch_app:      {name, timeout?, wait?}\n"
                        "  capture_screen:  {monitor?}\n"
                        "  focus_window:    {title?, pid?, exe_name?}  (at least one required)\n"
                        "  close_window:    {title?, pid?, exe_name?, force?}  (force=true terminates process)\n"
                        "  mouse_move:      {x, y, relative?, expected_window?}\n"
                        "  mouse_click:     {button?, x?, y?, double?, expected_window?}\n"
                        "  mouse_drag:      {from_x, from_y, to_x, to_y, button?, expected_window?}\n"
                        "  keyboard_type:   {text, expected_window?}\n"
                        "  keyboard_hotkey: {keys: ['ctrl','c'], expected_window?}\n"
                        "  capture_window:  {title?, pid?, exe_name?}  (at least one required)\n"
                        "  find_on_screen:  {grid_size?, monitor?}  (returns screenshot with coordinate grid)"
                    ),
                    "default": {},
                },
                "target_device_id": {
                    "type": "string",
                    "description": (
                        "Device ID obtained from list_native_devices. "
                        "If omitted, routing_mode defaults to 'auto' and the backend selects the best available device."
                    ),
                },
                "risk_level": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": (
                        "Risk level: low | medium | high | critical. High/critical require user approval.\n"
                        "Recommended: delete_file='high', close_window(force)='high', "
                        "run_shell/write_file/move_file='medium', "
                        "mouse_*/keyboard_*='medium', close_window='medium', "
                        "all others='low'"
                    ),
                    "default": "low",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for filtering.",
                    "default": [],
                },
                "timeout": {
                    "type": "integer",
                    "description": (
                        "Maximum seconds to wait for daemon execution to complete (sync mode only). "
                        "Default 60s. For long-running tools (e.g. run_shell with heavy commands), increase this."
                    ),
                    "default": 60,
                },
                "sync": {
                    "type": "boolean",
                    "description": (
                        "If true (default), wait for daemon to complete and return the actual result. "
                        "If false, return immediately with run_id/execution_id (fire-and-forget)."
                    ),
                    "default": True,
                },
            },
            "required": ["job_type"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        job_type        = call.arguments.get("job_type", "")
        payload         = call.arguments.get("payload") or {}
        risk_level      = call.arguments.get("risk_level", "low")
        target_device_id = call.arguments.get("target_device_id")
        sync            = call.arguments.get("sync", True)

        db       = get_db(ctx)
        user_id  = get_user_id(ctx)
        run_id   = ctx.run_id   # directly the orchestration / AgentRun id

        try:
            from sqlalchemy import select
            from shared.database import NativeDevice, AgentRun, RunExecution
            import uuid as _uuid

            # ── Resolve target device ─────────────────────────────────────────
            if target_device_id:
                res = await db.execute(
                    select(NativeDevice).where(
                        NativeDevice.id == target_device_id,
                        NativeDevice.user_id == user_id,
                        NativeDevice.is_enabled == True,  # noqa: E712
                    )
                )
                device = res.scalars().first()
                device_label = device.display_name if device else target_device_id
            else:
                res = await db.execute(
                    select(NativeDevice).where(
                        NativeDevice.user_id == user_id,
                        NativeDevice.is_enabled == True,  # noqa: E712
                    ).order_by(NativeDevice.last_seen_at.desc().nullslast())
                )
                device = res.scalars().first()
                target_device_id = device.id if device else None
                device_label = device.display_name if device else "auto"

            # ── Resolve AgentRun via ctx.run_id ───────────────────────────────
            # worker.py commits the AgentRun (id == run_id) before wait_response(),
            # so it is always present by the time tools execute.
            res = await db.execute(
                select(AgentRun).where(AgentRun.id == run_id)
            )
            run = res.scalars().first()

            if run is None:
                return _err(
                    call,
                    f"AgentRun {run_id} not found. "
                    "run_native_job must be called from within an active agent run."
                )

            # ── Create RunExecution ───────────────────────────────────────────
            exc = RunExecution(
                id=str(_uuid.uuid4()),
                run_id=run.id,
                kind=job_type.strip(),
                status="pending",
                risk_level=risk_level,
                payload=payload or {},
                target_device_id=target_device_id,
            )
            db.add(exc)
            await db.commit()
            await db.refresh(run)
            await db.refresh(exc)

            logger.info(
                "run_native_job: user=%s run=%s exec=%s kind=%s device=%s sync=%s",
                user_id, run.id, exc.id, job_type, target_device_id, sync,
            )

            import json
            if not sync:
                result_data = {
                    "run_id": run.id,
                    "execution_id": exc.id,
                    "status": exc.status,
                    "kind": exc.kind,
                    "target_device_id": exc.target_device_id,
                    "risk_level": exc.risk_level,
                    "message": (
                        f"Execution '{job_type}' queued for {device_label}. "
                        f"Monitor progress in Run Center (run_id={run.id})."
                    ),
                }
                return make_result(call, json.dumps(result_data, ensure_ascii=False))

            # ── Synchronous polling loop ──────────────────────────────────
            import time
            terminal_states = {"succeeded", "failed", "rejected"}
            poll_interval = 1.0
            timeout = call.arguments.get("timeout", 60)
            deadline = time.monotonic() + timeout
            last_status = exc.status

            while time.monotonic() < deadline:
                await asyncio.sleep(poll_interval)
                await db.refresh(exc)

                if exc.status != last_status:
                    logger.info(
                        "run_native_job poll: exec=%s status=%s -> %s",
                        exc.id, last_status, exc.status,
                    )
                    last_status = exc.status

                if exc.status in terminal_states:
                    break

                if exc.status == "waiting_approval":
                    deadline = max(deadline, time.monotonic() + 300)

            # ── Return result based on final status ───────────────────────
            import json
            if exc.status == "succeeded":
                result_data = exc.result or {}
                result_data["_meta"] = {
                    "run_id": run.id,
                    "execution_id": exc.id,
                    "status": "succeeded",
                }
                return make_result(call, json.dumps(result_data, ensure_ascii=False))
            elif exc.status == "failed":
                err_text = exc.error_log or "unknown error"
                return _err(call, f"Execution failed: {err_text} (run_id={run.id}, exec_id={exc.id})")
            elif exc.status == "rejected":
                return _err(call, f"Execution was rejected by user (run_id={run.id}, exec_id={exc.id})")
            else:
                return _err(call, f"Execution timed out after {timeout}s (status={exc.status}, run_id={run.id}, exec_id={exc.id})")

        except Exception as e:
            logger.error("run_native_job error: %s", e, exc_info=True)
            return _err(call, f"run_native_job error: {e}")


# ── helpers for terminal result ───────────────────────────────────────────────

def _build_terminal_result(call: ToolCallRef, exc) -> ToolResult:
    """Build tool result from a terminal-state execution."""
    import json
    if exc.status == "succeeded":
        result_data = exc.result or {}
        result_data["_meta"] = {
            "run_id": exc.run_id,
            "execution_id": exc.id,
            "status": "succeeded",
        }
        return make_result(call, json.dumps(result_data, ensure_ascii=False))
    elif exc.status == "failed":
        return _err(call, f"Execution failed: {exc.error_log or 'unknown error'}")
    elif exc.status == "rejected":
        return _err(call, "Execution was rejected by user")
    else:
        return _err(call, f"Unexpected status: {exc.status}")


# ═══════════════════════════════════════════════════════════════════════════════
# check_execution_result — instant status check
# ═══════════════════════════════════════════════════════════════════════════════

class CheckExecutionResultTool:
    definition = ToolDef(
        name="check_execution_result",
        description=(
            "Check the current status and result of a native execution. "
            "Use this after calling run_native_job with sync=false to see if the "
            "daemon has completed the execution. Returns status and result if available."
        ),
        parameters={
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "Execution ID returned by run_native_job (sync=false).",
                },
                "run_id": {
                    "type": "string",
                    "description": "Run ID returned by run_native_job.",
                },
            },
            "required": ["execution_id", "run_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        execution_id = call.arguments.get("execution_id", "")
        run_id_arg = call.arguments.get("run_id", "")

        db = get_db(ctx)
        try:
            from sqlalchemy import select
            from shared.database import RunExecution

            res = await db.execute(
                select(RunExecution).where(RunExecution.id == execution_id)
            )
            exc = res.scalars().first()
            if not exc:
                return _err(call, f"Execution '{execution_id}' not found")
            if exc.run_id != run_id_arg:
                return _err(call, f"Execution '{execution_id}' does not belong to run '{run_id_arg}'")

            import json
            result = {
                "execution_id": exc.id,
                "run_id": exc.run_id,
                "status": exc.status,
                "kind": exc.kind,
            }

            if exc.status == "succeeded":
                result["result"] = exc.result or {}
            elif exc.status == "failed":
                result["error"] = exc.error_log
            elif exc.status == "waiting_approval":
                result["note"] = "Waiting for user approval"

            return make_result(call, json.dumps(result, ensure_ascii=False))

        except Exception as e:
            logger.exception("check_execution_result failed: %s", e)
            return _err(call, f"Failed to check execution: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# wait_for_execution — blocking wait for a specific execution
# ═══════════════════════════════════════════════════════════════════════════════

class WaitForExecutionTool:
    definition = ToolDef(
        name="wait_for_execution",
        description=(
            "Wait for a native execution to complete and return its result. "
            "Use this after calling run_native_job with sync=false to block until "
            "the daemon finishes. Returns the actual result when done."
        ),
        parameters={
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "Execution ID returned by run_native_job (sync=false).",
                },
                "run_id": {
                    "type": "string",
                    "description": "Run ID returned by run_native_job.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Maximum seconds to wait for completion.",
                    "default": 60,
                },
            },
            "required": ["execution_id", "run_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        execution_id = call.arguments.get("execution_id", "")
        run_id_arg = call.arguments.get("run_id", "")
        timeout = call.arguments.get("timeout", 60)

        db = get_db(ctx)
        try:
            import time
            from sqlalchemy import select
            from shared.database import RunExecution

            res = await db.execute(
                select(RunExecution).where(RunExecution.id == execution_id)
            )
            exc = res.scalars().first()
            if not exc:
                return _err(call, f"Execution '{execution_id}' not found")
            if exc.run_id != run_id_arg:
                return _err(call, f"Execution '{execution_id}' does not belong to run '{run_id_arg}'")

            terminal_states = {"succeeded", "failed", "rejected"}

            # Already done?
            if exc.status in terminal_states:
                return _build_terminal_result(call, exc)

            # Poll
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                await asyncio.sleep(1.0)
                await db.refresh(exc)

                if exc.status in terminal_states:
                    return _build_terminal_result(call, exc)

                if exc.status == "waiting_approval":
                    deadline = max(deadline, time.monotonic() + 300)

            return _err(
                call,
                f"Execution timed out after {timeout}s "
                f"(status={exc.status}, exec_id={exc.id})"
            )

        except Exception as e:
            logger.exception("wait_for_execution failed: %s", e)
            return _err(call, f"Failed to wait for execution: {e}")
