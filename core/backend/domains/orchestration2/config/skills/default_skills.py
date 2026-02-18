from ...engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="investigation",
        description="Research & information gathering",
        tools=[
            "google_search", "research_url", "search_places", "deep_research",
            "read_reference", "list_files", "read_md_section",
            "get_current_status", "list_notes", "read_note",
            "get_project_rules", "get_project_health",
            "list_agents", "get_agent_profile",
            "list_user_projects", "list_members",
        ],
    ),
    SkillDef(
        name="document_creation",
        description="Writing & content generation",
        tools=[
            "save_artifact", "recursive_writer",
            "generate_image", "generate_mermaid_visualizer", "execute_code",
            "create_note", "init_plan", "update_plan_progress",
            "update_md_section", "update_canvas",
        ],
    ),
    SkillDef(
        name="file_management",
        description="File CRUD & imports",
        tools=[
            "save_artifact", "read_reference", "list_files",
            "delete_artifact", "import_github_repo",
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
]

ALL_SKILL_NAMES = [s.name for s in SKILL_DEFS]
