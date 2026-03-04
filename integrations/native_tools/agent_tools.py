"""Native device & execution agent tools for VisionArk.

Tools
-----
ListNativeDevicesTool   List the user's registered native devices with status/capability info.
RunNativeJobTool        Create an AgentRun + RunExecution targeted at a specific device (or auto-routed).
"""
from __future__ import annotations

import json
import logging
from typing import Any, List, Optional

from pydantic import Field
from va_sdk import BaseTool, BaseModel, IntegrationContext, ToolResult

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _ok(data: Any) -> ToolResult:
    return ToolResult(content=json.dumps(data, ensure_ascii=False), data=data, is_success=True)


def _err(message: str) -> ToolResult:
    return ToolResult(content=message, is_success=False)


async def _api(ctx: IntegrationContext, method: str, path: str, body: Optional[dict] = None):
    """Minimal async HTTP helper using the backend's internal session."""
    import httpx
    from app.config import settings  # noqa: WPS433

    base_url = getattr(settings, "internal_api_url", "http://localhost:8000")
    headers = {
        "Content-Type": "application/json",
        "X-Internal-User-Id": ctx.user_id,
    }
    async with httpx.AsyncClient(base_url=base_url, timeout=15.0) as client:
        kwargs: dict = {"headers": headers}
        if body is not None:
            kwargs["json"] = body
        resp = await client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()


# ═══════════════════════════════════════════════════════════════════════════════
# list_native_devices
# ═══════════════════════════════════════════════════════════════════════════════

class ListNativeDevicesArgs(BaseModel):
    enabled_only: bool = Field(False, description="If true, return only enabled devices.")
    online_only: bool = Field(False, description="If true, return only online devices.")
    capability: Optional[str] = Field(
        None,
        description="Filter devices that have this capability (e.g. 'run_shell', 'file_rw').",
    )


class ListNativeDevicesTool(BaseTool):
    name = "list_native_devices"
    description = (
        "List the user's registered native devices (desktops, servers, mobiles). "
        "Returns device_id, display_name, platform, status, is_enabled, and capabilities for each device. "
        "Use this tool before run_native_job to choose the target_device_id."
    )
    args_schema = ListNativeDevicesArgs

    async def run(
        self,
        ctx: IntegrationContext = None,
        enabled_only: bool = False,
        online_only: bool = False,
        capability: Optional[str] = None,
        **kwargs,
    ) -> Any:
        if not ctx:
            return _err("Context is required")
        try:
            from sqlalchemy import select
            from shared.database import NativeDevice

            db = ctx.db
            stmt = select(NativeDevice).where(NativeDevice.user_id == ctx.user_id)
            result = await db.execute(stmt)
            devices = result.scalars().all()

            data = []
            for d in devices:
                if enabled_only and not d.is_enabled:
                    continue
                if online_only and d.status != "online":
                    continue
                caps: List[str] = d.capabilities or []
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

            summary = (
                f"{len(data)} device(s) found"
                + (f" (enabled_only={enabled_only}" if enabled_only else "")
                + (f", online_only={online_only}" if online_only else "")
                + (f", capability={capability}" if capability else "")
                + (")" if enabled_only or online_only or capability else "")
            )
            return _ok({"devices": data, "count": len(data), "summary": summary})

        except Exception as exc:
            logger.exception("list_native_devices failed: %s", exc)
            return _err(f"Failed to list devices: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# run_native_job
# ═══════════════════════════════════════════════════════════════════════════════

class RunNativeJobArgs(BaseModel):
    job_type: str = Field(
        ...,
        description=(
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
    )
    payload: dict = Field(
        default_factory=dict,
        description=(
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
    )
    target_device_id: Optional[str] = Field(
        None,
        description=(
            "Device ID obtained from list_native_devices. "
            "If omitted, routing_mode defaults to 'auto' and the backend selects the best available device."
        ),
    )
    risk_level: str = Field(
        "low",
        description=(
            "Risk level: low | medium | high | critical. High/critical require user approval.\n"
            "Recommended: delete_file='high', close_window(force)='high', "
            "run_shell/write_file/move_file='medium', "
            "mouse_*/keyboard_*='medium', close_window='medium', "
            "all others='low'"
        ),
    )
    tags: List[str] = Field(default_factory=list, description="Optional tags for filtering.")
    timeout: int = Field(
        60,
        description=(
            "Maximum seconds to wait for daemon execution to complete (sync mode only). "
            "Default 60s. For long-running tools (e.g. run_shell with heavy commands), increase this."
        ),
    )
    sync: bool = Field(
        True,
        description=(
            "If true (default), wait for daemon to complete and return the actual result. "
            "If false, return immediately with run_id/execution_id (fire-and-forget)."
        ),
    )




class RunNativeJobTool(BaseTool):
    name = "run_native_job"
    description = (
        "Execute a native tool on a user's device (desktop, server, or mobile) "
        "and return the result synchronously. "
        "First call list_native_devices to find an appropriate device_id. "
        "Available tools include: shell commands, file operations, app control, "
        "window management, mouse/keyboard input, and screen capture. "
        "The daemon on the target device executes the tool and this call waits "
        "for the result (subject to user approval for high-risk executions). "
        "Returns the actual execution result from the daemon."
    )
    args_schema = RunNativeJobArgs

    async def run(
        self,
        ctx: IntegrationContext = None,
        job_type: str = "",
        payload: dict = None,
        target_device_id: Optional[str] = None,
        risk_level: str = "low",
        tags: Optional[List[str]] = None,
        timeout: int = 60,
        sync: bool = True,
        **kwargs,
    ) -> Any:
        if not ctx:
            return _err("Context is required")
        if not job_type.strip():
            return _err("job_type is required")

        try:
            import asyncio
            import time
            from sqlalchemy import select
            from shared.database import NativeDevice, AgentRun, RunExecution
            import uuid

            db = ctx.db
            device_label = "auto-selected device"

            # Validate target device if specified
            if target_device_id:
                res = await db.execute(
                    select(NativeDevice).where(
                        NativeDevice.id == target_device_id,
                        NativeDevice.user_id == ctx.user_id,
                    )
                )
                device = res.scalars().first()
                if not device:
                    return _err(f"Device '{target_device_id}' not found or not owned by this user.")
                if not device.is_enabled:
                    return _err(
                        f"Device '{device.display_name}' is not enabled. "
                        "Enable it in Settings > Devices before using it as a target."
                    )
                device_label = device.display_name

            # ── Resolve or create AgentRun ────────────────────────────────
            # Prefer the orchestration2 run_id already projected as AgentRun.
            # This keeps native executions in the same run timeline.
            metadata = getattr(ctx, "metadata", {}) or {}
            orch_run_id = metadata.get("run_id") or metadata.get("orchestration_run_id")

            if orch_run_id:
                # Reuse existing AgentRun (created by worker.py projection)
                res = await db.execute(
                    select(AgentRun).where(AgentRun.id == orch_run_id)
                )
                run = res.scalars().first()
                if run is None:
                    # Fallback: projection may not have committed yet — create standalone
                    orch_run_id = None

            if not orch_run_id:
                # Standalone native-only run (no orchestration context)
                run = AgentRun(
                    id=str(uuid.uuid4()),
                    user_id=ctx.user_id,
                    project_id=ctx.project_id,
                    session_id=getattr(ctx, "session_id", None),
                    status="running",
                    summary=f"{job_type.strip()} — {device_label}",
                )
                db.add(run)
                await db.flush()

            exc = RunExecution(
                id=str(uuid.uuid4()),
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
                ctx.user_id, run.id, exc.id, job_type, target_device_id, sync,
            )

            # ── Async (fire-and-forget) mode ──────────────────────────────
            if not sync:
                return _ok({
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
                })

            # ── Synchronous polling loop ──────────────────────────────────
            terminal_states = {"succeeded", "failed", "rejected"}
            poll_interval = 1.0
            deadline = time.monotonic() + timeout
            last_status = exc.status

            while time.monotonic() < deadline:
                await asyncio.sleep(poll_interval)

                # Re-read execution from DB to get daemon updates
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
                    # Extend timeout for approval wait (user needs time)
                    deadline = max(deadline, time.monotonic() + 300)

            # ── Return result based on final status ───────────────────────
            if exc.status == "succeeded":
                result_data = exc.result or {}
                result_data["_meta"] = {
                    "run_id": run.id,
                    "execution_id": exc.id,
                    "status": "succeeded",
                }
                return _ok(result_data)

            elif exc.status == "failed":
                return _err(
                    f"Execution failed: {exc.error_log or 'unknown error'} "
                    f"(run_id={run.id}, exec_id={exc.id})"
                )

            elif exc.status == "rejected":
                return _err(
                    f"Execution was rejected by user "
                    f"(run_id={run.id}, exec_id={exc.id})"
                )

            else:
                # Timeout
                return _err(
                    f"Execution timed out after {timeout}s "
                    f"(status={exc.status}, run_id={run.id}, exec_id={exc.id})"
                )

        except Exception as e:
            logger.exception("run_native_job failed: %s", e)
            return _err(f"Failed to create/poll execution: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# check_execution_result — instant status check
# ═══════════════════════════════════════════════════════════════════════════════

class CheckExecutionArgs(BaseModel):
    execution_id: str = Field(
        ..., description="Execution ID returned by run_native_job (sync=false)."
    )
    run_id: str = Field(
        ..., description="Run ID returned by run_native_job."
    )


class CheckExecutionResultTool(BaseTool):
    name = "check_execution_result"
    description = (
        "Check the current status and result of a native execution. "
        "Use this after calling run_native_job with sync=false to see if the "
        "daemon has completed the execution. Returns status and result if available."
    )
    args_schema = CheckExecutionArgs

    async def run(
        self,
        ctx: IntegrationContext = None,
        execution_id: str = "",
        run_id: str = "",
        **kwargs,
    ) -> Any:
        if not ctx:
            return _err("Context is required")

        try:
            from sqlalchemy import select
            from shared.database import RunExecution

            db = ctx.db
            res = await db.execute(
                select(RunExecution).where(RunExecution.id == execution_id)
            )
            exc = res.scalars().first()
            if not exc:
                return _err(f"Execution '{execution_id}' not found")
            if exc.run_id != run_id:
                return _err(f"Execution '{execution_id}' does not belong to run '{run_id}'")

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

            return _ok(result)

        except Exception as e:
            logger.exception("check_execution_result failed: %s", e)
            return _err(f"Failed to check execution: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# wait_for_execution — blocking wait for a specific execution
# ═══════════════════════════════════════════════════════════════════════════════

class WaitForExecutionArgs(BaseModel):
    execution_id: str = Field(
        ..., description="Execution ID returned by run_native_job (sync=false)."
    )
    run_id: str = Field(
        ..., description="Run ID returned by run_native_job."
    )
    timeout: int = Field(
        60, description="Maximum seconds to wait for completion."
    )


class WaitForExecutionTool(BaseTool):
    name = "wait_for_execution"
    description = (
        "Wait for a native execution to complete and return its result. "
        "Use this after calling run_native_job with sync=false to block until "
        "the daemon finishes. Returns the actual result when done."
    )
    args_schema = WaitForExecutionArgs

    async def run(
        self,
        ctx: IntegrationContext = None,
        execution_id: str = "",
        run_id: str = "",
        timeout: int = 60,
        **kwargs,
    ) -> Any:
        if not ctx:
            return _err("Context is required")

        try:
            import asyncio
            import time
            from sqlalchemy import select
            from shared.database import RunExecution

            db = ctx.db
            res = await db.execute(
                select(RunExecution).where(RunExecution.id == execution_id)
            )
            exc = res.scalars().first()
            if not exc:
                return _err(f"Execution '{execution_id}' not found")
            if exc.run_id != run_id:
                return _err(f"Execution '{execution_id}' does not belong to run '{run_id}'")

            terminal_states = {"succeeded", "failed", "rejected"}

            # Already done?
            if exc.status in terminal_states:
                return _build_terminal_result(exc)

            # Poll
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                await asyncio.sleep(1.0)
                await db.refresh(exc)

                if exc.status in terminal_states:
                    return _build_terminal_result(exc)

                if exc.status == "waiting_approval":
                    deadline = max(deadline, time.monotonic() + 300)

            return _err(
                f"Execution timed out after {timeout}s "
                f"(status={exc.status}, exec_id={exc.id})"
            )

        except Exception as e:
            logger.exception("wait_for_execution failed: %s", e)
            return _err(f"Failed to wait for execution: {e}")


def _build_terminal_result(exc) -> dict:
    """Build tool result from a terminal-state execution."""
    if exc.status == "succeeded":
        result_data = exc.result or {}
        result_data["_meta"] = {
            "run_id": exc.run_id,
            "execution_id": exc.id,
            "status": "succeeded",
        }
        return _ok(result_data)
    elif exc.status == "failed":
        return _err(f"Execution failed: {exc.error_log or 'unknown error'}")
    elif exc.status == "rejected":
        return _err("Execution was rejected by user")
    else:
        return _err(f"Unexpected status: {exc.status}")


