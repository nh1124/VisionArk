from ...engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="investigation",
        description="Research & information gathering",
        tools=[
            "google_search", "research_url", "search_places", "deep_research",
            "read_file_chunk", "list_files", "get_file_stat", "read_md_section",
            "get_current_status", "list_notes", "read_note",
            "get_project_rules", "get_project_health",
            "list_agents", "get_agent_profile",
            "list_user_projects", "list_members",
            "list_workspace_items", "read_workspace_item",
        ],
    ),
    SkillDef(
        name="document_creation",
        description="Writing & content generation",
        tools=[
            "write_file", "apply_text_patch", "recursive_writer",
            "generate_image", "generate_mermaid_visualizer", "execute_code",
            "create_note", "init_plan", "update_plan_progress",
            "update_md_section", "update_canvas",
        ],
    ),
    SkillDef(
        name="file_management",
        description="File CRUD & imports",
        tools=[
            "write_file", "read_file_chunk", "list_files", "delete_file",
            "apply_text_patch", "move_file", "copy_file",
            "make_directory", "get_file_stat", "import_github_repo",
        ],
    ),
    SkillDef(
        name="operation",
        description="System & project administration",
        tools=[
            "update_project", "update_project_rules",
            "manage_member", "update_agent_description",
            "set_timer", "raise_continue", "run_safe_shell",
            "browser_open", "browser_click", "browser_fill", "browser_screenshot",
        ],
    ),
    SkillDef(
        name="workspace_management",
        description="Read and write shared workspace items (profile, company info, reusable context), including file and directory management",
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
    ),
    SkillDef(
        name="delegation",
        description="Delegate subtasks to specialized sub-agents (researcher, writer)",
        tools=["delegate_task"],
    ),
]

ALL_SKILL_NAMES = [s.name for s in SKILL_DEFS]
