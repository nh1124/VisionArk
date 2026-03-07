"""Skill definitions for the Codex CLI integration."""

from domains.orchestration2.engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="codex_cli",
        description="Run AI-powered coding tasks via the Codex CLI on a connected native device",
        tools=["codex_check_runtime", "codex_run"],
        instructions="""## Codex CLI Skill

Use this skill when the user wants to perform coding tasks (write, edit, refactor, review code)
using the Codex CLI on their local machine or a connected device.

### Workflow
1. Call `codex_check_runtime` first to verify the CLI is installed and reachable.
   - If it returns `category: missing_binary`, inform the user the CLI is not installed
     and guide them to install it (`npm install -g @openai/codex`).
2. Call `codex_run` with a clear natural-language `prompt` describing the coding task.
   - Use `workdir` to set the working directory so Codex has project file context.
   - Use `risk_level: "medium"` for file edits; `"high"` for large refactors.

### Parameters
- `prompt` — Natural-language description of the task (required)
- `model` — Codex model ID, e.g. `o4-mini` (optional; defaults to CLI default)
- `sandbox` — Sandbox override: `read-only` | `workspace-write` | `danger-full-access` (omit to use `--full-auto`, recommended)
- `device_id` — Target device from `list_native_devices`; omit to auto-select (optional)
- `workdir` — Working directory on the device (optional; strongly recommended for file tasks)
- `risk_level` — `low` | `medium` | `high` | `critical` (default: `medium`)
- `timeout` — Seconds to wait (default: 120)

### Response categories
- `success` — Task completed; see `raw.stdout` for Codex output
- `missing_binary` — Codex CLI not installed on the device
- `approval_required` — High-risk execution needs user approval in Run Center
- `timeout` — Codex took longer than `timeout` seconds
- `permission_denied` — Execution rejected or file permission error
- `internal_error` — Unexpected failure; see `summary` for details

### Notes
- Codex requires an OpenAI API key configured in Settings → Integrations → Codex CLI.
- High-risk executions appear in the Run Center and require user approval before running.
- Always verify the result with the user before applying changes to production files.
""",
    ),
]
