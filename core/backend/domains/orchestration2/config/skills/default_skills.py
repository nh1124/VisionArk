from ...engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="research",
        description="Research & information gathering",
        tools=[
            "google_search", "research_url", "search_places", "deep_research",
            "deep_research_status", "deep_research_cancel",
            "read_file_chunk", "list_files", "get_file_stat", "read_md_section",
            "list_notes", "read_note",
            "get_project_rules", "get_project_health",
            "list_agents", "get_agent_profile",
            "list_user_projects", "list_members",
            "list_workspace_items", "read_workspace_item",
        ],
        instructions=(
            "When to use: any task requiring information gathering, fact-checking, or background research.\n"
            "Do first: check existing workspace items and notes before searching the web.\n"
            "Do not: write or modify files; use write_file or authoring skill for that.\n"
            "Output contract: always cite sources and include a confidence level for each key claim."
        ),
    ),
    SkillDef(
        name="authoring",
        description="Writing & content generation",
        tools=[
            "write_file", "apply_text_patch", "recursive_writer",
            "generate_image", "generate_mermaid_visualizer", "execute_code",
            "create_note", "update_md_section",
        ],
        instructions=(
            "When to use: creating or editing documents, code, notes, diagrams, or any written artifact.\n"
            "Do first: confirm target file path and output format before writing.\n"
            "Do not: delete existing content that was not explicitly requested for removal.\n"
            "Output contract: produce complete, self-contained output — no placeholders or 'TODO' stubs."
        ),
    ),
    SkillDef(
        name="document_output",
        description="Final document rendering (PDF, etc.)",
        tools=[
            "render_pdf",
        ],
        instructions=(
            "When to use: generating final-form output files (PDF) from finalized content.\n"
            "Do first: verify that source content is complete and approved before rendering.\n"
            "Do not: embed unverified data, PII, or placeholder text in rendered output.\n"
            "Output contract: return file_path, format, and size_bytes for every rendered file."
        ),
    ),
    SkillDef(
        name="repository_ops",
        description="File & directory CRUD",
        tools=[
            "write_file", "read_file_chunk", "list_files", "delete_file",
            "apply_text_patch", "move_file", "copy_file",
            "make_directory", "get_file_stat", "import_github_repo",
        ],
        instructions=(
            "When to use: any file or directory create, read, update, or delete operation.\n"
            "Do first: run list_files to understand the directory structure before making changes.\n"
            "Do not: delete files that were not created in the current session without explicit confirmation.\n"
            "Output contract: return the affected path(s) and byte count for every write or delete."
        ),
    ),
    SkillDef(
        name="workspace_context",
        description="Read and write shared workspace items (profile, company info, reusable context)",
        tools=[
            "list_workspace_items",
            "read_workspace_item",
            "create_workspace_item",
            "update_workspace_item",
            "delete_workspace_item",
            "create_workspace_directory",
            "read_workspace_file",
            "move_workspace_item",
        ],
        instructions=(
            "When to use: reading or writing shared workspace knowledge such as company profile, "
            "team conventions, or reusable context items.\n"
            "Do first: read the existing item with read_workspace_item before overwriting.\n"
            "Do not: delete workspace items without explicit permission from the user.\n"
            "Output contract: confirm item name, type, and action taken in every response."
        ),
    ),
    SkillDef(
        name="project_admin",
        description="Project settings & member management",
        tools=[
            "update_project", "update_project_rules",
            "manage_member", "update_agent_description",
        ],
        instructions=(
            "When to use: modifying project configuration, rules, or membership.\n"
            "Do first: read current settings before proposing or applying changes.\n"
            "Do not: remove members or transfer ownership without explicit user confirmation.\n"
            "Output contract: show before/after state for every configuration change."
        ),
    ),
    SkillDef(
        name="runtime_ops",
        description="Browser automation, shell execution & timers",
        tools=[
            "set_timer", "schedule_recurring_prompt", "raise_continue", "run_safe_shell",
            "browser_open", "browser_click", "browser_fill", "browser_screenshot",
        ],
        instructions=(
            "When to use: automating browser interactions, queuing shell commands, scheduling timers, or registering recurring prompt tasks.\n"
            "Do first: confirm the safety and reversibility of the operation before queuing.\n"
            "Do not: pass sensitive credentials or secrets directly to shell commands.\n"
            "Output contract: list each queued command with its approval status."
        ),
    ),
    SkillDef(
        name="monitoring_jobs",
        description="Monitor job scheduling, alert routing, and run/alert inspection",
        tools=[
            "schedule_monitor_job",
            "list_monitor_jobs",
            "update_monitor_job",
            "pause_monitor_job",
            "resume_monitor_job",
            "test_monitor_job_once",
            "list_monitor_job_runs",
            "list_monitor_alerts",
        ],
        instructions=(
            "When to use: creating, tuning, or operating monitor jobs and alert delivery policies.\n"
            "Do first: confirm source URL, cron, timezone, detector thresholds, and cooldown settings.\n"
            "Do not: enable agent_delivery without an explicit target project_id.\n"
            "Output contract: return monitor_job_id, next_run_at, and current alert policy for every change."
        ),
    ),
    SkillDef(
        name="native_execution",
        description="Run Center integration & native device control",
        tools=[
            "list_native_devices", "run_native_job",
            "check_execution_result", "wait_for_execution",
        ],
        instructions=(
            "When to use: executing jobs on the user's local or remote native devices (e.g. file ops, window management, shell).\n"
            "Do first: call list_native_devices to find the appropriate target device ID.\n"
            "Do not: perform high-risk actions without user approval.\n"
            "Output contract: return the execution result or queued status ID from the Run Center."
        ),
    ),
    SkillDef(
        name="external_comms",
        description="Email, calendar, messaging & external task management (populated by integration refresh)",
        tools=[],
        instructions=(
            "When to use: sending emails, scheduling meetings, posting messages, or managing external tasks.\n"
            "Do first: confirm recipient, subject, and content with the user before sending.\n"
            "Do not: transmit PII or confidential information without explicit user review.\n"
            "Output contract: return send/receive status and timestamp for every external action."
        ),
    ),
    SkillDef(
        name="planning_tracking",
        description="Plan initialization, progress updates & status checks",
        tools=[
            "init_plan", "update_plan_progress", "get_current_status",
        ],
        instructions=(
            "When to use: initializing a project plan, recording milestone progress, or checking current status.\n"
            "Do first: read the current plan status with get_current_status before writing updates.\n"
            "Do not: overwrite completed sections without explicit instruction.\n"
            "Output contract: every update must include completion percentage and the next pending step."
        ),
    ),
    SkillDef(
        name="delegation",
        description="Delegate subtasks to specialized sub-agents",
        tools=["delegate_task", "wait_for_delegation", "receive_delegation_results"],
        instructions=(
            "When to use: breaking a complex task into sub-tasks to be handled by specialized agents.\n"
            "Do first: clearly define the scope, deliverables, and constraints of each sub-task.\n"
            "Do not: delegate tasks that involve security-sensitive data without appropriate access controls.\n"
            "Output contract: report the delegated agent's result verbatim without modification."
        ),
    ),
]

ALL_SKILL_NAMES = [s.name for s in SKILL_DEFS]
