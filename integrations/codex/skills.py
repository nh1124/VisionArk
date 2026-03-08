"""Skill definitions for the Codex CLI integration."""

from domains.orchestration2.engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="codex_cli",
        description="Run AI-powered coding tasks via the Codex CLI on a connected native device",
        tools=["codex_check_runtime", "codex_run", "codex_job_wait", "codex_job_status", "codex_job_output", "codex_approval", "codex_job_cancel"],
        instructions="""\
## Codex CLI Skill

Use this skill when the user wants to perform coding tasks (write, edit, refactor, review code)
using the Codex CLI on their local machine or a connected device.

### Workflow
1. Call `codex_check_runtime` first to verify the CLI is installed and reachable.
   - If it returns `category: missing_binary`, inform the user the CLI is not installed
     and guide them to install it (`npm install -g @openai/codex`).
2. Call `codex_run` with a clear natural-language `prompt` describing the coding task.
   - Returns immediately with a `job_id`.
   - Use `workdir` to set the working directory so Codex has project file context.
   - Use `risk_level: "medium"` for file edits; `"high"` for large refactors.
3. Call `codex_job_wait` with the `job_id` to block until the result is ready.
   - Returns stdout when `completed`, or an error if `failed`.
   - Default timeout is 600s; increase for large tasks.
   - Use `codex_job_status` only if you need non-blocking status checks.
4. If `codex_job_wait` times out but the job is still `running`:
   a. Call `codex_job_output` to see what Codex is currently displaying on its console.
   b. If Codex is waiting for input (e.g. "Continue? (y/n)"), call `codex_approval`
      with the appropriate response (default `"\n"` for Enter, `"y\n"` for yes).
   c. Then call `codex_job_wait` again to resume waiting.
5. Optionally call `codex_job_cancel` to abort a running task.

### Parameters (codex_run)
- `prompt` — Natural-language description of the task (required)
- `model` — Codex model ID, e.g. `o4-mini` (optional; defaults to CLI default)
- `sandbox` — Sandbox override: `read-only` | `workspace-write` | `danger-full-access`
               (omit to use `--full-auto`, recommended)
- `device_id` — Target device from `list_native_devices`; omit to auto-select (optional)
- `workdir` — Working directory on the device (optional; strongly recommended for file tasks)
- `risk_level` — `low` | `medium` | `high` | `critical` (default: `medium`)

### Response categories (codex_job_status)
- `completed` — Task completed; see `stdout` for Codex output
- `failed / missing_binary` — Codex CLI not installed on the device
- `failed / rejected` — Execution rejected by the user in Run Center
- `failed / nonzero_exit` — Codex exited with a non-zero code; see `summary`
- `failed / timeout` — Codex ran too long
- `queued | running` — Still in progress; keep polling

### Notes
- Codex requires an OpenAI API key configured in Settings → Integrations → Codex CLI.
- High-risk executions appear in the Run Center and require user approval before running.
- Always verify the result with the user before applying changes to production files.
""",
    ),
]
