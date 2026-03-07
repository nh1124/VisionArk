"""Codex integration tools for VisionArk agents.

Tools
-----
CodexCheckRuntimeTool   Verify Codex CLI availability and version on a device.
CodexRunTool            Run a coding task via the Codex CLI on a native device.
"""

from __future__ import annotations

import shlex
from typing import Optional

from pydantic import Field
from va_sdk import BaseTool, BaseModel, IntegrationContext, ToolResult

from integrations._cli_run_helper import dispatch_shell_command, _err_result


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
            wd_result = await dispatch_shell_command(
                ctx,
                cmd=f"test -d {shlex.quote(workdir)} && echo ok || echo missing",
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

        from integrations._cli_run_helper import _ok_result
        return _ok_result(
            f"Codex CLI available: {version_str}",
            version=version_str,
            device_id=device_id or data.get("run_id"),  # best-effort
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
    timeout: Optional[int] = Field(
        300,
        description="Maximum seconds to wait for Codex to complete. Codex tasks involve AI reasoning and tool calls; 300s is recommended.",
        ge=10,
        le=600,
    )


class CodexRunTool(BaseTool):
    name = "codex_run"
    description = (
        "Execute a coding task using the Codex CLI on a native device. "
        "Dispatches the task to the device daemon via the Run Center and returns the result. "
        "High-risk operations (file writes, refactors) may require user approval."
    )
    args_schema = CodexRunArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        prompt: str = kwargs.get("prompt", "")
        model: str | None = kwargs.get("model")
        sandbox: str | None = kwargs.get("sandbox")
        workdir: str | None = kwargs.get("workdir")
        device_id: str | None = kwargs.get("device_id")
        risk_level: str = kwargs.get("risk_level") or "medium"
        timeout: int = int(kwargs.get("timeout") or 120)

        if not prompt.strip():
            return _err_result("invalid_args", "prompt is required and must not be empty.")

        # Build codex exec argv (direct spawn — no shell quoting involved)
        argv = ["codex", "exec"]
        if sandbox:
            argv += ["--sandbox", sandbox]
        else:
            argv.append("--full-auto")
        if model:
            argv += ["--model", model]
        argv.append(prompt)

        return await dispatch_shell_command(
            ctx,
            argv=argv,
            cwd=workdir,
            device_id=device_id,
            risk_level=risk_level,
            timeout=timeout,
            sync=True,
        )
