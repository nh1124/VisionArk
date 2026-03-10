"""Shared helper for CLI integration tools that dispatch native shell commands.

Each CLI integration (codex, antigravity, claude) imports from here to avoid
duplicating NativeRun creation and polling logic.

Response format (all tools):
  ok:           bool
  category:     success | missing_binary | invalid_args | permission_denied
                | timeout | approval_required | internal_error
  summary:      str
  run_id:       str (present when an execution was started)
  execution_id: str (present when an execution was started)
  raw:          dict (present on success — raw daemon result)
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from va_sdk import IntegrationContext, ToolResult

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {"succeeded", "failed", "rejected"}


# ── response builders ──────────────────────────────────────────────────────────

def _err_result(category: str, summary: str, **extra: Any) -> ToolResult:
    data = {"ok": False, "category": category, "summary": summary, **extra}
    return ToolResult(content=json.dumps(data), data=data, is_success=False)


def _ok_result(summary: str, **extra: Any) -> ToolResult:
    data = {"ok": True, "category": "success", "summary": summary, **extra}
    return ToolResult(content=json.dumps(data), data=data, is_success=True)


# ── device helpers ─────────────────────────────────────────────────────────────

async def _resolve_device(db, user_id: str, device_id: str | None):
    """Return (device_id, label) for an enabled device, or (None, 'auto')."""
    from sqlalchemy import select
    from shared.database import NativeDevice

    if device_id:
        res = await db.execute(
            select(NativeDevice).where(
                NativeDevice.id == device_id,
                NativeDevice.user_id == user_id,
                NativeDevice.is_enabled == True,  # noqa: E712
            )
        )
        device = res.scalars().first()
        if not device:
            return None, None  # signals "device not found"
        return device.id, device.display_name
    else:
        res = await db.execute(
            select(NativeDevice).where(
                NativeDevice.user_id == user_id,
                NativeDevice.is_enabled == True,  # noqa: E712
            ).order_by(NativeDevice.last_seen_at.desc().nullslast())
        )
        device = res.scalars().first()
        if not device:
            return None, "auto"
        return device.id, device.display_name


# ── category detection ─────────────────────────────────────────────────────────

def _classify_exit(exit_code: int, stdout: str, stderr: str) -> str:
    """Classify a non-zero exit code into a standard category."""
    combined = (stdout + stderr).lower()
    if exit_code == 127 or "command not found" in combined or "not recognized" in combined:
        return "missing_binary"
    if exit_code in (1, 13) and ("permission" in combined or "access denied" in combined):
        return "permission_denied"
    return "internal_error"


# ── main dispatch ──────────────────────────────────────────────────────────────

async def dispatch_shell_command(
    ctx: IntegrationContext,
    cmd: str | None = None,
    *,
    argv: list[str] | None = None,
    cwd: str | None = None,
    device_id: str | None = None,
    risk_level: str = "low",
    timeout: int = 60,
    sync: bool = True,
) -> ToolResult:
    """Create a NativeRun for a shell command and optionally wait for result.

    Parameters
    ----------
    ctx:        IntegrationContext — must have metadata["run_id"] set.
    cmd:        Shell command string to execute on the daemon (mutually exclusive with argv).
    argv:       Argument vector for direct process spawn — avoids all shell quoting issues.
                Preferred over cmd when the prompt/args may contain spaces or special chars.
    cwd:        Working directory (passed to run_shell payload).
    device_id:  Target device; auto-selects if None.
    risk_level: low | medium | high | critical.
    timeout:    Seconds to wait for the daemon result (sync mode).
    sync:       If False, return immediately after queuing.
    """
    if cmd is None and argv is None:
        return _err_result("internal_error", "dispatch_shell_command: either cmd or argv must be provided.")
    run_id = ctx.metadata.get("run_id")
    if not run_id:
        return _err_result(
            "internal_error",
            "No active agent run context. CLI tools must be invoked within an agent run.",
        )

    db = ctx.db
    user_id = ctx.user_id

    try:
        from domains.native.run_service import NativeRunService

        # Resolve device
        resolved_device_id, device_label = await _resolve_device(db, user_id, device_id)
        if device_id and resolved_device_id is None:
            return _err_result(
                "internal_error",
                f"Device '{device_id}' not found or is disabled.",
            )

        # Build run_shell payload
        payload: dict = {"timeout": timeout}
        if argv is not None:
            payload["argv"] = argv
        else:
            payload["cmd"] = cmd
        if cwd:
            payload["cwd"] = cwd

        # Create NativeRun unit directly from orchestration context.
        native_run = await NativeRunService.create_run(
            db=db,
            user_id=user_id,
            project_id=getattr(ctx, "project_id", None),
            session_id=getattr(ctx, "session_id", None),
            summary="cli.run_shell",
            trace_id=getattr(ctx, "trace_id", None),
            origin_type="integration.cli",
            origin_id=run_id,
            orchestration_run_id=run_id,
            kind="local.run_shell",
            payload=payload,
            risk_level=risk_level,
            target_device_id=resolved_device_id,
        )

        _cmd_preview = (cmd or " ".join(argv or []))[:80]
        logger.info(
            "cli_dispatch: user=%s run=%s exec=%s cmd=%r device=%s sync=%s",
            user_id, native_run.id, native_run.id, _cmd_preview, resolved_device_id, sync,
        )

        if not sync:
            return _ok_result(
                f"Command queued for '{device_label}'.",
                run_id=native_run.id,
                execution_id=native_run.id,
                status=native_run.status,
            )

        # Synchronous polling
        import time
        deadline = time.monotonic() + timeout + 30  # buffer over the cmd timeout

        while time.monotonic() < deadline:
            await asyncio.sleep(1.0)
            await db.refresh(native_run)
            if native_run.status in _TERMINAL_STATES:
                break
            if native_run.status == "waiting_approval":
                deadline = max(deadline, time.monotonic() + 300)

        # Map final status to response
        if native_run.status == "succeeded":
            raw = native_run.result or {}
            stdout: str = raw.get("stdout", "")
            stderr: str = raw.get("stderr", "")
            exit_code: int = raw.get("exit_code", 0)

            if exit_code != 0:
                category = _classify_exit(exit_code, stdout, stderr)
                return _err_result(
                    category,
                    f"Command exited {exit_code}: {stderr.strip() or stdout.strip()}",
                    run_id=native_run.id,
                    execution_id=native_run.id,
                    raw=raw,
                )

            return _ok_result(
                stdout.strip() or "Command completed.",
                run_id=native_run.id,
                execution_id=native_run.id,
                raw=raw,
            )

        if native_run.status == "failed":
            return _err_result(
                "internal_error",
                native_run.error_log or "Execution failed.",
                run_id=native_run.id,
                execution_id=native_run.id,
            )

        if native_run.status == "rejected":
            return _err_result(
                "permission_denied",
                "Execution was rejected by the user.",
                run_id=native_run.id,
                execution_id=native_run.id,
            )

        if native_run.status == "waiting_approval":
            return _err_result(
                "approval_required",
                "Execution is waiting for user approval in the Run Center.",
                run_id=native_run.id,
                execution_id=native_run.id,
            )

        return _err_result(
            "timeout",
            f"Execution timed out after {timeout}s (status={native_run.status}).",
            run_id=native_run.id,
            execution_id=native_run.id,
        )

    except Exception as e:
        logger.error("dispatch_shell_command error: %s", e, exc_info=True)
        return _err_result("internal_error", f"Dispatch error: {e}")


# ── async dispatch (LongRunningJob) ────────────────────────────────────────────

async def dispatch_shell_command_async(
    ctx: IntegrationContext,
    cmd: str | None = None,
    *,
    argv: list[str] | None = None,
    cwd: str | None = None,
    device_id: str | None = None,
    risk_level: str = "medium",
    tool_name: str = "cli_run",
    timeout: int = 600,
    completion_markers: list[str] | None = None,
    extra_payload: dict | None = None,
    job_extra_input: dict | None = None,
) -> ToolResult:
    """Create a NativeRun + LongRunningJob and return immediately with job_id.

    The background handler ``cli.run_shell`` (CliShellHandler) will poll the
    NativeRun and update the job to completed/failed when the daemon finishes.

    Returns a ToolResult with::
        job_id:       str  — use with codex_job_status / codex_job_cancel
        execution_id: str  — NativeRun ID
        run_id:       str  — NativeRun ID
        status:       "queued"
    """
    if cmd is None and argv is None:
        return _err_result("internal_error", "dispatch_shell_command_async: either cmd or argv must be provided.")

    run_id = ctx.metadata.get("run_id")
    if not run_id:
        return _err_result(
            "internal_error",
            "No active agent run context. CLI tools must be invoked within an agent run.",
        )

    db = ctx.db
    user_id = ctx.user_id

    try:
        from domains.native.run_service import NativeRunService

        # Resolve device
        resolved_device_id, device_label = await _resolve_device(db, user_id, device_id)
        if device_id and resolved_device_id is None:
            return _err_result(
                "internal_error",
                f"Device '{device_id}' not found or is disabled.",
            )

        # Build run_shell payload
        payload: dict = {"timeout": timeout}
        if argv is not None:
            payload["argv"] = argv
        else:
            payload["cmd"] = cmd
        if cwd:
            payload["cwd"] = cwd
        if completion_markers:
            payload["completion_markers"] = completion_markers
        if extra_payload:
            payload.update(extra_payload)

        # Create NativeRun (no hard timeout handling here; handler manages deadline)
        native_run = await NativeRunService.create_run(
            db=db,
            user_id=user_id,
            project_id=getattr(ctx, "project_id", None),
            session_id=getattr(ctx, "session_id", None),
            summary="cli.run_shell.async",
            trace_id=getattr(ctx, "trace_id", None),
            origin_type="integration.cli",
            origin_id=run_id,
            orchestration_run_id=run_id,
            kind="local.run_shell",
            payload=payload,
            risk_level=risk_level,
            target_device_id=resolved_device_id,
        )

        _cmd_preview = (cmd or " ".join(argv or []))[:80]
        logger.info(
            "cli_dispatch_async: user=%s run=%s exec=%s cmd=%r device=%s",
            user_id, native_run.id, native_run.id, _cmd_preview, resolved_device_id,
        )

        # Create LongRunningJob that the background handler will drive
        from integrations._internal_services import LongRunningJobService
        job = await LongRunningJobService.create_job(
            db=db,
            user_id=user_id,
            tool_name=tool_name,
            job_kind="cli.run_shell",
            input_payload={
                "execution_id": native_run.id,
                "run_id": native_run.id,
                **(job_extra_input or {}),
            },
            trace_id=getattr(native_run, "trace_id", None),
            origin_type="native_execution",
            origin_id=native_run.id,
        )

        return _ok_result(
            f"Task queued for '{device_label}'. Poll job_id to check progress.",
            job_id=job.id,
            execution_id=native_run.id,
            run_id=native_run.id,
            status="queued",
        )

    except Exception as e:
        logger.error("dispatch_shell_command_async error: %s", e, exc_info=True)
        return _err_result("internal_error", f"Dispatch error: {e}")
