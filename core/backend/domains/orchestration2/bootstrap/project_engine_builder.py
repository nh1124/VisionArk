from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import AsyncSessionLocal, ProjectAgentAssignment, Agent as UserAgent
from ..engine.agent_engine import AgentEngine
from ..engine.models.agent import AgentDef, AgentLimits
from ..engine.models.skill import SkillDef
from ..engine.store.sqlalchemy_store import SQLAlchemyStore
from ..roles.planner_role import PlannerRole
from ..roles.project_role import ProjectRole
from ..roles.verifier_role import VerifierRole
from ..roles.responder_role import ResponderRole
from ..roles.direct_role import DirectRole

# New components
from ..config.skills.default_skills import SKILL_DEFS
from ..config.tools.default_catalog import get_core_tools, get_delegation_tools
from ..prompting.prompt_context_loader import load_prompt_components
from ..integrations.tool_reflection import register_and_reflect_integrations
from ..skills.noop import NoOpSkill

logger = logging.getLogger(__name__)


async def _load_active_tool_names_from_db(
    user_id: str, db_session: AsyncSession
) -> set[str] | None:
    """Return the set of is_active=True tool names for a user from tool_registry.

    Returns None when the registry has no rows for this user (not yet seeded),
    which triggers the caller to register all tools as a fallback.
    """
    try:
        from shared.database import ToolRegistry
        result = await db_session.execute(
            select(ToolRegistry.name).where(
                ToolRegistry.user_id == user_id,
                ToolRegistry.is_active == True,  # noqa: E712
            )
        )
        names = set(result.scalars().all())
        if names:
            return names
    except Exception as exc:
        logger.warning(
            "Failed to load active tool names from DB for user %s: %s", user_id, exc
        )
    return None


async def _load_skills_from_db(user_id: str, db_session: AsyncSession) -> list[SkillDef]:
    """Load active skill definitions from DB for a user.

    Falls back to static SKILL_DEFS if the DB has no active rows (e.g. first
    request before seed completes, or after a failed migration).
    """
    try:
        from shared.database import SkillRegistry
        result = await db_session.execute(
            select(SkillRegistry).where(
                SkillRegistry.user_id == user_id,
                SkillRegistry.is_active == True,  # noqa: E712
            )
        )
        rows = result.scalars().all()
        if rows:
            return [
                SkillDef(
                    name=row.name,
                    description=row.description or "",
                    tools=row.tools or [],
                    instructions=row.instructions or None,
                )
                for row in rows
            ]
    except Exception as exc:
        logger.warning("Failed to load skills from DB for user %s: %s 窶・falling back to SKILL_DEFS", user_id, exc)

    # Fallback: DB not ready or empty
    logger.info("No DB skills found for user %s 窶・using static SKILL_DEFS", user_id)
    return [s.model_copy() for s in SKILL_DEFS]


def _load_graph_yamls() -> list[str]:
    """Load all graph definitions from config/graphs/."""
    current_dir = Path(__file__).parent
    graphs_dir = current_dir.parent / "config" / "graphs"
    if not graphs_dir.exists():
        logger.error(f"Graphs directory not found at {graphs_dir}")
        return []
    yamls = []
    for graph_path in sorted(graphs_dir.glob("*.yaml")):
        content = graph_path.read_text(encoding="utf-8")
        if content.strip():
            yamls.append(content)
            logger.debug("Loaded graph definition: %s", graph_path.name)
    return yamls


async def create_engine_for_project(
    project_id: str,
    user_id: str,
    db_session: AsyncSession,
    api_key: str,
    preferred_model: str | None = None,
    provider_id: str = "gemini",
) -> tuple[AgentEngine, str]:
    """Bootstrap an AgentEngine for a project context. Called per-request.

    Returns (engine, agent_id).
    """
    # SQLAlchemyStore must NOT share the caller's db_session because the
    # orchestration engine runs in a separate asyncio.Task (async_mode=True).
    # SQLAlchemy's asyncpg dialect must not be shared across Task boundaries.
    # Pass the session factory so each Store operation uses its own session.
    store = SQLAlchemyStore(AsyncSessionLocal)

    # 1. Create engine
    engine = AgentEngine(store=store)

    # 2. Load active tool names from DB for filtering.
    #    Returns None when tool_registry has no rows yet 竊・lazy-seed, then register all tools.
    active_tool_names = await _load_active_tool_names_from_db(user_id, db_session)

    if active_tool_names is None:
        # Lazy-seed: handles users created before tool_registry was introduced.
        logger.info("tool_registry empty for user %s 窶・seeding now", user_id)
        try:
            from shared.database import get_engine as _get_engine
            from domains.orchestration2.bootstrap.definition_refresh_service import refresh_core_sync
            await asyncio.to_thread(refresh_core_sync, _get_engine(), user_id)
            active_tool_names = await _load_active_tool_names_from_db(user_id, db_session)
        except Exception as exc:
            logger.warning("Failed to seed tool_registry for user %s: %s", user_id, exc)

    # Register core tools 窶・only those with is_active=True in tool_registry.
    # If active_tool_names is still None (seed failed), register all tools as fallback.
    for tool_def, tool_impl in get_core_tools():
        if active_tool_names is None or tool_def.name in active_tool_names:
            engine.register_tool(tool_def, tool_impl)

    # 2b. Load skills from DB (source of truth) 窶・falls back to SKILL_DEFS if needed.
    # We work with copies so integration tool injection doesn't mutate the DB rows.
    dynamic_skills = await _load_skills_from_db(user_id, db_session)
    dynamic_skills = [s.model_copy() for s in dynamic_skills]

    # Register integration tools and build the prompt text about available integrations.
    # Skills are NOT modified here 窶・operation skill injection now happens via DB refresh.
    integration_tools_text = await register_and_reflect_integrations(
        user_id, db_session, engine
    )

    # 3. Create LLM Engine based on provider
    if provider_id == "openai":
        from ..engine_runtime.openai_engine import OpenAIEngine
        llm_engine = OpenAIEngine(
            api_key=api_key,
            tool_registry=engine.tools,
            model=preferred_model,
        )
    elif provider_id == "anthropic":
        from ..engine_runtime.anthropic_engine import AnthropicEngine
        llm_engine = AnthropicEngine(
            api_key=api_key,
            tool_registry=engine.tools,
            model=preferred_model,
        )
    else:
        from ..engine_runtime.gemini_engine import GeminiEngine
        llm_engine = GeminiEngine(
            api_key=api_key,
            tool_registry=engine.tools,
            model=preferred_model,
        )

    # 5. Register engine runtime via public API
    engine.register_engine(llm_engine)

    # 5b. Register delegation tools (require engine reference 窶・_orchestrator must exist)
    for delegation_tool_def, delegation_tool_impl in get_delegation_tools(engine):
        engine.register_tool(delegation_tool_def, delegation_tool_impl)

    # 6. Register model config
    engine.register_model("default", preferred_model or "gemini-3.1-pro-preview")

    # 7. Register skills (for tool filtering)
    for skill_def in dynamic_skills:
        # Use simple NoOpSkill wrapper
        engine.register_skill(skill_def, NoOpSkill(skill_def))

    # 8. Register roles
    engine.register_role(PlannerRole())
    engine.register_role(ProjectRole())
    engine.register_role(VerifierRole())
    engine.register_role(ResponderRole())
    engine.register_role(DirectRole())

    # 9. Register graphs (all YAML files in config/graphs/)
    graph_yamls = _load_graph_yamls()
    if graph_yamls:
        for graph_yaml in graph_yamls:
            engine.register_graph(graph_yaml)
    else:
        logger.warning("No graph definitions found.")

    # 10. Pre-load prompt data
    prompt_data = await load_prompt_components(
        db_session,
        project_id,
        user_id,
        engine=engine,
        all_skills=dynamic_skills,
    )
    if integration_tools_text:
        prompt_data["integration_tools_text"] = integration_tools_text

    # 11. Resolve main agent from the project's default assignment.
    # Source of truth is the project settings page:
    # - enabled agents: project_agent_assignments
    # - main agent: is_default=True assignment
    agent_skills = [s.name for s in dynamic_skills]
    resolved_graph_id: str = "direct_assistant"
    try:
        assignment_res = await db_session.execute(
            select(ProjectAgentAssignment).where(
                ProjectAgentAssignment.project_id == project_id,
                ProjectAgentAssignment.is_default == True,
            )
        )
        assignment = assignment_res.scalar_one_or_none()
        if assignment is None:
            raise ValueError(
                f"No default agent assignment configured for project {project_id}"
            )

        user_agent_res = await db_session.execute(
            select(UserAgent).where(
                UserAgent.id == assignment.agent_id,
                UserAgent.user_id == user_id,
                UserAgent.status == "active",
            )
        )
        user_agent = user_agent_res.scalar_one_or_none()
        if user_agent is None:
            raise ValueError(
                f"Default assigned agent {assignment.agent_id} is missing or inactive"
            )

        # skill_ids=[] means "all active skills"; preserve that contract.
        if user_agent.skill_ids:
            agent_skills = user_agent.skill_ids
        if user_agent.graph_id:
            resolved_graph_id = user_agent.graph_id
        logger.info(
            "Project %s: using main agent '%s' (graph=%s, skills=%s)",
            project_id,
            user_agent.display_name,
            resolved_graph_id,
            agent_skills,
        )
    except Exception as e:
        logger.warning(
            "Failed to resolve default agent config for project %s: %s",
            project_id,
            e,
        )
        raise

    # 12. Register main project agent
    agent_def = AgentDef(
        name=f"project_{project_id}",
        graph_name=resolved_graph_id,
        default_model="default",
        skills=agent_skills,
        limits=AgentLimits(max_turns=25),
    )
    agent_id = engine.register_agent(agent_def)

    # Store prompt data
    engine._prompt_data = prompt_data  # type: ignore[attr-defined]

    # 13. Register delegation sub-agents from project-enabled agents.
    # Source of truth:
    # - User agent registry (seeded and user-created)
    # - Project settings (project_agent_assignments) for enable/default control
    # Max turns per sub-agent (DB has no limits field; use sensible defaults).
    _SUB_AGENT_MAX_TURNS: dict[str, int] = {
        "researcher": 15,
        "writer": 15,
        "reviewer": 10,
    }
    try:
        enabled_result = await db_session.execute(
            select(ProjectAgentAssignment, UserAgent)
            .join(UserAgent, ProjectAgentAssignment.agent_id == UserAgent.id)
            .where(
                ProjectAgentAssignment.project_id == project_id,
                UserAgent.user_id == user_id,
                UserAgent.status == "active",
            )
        )
        enabled_rows = enabled_result.all()
        if not enabled_rows:
            logger.warning(
                "No enabled project agents configured for project %s (user=%s)",
                project_id,
                user_id,
            )

        seen_names: set[str] = set()
        for assignment, row in enabled_rows:
            # The default assignment is the main project agent, not a delegation sub-agent.
            if assignment.is_default:
                continue
            if not row.display_name:
                logger.warning("Skipping enabled agent with empty display_name: id=%s", row.id)
                continue
            if row.display_name in seen_names:
                logger.warning(
                    "Duplicate enabled agent display_name '%s' for project %s; skipping duplicate",
                    row.display_name,
                    project_id,
                )
                continue

            seen_names.add(row.display_name)
            sub_def = AgentDef(
                name=row.display_name,
                graph_name=row.graph_id or "direct_assistant",
                default_model="default",
                skills=row.skill_ids or [],
                limits=AgentLimits(max_turns=_SUB_AGENT_MAX_TURNS.get(row.display_name, 15)),
            )
            engine.register_agent(sub_def)
            logger.debug(
                "Registered sub-agent '%s' (graph=%s, skills=%s)",
                sub_def.name, sub_def.graph_name, sub_def.skills,
            )
    except Exception as exc:
        logger.warning("Failed to load delegation sub-agents from project settings: %s", exc)

    return engine, agent_id
