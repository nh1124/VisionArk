"""Skill definitions for the Claude CLI integration."""

from domains.orchestration2.engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="claude_cli",
        description="Delegate AI reasoning, document generation, or code review to the Claude CLI on a native device",
        tools=["claude_check_runtime", "claude_run"],
        instructions="""## Claude CLI Skill

Use this skill when the user wants to invoke the Anthropic Claude CLI (`claude`) on a connected
device — for example to run prompts with file system access, perform code review in-context,
or generate documents from local files.

### When to use
- The user wants to run a Claude prompt that requires access to local files on a device.
- The user wants to delegate a long AI task to a device running Claude CLI independently.
- The user wants to use a specific Claude model version available through the CLI.

### Workflow
1. Call `claude_check_runtime` to verify the CLI is installed and reachable.
   - If `category: missing_binary`, guide the user to install it:
     `npm install -g @anthropic-ai/claude-code`
2. Call `claude_run` with the `prompt` to send.

### Parameters
- `prompt` — The prompt to send to Claude CLI (required)
- `model` — Claude model ID, e.g. `claude-opus-4-6`, `claude-sonnet-4-6` (optional;
  defaults to service config or CLI default)
- `device_id` — Target device; omit to auto-select (optional)
- `workdir` — Working directory on the device (optional; useful for file-relative prompts)
- `risk_level` — `low` | `medium` | `high` | `critical` (default: `low`)
- `timeout` — Seconds to wait for Claude response (default: 300; increase for long tasks)

### Response categories
- `success` — Claude responded; see `raw.stdout` for the full response
- `missing_binary` — Claude CLI not installed on the device
- `approval_required` — High-risk execution pending user approval
- `timeout` — Claude took longer than `timeout` seconds
- `permission_denied` — Rejected or API key invalid
- `internal_error` — Unexpected failure

### Notes
- Requires an Anthropic API key configured in Settings → Integrations → Claude CLI.
- Claude CLI responses can be long; the default timeout is 300 s. Increase `timeout` for
  complex document generation or large-context tasks.
- The `workdir` parameter is particularly useful when Claude needs to read local project files.
""",
    ),
]
