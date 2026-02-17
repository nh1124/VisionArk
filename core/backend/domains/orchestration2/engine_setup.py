"""Engine setup — bootstraps an AgentEngine per request.

This is VisionArk-specific glue code (NOT part of orchestration2 core).
It registers tools, skills, roles, models, graphs, and agents for a given
project context.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .engine.agent_engine import AgentEngine
from .engine.models.agent import AgentDef, AgentLimits
from .engine.models.execution import ExecutionContext, SkillResult
from .engine.models.message import Message
from .engine.models.skill import SkillDef
from .engine.models.tool import ToolDef
from .roles.planner_role import PlannerRole
from .roles.project_role import ProjectRole
from .roles.responder_role import ResponderRole
from .roles.verifier_role import VerifierRole
from .engine.store.sqlalchemy_store import SQLAlchemyStore

from .engine_runtime.gemini_engine import GeminiEngine

logger = logging.getLogger(__name__)


# ── No-op skill impl (used purely for tool-filtering, never executed) ─

class _NoOpSkill:
    """Minimal BaseSkill-compatible impl for tool-filtering-only skills."""

    def __init__(self, skill_def: SkillDef) -> None:
        self.definition = skill_def

    async def run(self, input_message: Message, ctx: ExecutionContext) -> SkillResult:
        raise NotImplementedError("This skill is used for tool filtering only")


# ── Skill group definitions ──────────────────────────────────────────

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


# ── Graph YAML ────────────────────────────────────────────────────────

PROJECT_GRAPH_YAML = """
graph_name: project_assistant
start: plan
steps:
  - id: plan
    type: role
    role: planner
    skills: [investigation]
    limits:
      max_turns: 10
    on:
      - when: "event.type == 'done'"
        next: execute
      - when: default
        next: plan
  - id: execute
    type: role
    role: project
    skills: [investigation, document_creation, file_management, operation]
    limits:
      max_turns: 25
      max_tool_calls: 50
    on:
      - when: "event.type == 'done'"
        next: verify
      - when: default
        next: execute
  - id: verify
    type: role
    role: verifier
    skills: [investigation]
    limits:
      max_turns: 5
      max_tool_calls: 10
    on:
      - when: "event.type == 'done'"
        next: respond
      - when: default
        next: verify
  - id: respond
    type: role
    role: responder
    skills: []
    terminal: true
"""


# ── Tool discovery ────────────────────────────────────────────────────

def _get_all_tools() -> list[tuple[ToolDef, Any]]:
    """Return all tool (definition, implementation) pairs."""
    from .tools.library.files import (
        SaveArtifactTool, ReadReferenceTool, ListFilesTool,
        DeleteArtifactTool, ImportGitHubRepoTool,
    )
    from .tools.library.search import (
        GoogleSearchTool, ResearchURLTool, SearchPlacesTool, DeepResearchTool,
    )
    from .tools.library.ai import (
        GenerateImageTool, MermaidVisualizerTool, ExecuteCodeTool,
    )
    from .tools.library.browser import (
        BrowserOpenTool, BrowserClickTool, BrowserFillTool, BrowserScreenshotTool,
    )
    from .tools.library.canvas import UpdateCanvasTool
    from .tools.library.governance import GetProjectRulesTool, UpdateProjectRulesTool
    from .tools.library.notes import ListNotesTool, ReadNoteTool, CreateNoteTool
    from .tools.library.system import (
        ListAgentsTool, GetAgentProfileTool,
        ListUserProjectsTool, UpdateProjectTool,
        GetProjectHealthTool, SetTimerTool, RaiseContinueTool,
    )
    from .tools.library.members import (
        ListMembersTool, ManageMemberTool, UpdateAgentDescriptionTool,
    )
    from .tools.library.writer import RecursiveWriterTool
    from .tools.library.shell import RunSafeShellTool

    from .tools.library.markdown import (
        ReadMDSectionTool, InitPlanTool, UpdatePlanProgressTool,
        GetCurrentStatusTool, UpdateMDSectionTool,
    )

    tool_classes = [
        # Files
        SaveArtifactTool, ReadReferenceTool, ListFilesTool,
        DeleteArtifactTool, ImportGitHubRepoTool,
        # Search
        GoogleSearchTool, ResearchURLTool, SearchPlacesTool, DeepResearchTool,
        # AI
        GenerateImageTool, MermaidVisualizerTool, ExecuteCodeTool,
        # Browser
        BrowserOpenTool, BrowserClickTool, BrowserFillTool, BrowserScreenshotTool,
        # Canvas
        UpdateCanvasTool,
        # Governance
        GetProjectRulesTool, UpdateProjectRulesTool,
        # Notes
        ListNotesTool, ReadNoteTool, CreateNoteTool,
        # System
        ListAgentsTool, GetAgentProfileTool,
        ListUserProjectsTool, UpdateProjectTool,
        GetProjectHealthTool, SetTimerTool, RaiseContinueTool,
        # Members
        ListMembersTool, ManageMemberTool, UpdateAgentDescriptionTool,
        # Writer
        RecursiveWriterTool,
        # Shell
        RunSafeShellTool,

        # Markdown
        ReadMDSectionTool, InitPlanTool, UpdatePlanProgressTool,
        GetCurrentStatusTool, UpdateMDSectionTool,
    ]

    result = []
    for cls in tool_classes:
        instance = cls()
        result.append((instance.definition, instance))
    return result


# ── Prompt loading helpers ────────────────────────────────────────────

async def _load_prompt_components(
    db: AsyncSession, project_id: str, user_id: str
) -> dict[str, Any]:
    """Pre-load all data needed by ProjectRole.build_prompt().

    Returns a dict of metadata keys ready to merge into ctx.metadata.
    """
    result: dict[str, Any] = {}

    # 1. Prompt components (static files)
    try:
        from shared.paths import get_prompts_dir

        prompts_dir = get_prompts_dir()
        components = []
        for comp_name in ["identity", "formatting"]:
            comp_path = prompts_dir / "components" / f"{comp_name}.md"
            if comp_path.exists():
                components.append(comp_path.read_text(encoding="utf-8"))
        result["system_prompt_components"] = components
    except Exception as e:
        logger.warning("Failed to load prompt components: %s", e)

    # 2. Agent profile (DB)
    try:
        from shared.database import ProjectAgent

        res = await db.execute(
            select(ProjectAgent).filter(
                ProjectAgent.project_id == project_id,
                ProjectAgent.role_name == "project",
                ProjectAgent.status == "active",
            )
        )
        agent = res.scalars().first()
        if agent and agent.system_prompt:
            result["agent_profile"] = agent.system_prompt
    except Exception as e:
        logger.warning("Failed to load agent profile: %s", e)

    # 3. Project plan (PLAN.md)
    try:
        from shared.paths import get_plan_path

        plan_path = get_plan_path(user_id, project_id)
        if plan_path.exists():
            result["project_plan"] = plan_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        logger.warning("Failed to load project plan: %s", e)

    # 4. Skills text
    try:
        from shared.database import ProjectSkill, Skill, ProjectAgent as AgentModel

        agent_res = await db.execute(
            select(AgentModel).filter(
                AgentModel.project_id == project_id,
                AgentModel.role_name == "project",
            )
        )
        agent = agent_res.scalars().first()
        if agent:
            skill_res = await db.execute(
                select(Skill)
                .join(ProjectSkill, ProjectSkill.skill_id == Skill.id)
                .filter(ProjectSkill.agent_id == agent.id, Skill.is_active == True)
            )
            skills = skill_res.scalars().all()
            if skills:
                texts = []
                skill_map = {}
                for s in skills:
                    content = f"### {s.name}\n{s.content}"
                    texts.append(content)
                    skill_map[s.name] = content
                
                result["skills_text"] = "\n\n".join(texts)
                result["skill_definitions"] = skill_map
    except Exception as e:
        logger.warning("Failed to load skills: %s", e)

    # 5. User settings
    try:
        from shared.database import UserSettings

        res = await db.execute(
            select(UserSettings).filter(UserSettings.user_id == user_id)
        )
        settings = res.scalars().first()
        if settings and settings.general_settings:
            result["user_settings"] = settings.general_settings
    except Exception as e:
        logger.warning("Failed to load user settings: %s", e)

    return result


# ── Main factory function ─────────────────────────────────────────────

async def create_engine_for_project(
    project_id: str,
    user_id: str,
    db_session: AsyncSession,
    api_key: str,
    preferred_model: str | None = None,
) -> tuple[AgentEngine, str]:
    """Bootstrap an AgentEngine for a project context. Called per-request.

    Returns (engine, agent_id).
    """
    store = SQLAlchemyStore(db_session)

    # 1. Create engine
    engine = AgentEngine(store=store)

    # 2. Register all tools
    for tool_def, tool_impl in _get_all_tools():
        engine.register_tool(tool_def, tool_impl)
        
    # 2b. Register integration tools
    # 2b. Register integration tools and reflect them into Skills/Prompts
    integration_tools_text = ""
    dynamic_skills = [s.model_copy() for s in SKILL_DEFS]
    
    try:
        from integrations.loader import load_integration_tools
        integration_tools = await load_integration_tools(user_id, db_session)
        
        valid_integrations = []
        for tool_def, tool_impl in integration_tools:
            # Duplicate check: Core tools take precedence
            try:
                engine.get_tool(tool_def.name)
                logger.warning(
                    "Integration tool '%s' skipped (shadows existing core tool)", 
                    tool_def.name
                )
            except Exception:
                # Tool does not exist, safe to register
                engine.register_tool(tool_def, tool_impl)
                valid_integrations.append(tool_def)

        # Dynamic Reflection: Inject valid tools into "operation" skill (default)
        # and build prompt text.
        if valid_integrations:
            # Add to 'operation' skill
            for s in dynamic_skills:
                if s.name == "operation":
                    s.tools.extend([t.name for t in valid_integrations])
            
            # Build prompt text
            lines = ["The following external integration tools are available:\n"]
            for tool in valid_integrations:
                lines.append(f"- {tool.name}: {tool.description}")
                # Optional: Add args schema if helpful, but keeping it brief for now
            integration_tools_text = "\n".join(lines)
                
        logger.info("Registered %d integration tools", len(valid_integrations))
    except Exception as e:
        logger.warning("Failed to load integration tools: %s", e)

    # 3. Create GeminiEngine (uses Gemini SDK directly, no LLMProvider wrapper)
    gemini_engine = GeminiEngine(
        api_key=api_key,
        tool_registry=engine.tools,
        model=preferred_model,
    )

    # 5. Register engine runtime via public API
    engine.register_engine(gemini_engine)

    # 6. Register model config (for metadata; provider_impl no longer used)
    engine.register_model("default", preferred_model or "gemini-3-pro-preview")

    # 7. Register skills (for tool filtering)
    # 7. Register skills (for tool filtering)
    for skill_def in dynamic_skills:
        engine.register_skill(skill_def, _NoOpSkill(skill_def))

    # 8. Register roles
    engine.register_role(PlannerRole())
    engine.register_role(ProjectRole())
    engine.register_role(VerifierRole())
    engine.register_role(ResponderRole())

    # 9. Register graph
    engine.register_graph(PROJECT_GRAPH_YAML)

    # 10. Pre-load prompt data
    prompt_data = await _load_prompt_components(db_session, project_id, user_id)
    if integration_tools_text:
        prompt_data["integration_tools_text"] = integration_tools_text

    # 11. Register agent
    agent_def = AgentDef(
        name=f"project_{project_id}",
        graph_name="project_assistant",
        default_model="default",
        skills=ALL_SKILL_NAMES,
        limits=AgentLimits(max_turns=25),
    )
    agent_id = engine.register_agent(agent_def)

    # Store prompt data in a way that will be merged into run metadata
    engine._prompt_data = prompt_data  # type: ignore[attr-defined]


    return engine, agent_id
