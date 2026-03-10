"""Codex integration tools for VisionArk agents.

Tools
-----
CodexCheckRuntimeTool   Verify Codex CLI availability and version on a device.
CodexRunTool            Run a coding task via the Codex CLI (returns a job_id immediately).
CodexJobStatusTool      Check the status / result of a Codex task.
CodexJobWaitTool        Block until a Codex task completes (polls every 5s).
CodexJobOutputTool      Get the current stdout of a running Codex task.
CodexApprovalTool       Send text input to a running Codex process (e.g. approve a prompt).
CodexJobCancelTool      Cancel a queued or running Codex task.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic import Field
from va_sdk import BaseTool, BaseModel, IntegrationContext, ToolResult

from integrations._cli_run_helper import (
    dispatch_shell_command,
    dispatch_shell_command_async,
    _err_result,
    _ok_result,
)

logger = logging.getLogger(__name__)


# ── check_runtime ──────────────────────────────────────────────────────────────

class CodexCheckRuntimeArgs(BaseModel):
    device_id: Optional[str] = Field(
        None,
        description="Target device ID (from list_native_devices). Auto-selects if omitted.",
    )
    workdir: Optional[str] = Field(
        None,
        description="Working directory to verify accessibility on the device.",
    )


class CodexCheckRuntimeTool(BaseTool):
    name = "codex_check_runtime"
    description = (
        "Verify that the Codex CLI binary is installed and reachable on a native device. "
        "Returns the version string, device info, and whether the working directory is accessible. "
        "Call this before codex_run to confirm the environment is ready."
    )
    args_schema = CodexCheckRuntimeArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        device_id: str | None = kwargs.get("device_id")
        workdir: str | None = kwargs.get("workdir")

        # Check version
        version_result = await dispatch_shell_command(
            ctx,
            cmd="codex --version",
            device_id=device_id,
            risk_level="low",
            timeout=15,
            sync=True,
        )

        if not version_result.is_success:
            return version_result

        data = version_result.data or {}
        raw = data.get("raw", {})
        version_str = (raw.get("stdout") or "").strip() or "unknown"

        # Optionally check workdir accessibility
        if workdir:
            # Validate workdir with the same execution path used by codex_run:
            # spawn a tiny command with cwd=workdir on the target device.
            wd_result = await dispatch_shell_command(
                ctx,
                argv=["python", "-c", "print('ok')"],
                cwd=workdir,
                device_id=device_id,
                risk_level="low",
                timeout=10,
                sync=True,
            )
            if wd_result.is_success:
                wd_raw = (wd_result.data or {}).get("raw", {})
                wd_accessible = (wd_raw.get("stdout") or "").strip() == "ok"
            else:
                wd_accessible = None
        else:
            wd_accessible = None

        return _ok_result(
            f"Codex CLI available: {version_str}",
            version=version_str,
            device_id=device_id or data.get("run_id"),
            workdir_accessible=wd_accessible,
            run_id=data.get("run_id"),
            execution_id=data.get("execution_id"),
        )


# ── run ────────────────────────────────────────────────────────────────────────

class CodexRunArgs(BaseModel):
    prompt: str = Field(
        ...,
        description="Natural-language coding task description for Codex (e.g. 'Add error handling to utils.py').",
    )
    model: Optional[str] = Field(
        None,
        description="Model to use, e.g. 'o4-mini' (passed as --model). Defaults to Codex CLI default.",
    )
    sandbox: Optional[str] = Field(
        None,
        description=(
            "Sandbox policy override: read-only | workspace-write | danger-full-access. "
            "Omit to use --full-auto (workspace-write + auto-approvals, recommended)."
        ),
    )
    workdir: Optional[str] = Field(
        None,
        description="Working directory on the device.",
    )
    device_id: Optional[str] = Field(
        None,
        description="Target device ID. Auto-selects if omitted.",
    )
    risk_level: Optional[str] = Field(
        "medium",
        description="Risk level: low | medium | high | critical. File-editing tasks default to medium.",
    )


class CodexRunTool(BaseTool):
    name = "codex_run"
    description = (
        "Execute a coding task using the Codex CLI on a native device. "
        "Returns immediately with a job_id  Euse codex_job_status to check progress "
        "and retrieve the result when complete. "
        "High-risk operations (file writes, refactors) may require user approval in the Run Center."
    )
    args_schema = CodexRunArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        import os
        prompt: str = kwargs.get("prompt", "")
        model: str | None = kwargs.get("model")
        sandbox: str | None = kwargs.get("sandbox")
        workdir: str | None = kwargs.get("workdir")
        device_id: str | None = kwargs.get("device_id")
        risk_level: str = kwargs.get("risk_level") or "medium"

        if not prompt.strip():
            return _err_result("invalid_args", "prompt is required and must not be empty.")
        if not workdir or not str(workdir).strip():
            return _err_result(
                "invalid_args",
                "workdir is required for codex_run. Please pass an explicit project directory path.",
            )
        workdir = str(workdir).strip()
        # IMPORTANT:
        # Do not resolve relative workdir on the backend host.
        # Native commands run on a remote/local device via daemon, so relative
        # path resolution must happen on that device (daemon side), not here.
        expanded = os.path.expanduser(workdir)
        if os.path.isabs(expanded):
            workdir = os.path.abspath(expanded)
        else:
            # Keep relative path (e.g. ".", "./project") as-is.
            # daemon local_tools.rs resolves it against device user's home.
            workdir = workdir
        logger.info(
            "codex_run.request user=%s run=%s device=%s workdir=%r model=%r sandbox=%r prompt_len=%d",
            getattr(ctx, "user_id", None),
            (ctx.metadata or {}).get("run_id"),
            device_id,
            workdir,
            model,
            sandbox or "workspace-write+full-auto",
            len(prompt),
        )

        # Build codex exec argv (direct spawn  Eno shell quoting involved)
        argv = ["codex", "exec"]
        if sandbox:
            argv += ["--sandbox", sandbox]
        else:
            # workspace-write sandbox + auto-approve all actions
            argv += ["--sandbox", "workspace-write", "--full-auto"]
        if model:
            argv += ["--model", model]
        # Keep Codex CLI invocation stable on Windows:
        # use run_shell's cwd for working-directory control and avoid passing
        # relative --cd (e.g. ".") directly to codex exec.
        if os.path.isabs(workdir):
            argv += ["--cd", workdir]
        else:
            logger.warning(
                "codex_run.relative_workdir detected workdir=%r; using run_shell cwd resolution and omitting --cd",
                workdir,
            )
        # Required when workdir is not a trusted git repo
        argv.append("--skip-git-repo-check")
        argv.append(prompt)
        result = await dispatch_shell_command_async(
            ctx,
            argv=argv,
            cwd=workdir,
            device_id=device_id,
            risk_level=risk_level,
            tool_name="codex_run",
            timeout=600,  # codex needs time for AI inference; daemon default (30s) is too short
            completion_markers=["tokens used"],
            extra_payload={
                # Auto-recover when Codex/PowerShell gets stuck waiting for input.
                "idle_approval_secs": 90,
                "idle_kill_after_approval_secs": 120,
                # Daemon heartbeat logs for observability.
                "heartbeat_secs": 15,
            },
            job_extra_input={
                # LRJ-level stale guard (seconds) to avoid infinite "running".
                "stall_timeout_sec": 420,
            },
        )
        data = result.data or {}
        logger.info(
            "codex_run.queued ok=%s job_id=%s execution_id=%s run_id=%s",
            data.get("ok"),
            data.get("job_id"),
            data.get("execution_id"),
            data.get("run_id"),
        )
        return result


# ── job_status ─────────────────────────────────────────────────────────────────

class CodexJobStatusArgs(BaseModel):
    job_id: str = Field(
        ...,
        description="Job ID returned by codex_run.",
    )


class CodexJobStatusTool(BaseTool):
    name = "codex_job_status"
    description = (
        "Check the status of an async Codex task started by codex_run. "
        "Returns status (queued | running | completed | failed | cancelled) and, "
        "when complete, the stdout output from Codex."
    )
    args_schema = CodexJobStatusArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        job_id: str = kwargs.get("job_id", "")
        if not job_id:
            return _err_result("invalid_args", "job_id is required.")
        logger.info("codex_job_status.request user=%s job_id=%s", getattr(ctx, "user_id", None), job_id)

        try:
            from integrations._internal_services import LongRunningJobService
            job = await LongRunningJobService.get_job(ctx.db, job_id, ctx.user_id)
        except Exception as e:
            return _err_result("internal_error", f"Failed to fetch job: {e}")

        if job is None:
            return _err_result("not_found", f"Job '{job_id}' not found.")

        status = job.status
        logger.info("codex_job_status.state job_id=%s status=%s", job_id, status)

        if status == "completed":
            result = job.result_payload or {}
            stdout = result.get("stdout", "")
            return _ok_result(
                stdout.strip() or "Codex task completed.",
                job_id=job_id,
                status=status,
                stdout=stdout,
                stderr=result.get("stderr", ""),
                exit_code=result.get("exit_code", 0),
                execution_id=result.get("execution_id"),
            )

        if status == "failed":
            return _err_result(
                job.error_code or "failed",
                job.error_message or "Codex task failed.",
                job_id=job_id,
                status=status,
            )

        # queued / running / cancelled
        progress = getattr(job, "progress", None) or {}
        return _ok_result(
            f"Codex task is {status}.",
            job_id=job_id,
            status=status,
            progress_pct=progress.get("pct") if isinstance(progress, dict) else None,
            progress_message=progress.get("message") if isinstance(progress, dict) else None,
        )


# ── job_wait ──────────────────────────────────────────────────────────────────

class CodexJobWaitArgs(BaseModel):
    job_id: str = Field(
        ...,
        description="Job ID returned by codex_run.",
    )
    timeout: Optional[int] = Field(
        600,
        description="Maximum seconds to wait for completion (default 600).",
        ge=10,
        le=3600,
    )


class CodexJobWaitTool(BaseTool):
    name = "codex_job_wait"
    description = (
        "Wait for a Codex task to complete and return its result. "
        "Polls until the job is completed or failed (up to timeout seconds). "
        "Use this right after codex_run  Eit blocks until the result is ready, "
        "so you do not need to manually poll codex_job_status."
    )
    args_schema = CodexJobWaitArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        import asyncio
        import time

        job_id: str = kwargs.get("job_id", "")
        timeout: int = int(kwargs.get("timeout") or 600)

        if not job_id:
            return _err_result("invalid_args", "job_id is required.")
        logger.info(
            "codex_job_wait.start user=%s job_id=%s timeout=%s",
            getattr(ctx, "user_id", None),
            job_id,
            timeout,
        )

        deadline = time.monotonic() + timeout

        while True:
            await asyncio.sleep(2)

            try:
                from integrations._internal_services import LongRunningJobService
                ctx.db.expire_all()  # force fresh DB read (avoid stale identity map cache)
                job = await LongRunningJobService.get_job(ctx.db, job_id, ctx.user_id)
            except Exception as e:
                return _err_result("internal_error", f"Failed to fetch job: {e}")

            if job is None:
                return _err_result("not_found", f"Job '{job_id}' not found.")

            status = job.status

            if status == "completed":
                result = job.result_payload or {}
                stdout = result.get("stdout", "")
                logger.info(
                    "codex_job_wait.completed job_id=%s stdout_len=%d stderr_len=%d exit_code=%s",
                    job_id,
                    len(stdout or ""),
                    len(result.get("stderr", "") or ""),
                    result.get("exit_code", 0),
                )
                return _ok_result(
                    stdout.strip() or "Codex task completed.",
                    job_id=job_id,
                    status=status,
                    stdout=stdout,
                    stderr=result.get("stderr", ""),
                    exit_code=result.get("exit_code", 0),
                )

            if status in ("failed", "cancelled"):
                logger.warning(
                    "codex_job_wait.terminal_non_success job_id=%s status=%s code=%s",
                    job_id,
                    status,
                    job.error_code,
                )
                return _err_result(
                    job.error_code or status,
                    job.error_message or "Codex task failed.",
                    job_id=job_id,
                    status=status,
                )

            # queued / running  Echeck timeout AFTER poll so we never skip the final check
            if time.monotonic() >= deadline:
                break

        return _err_result(
            "timeout",
            f"Job '{job_id}' did not complete within {timeout}s. Use codex_job_status to check later.",
            job_id=job_id,
        )


# ── job_cancel ─────────────────────────────────────────────────────────────────

class CodexJobCancelArgs(BaseModel):
    job_id: str = Field(
        ...,
        description="Job ID returned by codex_run.",
    )


class CodexJobCancelTool(BaseTool):
    name = "codex_job_cancel"
    description = (
        "Cancel a Codex task that was started by codex_run. "
        "Only jobs in queued or running state can be cancelled."
    )
    args_schema = CodexJobCancelArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        job_id: str = kwargs.get("job_id", "")
        if not job_id:
            return _err_result("invalid_args", "job_id is required.")

        try:
            from integrations._internal_services import LongRunningJobService
            job = await LongRunningJobService.get_job(ctx.db, job_id, ctx.user_id)
            if job is None:
                return _err_result("not_found", f"Job '{job_id}' not found.")
            if job.status in ("completed", "failed", "cancelled", "expired"):
                return _err_result(
                    "invalid_state",
                    f"Job '{job_id}' is already {job.status} and cannot be cancelled.",
                )
            await LongRunningJobService.cancel_job(ctx.db, job_id, ctx.user_id)
        except Exception as e:
            return _err_result("internal_error", f"Failed to cancel job: {e}")

        return _ok_result(f"Job '{job_id}' cancelled.", job_id=job_id, status="cancelled")


# ── job_output ─────────────────────────────────────────────────────────────────

class CodexJobOutputArgs(BaseModel):
    job_id: str = Field(..., description="Job ID returned by codex_run.")


class CodexJobOutputTool(BaseTool):
    name = "codex_job_output"
    description = (
        "Get the current stdout output of a running Codex task. "
        "Use this to see what Codex is currently displaying or waiting for. "
        "Returns the last ~3000 characters of output captured so far. "
        "If Codex appears stuck, call this to inspect its current state, "
        "then use codex_approval to send the required input."
    )
    args_schema = CodexJobOutputArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        job_id: str = kwargs.get("job_id", "")
        if not job_id:
            return _err_result("invalid_args", "job_id is required.")

        try:
            from integrations._internal_services import LongRunningJobService, RunService
            job = await LongRunningJobService.get_job(ctx.db, job_id, ctx.user_id)
        except Exception as e:
            return _err_result("internal_error", f"Failed to fetch job: {e}")

        if job is None:
            return _err_result("not_found", f"Job '{job_id}' not found.")

        # Try partial_stdout from RunExecution first (real-time, streamed by daemon)
        exec_id: str | None = (job.input_payload or {}).get("execution_id")
        partial: str | None = None
        if exec_id:
            try:
                from integrations._internal_services import RunService
                partial = await RunService.get_partial_stdout(ctx.db, exec_id)
            except Exception:
                pass

        # Fallback: use LRJ progress message (updated every poll cycle)
        progress = getattr(job, "progress", None) or {}
        if not partial:
            if isinstance(progress, dict):
                partial = progress.get("message", "")

        if not partial:
            return _ok_result(
                "No output yet.",
                job_id=job_id,
                status=job.status,
                output="",
            )

        return _ok_result(
            partial[-3000:],
            job_id=job_id,
            status=job.status,
            execution_id=exec_id,
            progress_message=progress.get("message") if isinstance(progress, dict) else None,
            output=partial[-3000:],
            total_bytes=len(partial),
        )


# ── approval (stdin injection) ─────────────────────────────────────────────────

class CodexApprovalArgs(BaseModel):
    job_id: str = Field(..., description="Job ID returned by codex_run.")
    input_text: str = Field(
        "\n",
        description=(
            "Text to send to Codex's stdin. "
            "Use '\\n' (default) to press Enter and confirm a prompt. "
            "Use 'y\\n' or 'yes\\n' to answer yes/no questions. "
            "Use any other text followed by '\\n' for custom input."
        ),
    )


class CodexApprovalTool(BaseTool):
    name = "codex_approval"
    description = (
        "Send text input to a running Codex process. "
        "Use after codex_job_output reveals that Codex is waiting for input. "
        "Defaults to sending a newline (Enter) to confirm prompts. "
        "For yes/no questions send 'y\\n'. "
        "The input is written directly to Codex's stdin on the native device."
    )
    args_schema = CodexApprovalArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        job_id: str = kwargs.get("job_id", "")
        text: str = kwargs.get("input_text", "\n")
        if not job_id:
            return _err_result("invalid_args", "job_id is required.")

        try:
            from integrations._internal_services import LongRunningJobService, RunService
            job = await LongRunningJobService.get_job(ctx.db, job_id, ctx.user_id)
        except Exception as e:
            return _err_result("internal_error", f"Failed to fetch job: {e}")

        if job is None:
            return _err_result("not_found", f"Job '{job_id}' not found.")

        exec_id: str | None = (job.input_payload or {}).get("execution_id")
        if not exec_id:
            return _err_result("invalid_state", "No execution_id found for this job.")

        try:
            from integrations._internal_services import RunService
            await RunService.enqueue_stdin(ctx.db, exec_id, text)
        except ValueError as e:
            return _err_result("not_found", str(e))
        except Exception as e:
            return _err_result("internal_error", f"Failed to enqueue stdin: {e}")

        return _ok_result(
            f"Input sent to Codex: {repr(text)}",
            job_id=job_id,
            exec_id=exec_id,
            text_sent=text,
        )
