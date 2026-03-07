"""Antigravity integration tools for VisionArk agents.

Tools
-----
AntigravityCheckRuntimeTool   Verify Antigravity CLI availability and version on a device.
AntigravityRunTool            Run an Antigravity command on a native device.
"""

from __future__ import annotations

import shlex
from typing import List, Optional

from pydantic import Field
from va_sdk import BaseTool, BaseModel, IntegrationContext, ToolResult

from integrations._cli_run_helper import dispatch_shell_command, _err_result, _ok_result


# ── check_runtime ──────────────────────────────────────────────────────────────

class AntigravityCheckRuntimeArgs(BaseModel):
    device_id: Optional[str] = Field(
        None,
        description="Target device ID (from list_native_devices). Auto-selects if omitted.",
    )
    workdir: Optional[str] = Field(
        None,
        description="Working directory to verify accessibility on the device.",
    )


class AntigravityCheckRuntimeTool(BaseTool):
    name = "antigravity_check_runtime"
    description = (
        "Verify that the Antigravity CLI binary is installed and reachable on a native device. "
        "Returns the version string and device reachability status. "
        "Call this before antigravity_run to confirm the environment is ready."
    )
    args_schema = AntigravityCheckRuntimeArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        device_id: str | None = kwargs.get("device_id")
        workdir: str | None = kwargs.get("workdir")

        version_result = await dispatch_shell_command(
            ctx,
            cmd="antigravity --version",
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

        return _ok_result(
            f"Antigravity CLI available: {version_str}",
            version=version_str,
            workdir_accessible=wd_accessible,
            run_id=data.get("run_id"),
            execution_id=data.get("execution_id"),
        )


# ── run ────────────────────────────────────────────────────────────────────────

class AntigravityRunArgs(BaseModel):
    command: str = Field(
        ...,
        description=(
            "Antigravity subcommand or full command string to execute "
            "(e.g. 'deploy', 'build --target prod', 'status')."
        ),
    )
    args: Optional[List[str]] = Field(
        None,
        description="Additional positional/flag arguments appended after the command.",
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
        description="Risk level: low | medium | high | critical.",
    )
    timeout: Optional[int] = Field(
        60,
        description="Maximum seconds to wait for Antigravity to complete.",
        ge=10,
        le=600,
    )


class AntigravityRunTool(BaseTool):
    name = "antigravity_run"
    description = (
        "Execute an Antigravity CLI command on a native device via the Run Center. "
        "Destructive operations (deploy, reset) are automatically escalated to high risk "
        "and may require user approval."
    )
    args_schema = AntigravityRunArgs

    # Subcommands that carry inherent risk and should be elevated.
    _HIGH_RISK_KEYWORDS = frozenset({"deploy", "destroy", "reset", "drop", "delete", "rm", "purge"})

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        command: str = kwargs.get("command", "")
        extra_args: list = kwargs.get("args") or []
        workdir: str | None = kwargs.get("workdir")
        device_id: str | None = kwargs.get("device_id")
        risk_level: str = kwargs.get("risk_level") or "medium"
        timeout: int = int(kwargs.get("timeout") or 60)

        if not command.strip():
            return _err_result("invalid_args", "command is required and must not be empty.")

        # Auto-escalate risk for dangerous subcommands
        first_word = command.strip().split()[0].lower()
        if first_word in self._HIGH_RISK_KEYWORDS and risk_level not in ("high", "critical"):
            risk_level = "high"

        # Build argv (direct spawn — no shell quoting involved)
        argv = ["antigravity"] + command.split() + list(extra_args)

        return await dispatch_shell_command(
            ctx,
            argv=argv,
            cwd=workdir,
            device_id=device_id,
            risk_level=risk_level,
            timeout=timeout,
            sync=True,
        )
