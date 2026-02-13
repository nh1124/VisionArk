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
from .engine.models.skill import SkillDef
from .engine.models.tool import ToolDef
from .roles.project_role import ProjectRole
from .roles.responder_role import ResponderRole
from .engine.store.sqlalchemy_store import SQLAlchemyStore

logger = logging.getLogger(__name__)

# ── Graph YAML ────────────────────────────────────────────────────────

PROJECT_GRAPH_YAML = """
graph_name: project_assistant
start: main
steps:
  - id: main
    type: role
    role: project
    limits:
      max_turns: 25
      max_tool_calls: 50
    on:
      - when: "event.type == 'done'"
        next: respond
      - when: default
        next: main
  - id: respond
    type: responder
    role: responder
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
        ListAgentsTool, GetAgentProfileTool, AskAgentTool,
        BroadcastSystemMessageTool, ListUserProjectsTool, UpdateProjectTool,
        GetProjectHealthTool, SetTimerTool, RaiseContinueTool,
    )
    from .tools.library.members import (
        ListMembersTool, ManageMemberTool, UpdateAgentDescriptionTool,
    )
    from .tools.library.writer import RecursiveWriterTool
    from .tools.library.shell import RunSafeShellTool
    from .tools.library.routing import (
        MulticastMessageTool, SubscribeIntentTool,
        UnsubscribeIntentTool, ListSubscriptionsTool,
    )
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
        ListAgentsTool, GetAgentProfileTool, AskAgentTool,
        BroadcastSystemMessageTool, ListUserProjectsTool, UpdateProjectTool,
        GetProjectHealthTool, SetTimerTool, RaiseContinueTool,
        # Members
        ListMembersTool, ManageMemberTool, UpdateAgentDescriptionTool,
        # Writer
        RecursiveWriterTool,
        # Shell
        RunSafeShellTool,
        # Routing
        MulticastMessageTool, SubscribeIntentTool,
        UnsubscribeIntentTool, ListSubscriptionsTool,
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
                for s in skills:
                    texts.append(f"### {s.name}\n{s.content}")
                result["skills_text"] = "\n\n".join(texts)
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

    # 6. Team roster
    try:
        from shared.database import ProjectAgent as AgentModel, Project

        roster_parts = []

        # System agents
        sys_res = await db.execute(
            select(AgentModel).filter(AgentModel.agent_type == "SYSTEM", AgentModel.status == "active")
        )
        sys_agents = sys_res.scalars().all()
        if sys_agents:
            roster_parts.append("### System Agents")
            for a in sys_agents:
                desc = a.description or "System capabilities."
                roster_parts.append(f"- **{a.display_name}** (ID: `{a.id}`): {desc}")

        # Member agents
        mem_res = await db.execute(
            select(AgentModel).filter(
                AgentModel.project_id == project_id,
                AgentModel.agent_type == "MEMBER",
                AgentModel.status == "active",
            )
        )
        mem_agents = mem_res.scalars().all()
        if mem_agents:
            roster_parts.append("### Project Members")
            for a in mem_agents:
                desc = a.description or "Project specialist."
                roster_parts.append(f"- **{a.display_name}** (ID: `{a.id}`): {desc}")

        # Peer projects
        peer_res = await db.execute(
            select(AgentModel)
            .join(Project, AgentModel.project_id == Project.id)
            .filter(
                Project.user_id == user_id,
                AgentModel.agent_type == "PROJECT",
                AgentModel.project_id != project_id,
                AgentModel.status == "active",
            )
        )
        peer_agents = peer_res.scalars().all()
        if peer_agents:
            roster_parts.append("### Peer Projects")
            for a in peer_agents:
                desc = a.description or "Peer project."
                roster_parts.append(f"- **{a.display_name}** (ID: `{a.id}`): {desc}")

        if roster_parts:
            result["team_roster"] = "\n## Active Team Roster\n" + "\n".join(roster_parts)
    except Exception as e:
        logger.warning("Failed to load team roster: %s", e)

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
    engine = AgentEngine(store=SQLAlchemyStore(db_session))

    # 1. Register LLM
    from infrastructure.llm.orchestration2_provider import GeminiLLMProvider

    engine.register_model(
        "default",
        "gemini",
        provider_impl=GeminiLLMProvider(api_key, preferred_model),
    )

    # 2. Register all tools
    for tool_def, tool_impl in _get_all_tools():
        engine.register_tool(tool_def, tool_impl)

    # 3. Register roles
    engine.register_role(ProjectRole())
    engine.register_role(ResponderRole())

    # 4. Register graph
    engine.register_graph(PROJECT_GRAPH_YAML)

    # 5. Pre-load prompt data
    prompt_data = await _load_prompt_components(db_session, project_id, user_id)

    # 6. Register agent
    agent_def = AgentDef(
        name=f"project_{project_id}",
        graph_name="project_assistant",
        default_model="default",
        limits=AgentLimits(max_turns=25),
    )
    agent_id = engine.register_agent(agent_def)

    # Store prompt data in a way that will be merged into run metadata
    engine._prompt_data = prompt_data  # type: ignore[attr-defined]

    return engine, agent_id
