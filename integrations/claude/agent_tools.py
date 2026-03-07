"""Claude CLI integration tools for VisionArk agents.

Tools
-----
ClaudeCheckRuntimeTool   Verify Claude CLI availability and version on a device.
ClaudeRunTool            Run a Claude CLI prompt on a native device.
"""

from __future__ import annotations

import shlex
from typing import Optional

from pydantic import Field
from va_sdk import BaseTool, BaseModel, IntegrationContext, ToolResult

from integrations._cli_run_helper import dispatch_shell_command, _err_result, _ok_result


# ── check_runtime ──────────────────────────────────────────────────────────────

class ClaudeCheckRuntimeArgs(BaseModel):
    device_id: Optional[str] = Field(
        None,
        description="Target device ID (from list_native_devices). Auto-selects if omitted.",
    )
    workdir: Optional[str] = Field(
        None,
        description="Working directory to verify accessibility on the device.",
    )


class ClaudeCheckRuntimeTool(BaseTool):
    name = "claude_check_runtime"
    description = (
        "Verify that the Claude CLI (Anthropic) is installed and reachable on a native device. "
        "Returns the version string and device reachability status. "
        "Call this before claude_run to confirm the environment is ready."
    )
    args_schema = ClaudeCheckRuntimeArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        device_id: str | None = kwargs.get("device_id")
        workdir: str | None = kwargs.get("workdir")

        version_result = await dispatch_shell_command(
            ctx,
            cmd="claude --version",
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
            f"Claude CLI available: {version_str}",
            version=version_str,
            workdir_accessible=wd_accessible,
            run_id=data.get("run_id"),
            execution_id=data.get("execution_id"),
        )


# ── run ────────────────────────────────────────────────────────────────────────

class ClaudeRunArgs(BaseModel):
    prompt: str = Field(
        ...,
        description="Prompt to send to the Claude CLI (e.g. 'Summarize the contents of README.md').",
    )
    model: Optional[str] = Field(
        None,
        description=(
            "Claude model to use (passed as --model). "
            "Examples: 'claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-4-5'. "
            "Defaults to the model configured in the Claude CLI or the service default_model setting."
        ),
    )
    workdir: Optional[str] = Field(
        None,
        description="Working directory on the device (used for file-relative prompts).",
    )
    device_id: Optional[str] = Field(
        None,
        description="Target device ID. Auto-selects if omitted.",
    )
    risk_level: Optional[str] = Field(
        "low",
        description="Risk level: low | medium | high | critical. Claude prompts are typically low risk.",
    )
    timeout: Optional[int] = Field(
        300,
        description="Maximum seconds to wait for the Claude CLI to respond.",
        ge=10,
        le=1800,
    )


class ClaudeRunTool(BaseTool):
    name = "claude_run"
    description = (
        "Execute a prompt via the Claude CLI (Anthropic) on a native device. "
        "Useful for delegating AI reasoning tasks, document generation, or code review "
        "to a locally running Claude instance with file system access. "
        "Returns the full Claude response."
    )
    args_schema = ClaudeRunArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> ToolResult:
        if not ctx:
            return _err_result("internal_error", "Missing integration context.")

        prompt: str = kwargs.get("prompt", "")
        model: str | None = kwargs.get("model")
        workdir: str | None = kwargs.get("workdir")
        device_id: str | None = kwargs.get("device_id")
        risk_level: str = kwargs.get("risk_level") or "low"
        timeout: int = int(kwargs.get("timeout") or 300)

        if not prompt.strip():
            return _err_result("invalid_args", "prompt is required and must not be empty.")

        # Build claude argv (direct spawn — no shell quoting involved)
        argv = ["claude", "-p", prompt]
        if model:
            argv += ["--model", model]

        return await dispatch_shell_command(
            ctx,
            argv=argv,
            cwd=workdir,
            device_id=device_id,
            risk_level=risk_level,
            timeout=timeout,
            sync=True,
        )
