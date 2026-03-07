"""Skill definitions for the Antigravity CLI integration."""

from domains.orchestration2.engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="antigravity_cli",
        description="Execute Antigravity CLI commands on a connected native device",
        tools=["antigravity_check_runtime", "antigravity_run"],
        instructions="""## Antigravity CLI Skill

Use this skill when the user wants to run Antigravity CLI operations
(build, deploy, status checks, etc.) on their local machine or a connected device.

### Workflow
1. Call `antigravity_check_runtime` to confirm the CLI is installed.
   - If `category: missing_binary`, inform the user and guide installation.
2. Call `antigravity_run` with the desired `command` (subcommand or full command string).

### Parameters
- `command` — Antigravity subcommand or full command (required), e.g. `status`, `build --target prod`
- `args` — Additional arguments appended after the command (optional list of strings)
- `device_id` — Target device from `list_native_devices`; omit to auto-select (optional)
- `workdir` — Working directory on the device (optional)
- `risk_level` — `low` | `medium` | `high` | `critical` (default: `medium`)
  - Destructive subcommands (`deploy`, `destroy`, `reset`, `drop`, `delete`) are automatically
    elevated to `high` risk regardless of this parameter.
- `timeout` — Seconds to wait (default: 60)

### Response categories
- `success` — Command completed; see `raw.stdout` for output
- `missing_binary` — Antigravity CLI not installed on the device
- `approval_required` — High-risk command needs user approval in Run Center
- `timeout` — Command exceeded `timeout` seconds
- `permission_denied` — Execution rejected or insufficient permissions
- `internal_error` — Unexpected failure

### Notes
- Destructive operations (`deploy`, `destroy`, `reset`, etc.) require explicit user approval
  via the Run Center before they execute on the device.
- Configure the integration in Settings → Integrations → Antigravity CLI.
""",
    ),
]
