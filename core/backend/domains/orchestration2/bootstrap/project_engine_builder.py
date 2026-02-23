from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import AsyncSessionLocal, ProjectAgentAssignment, Agent as UserAgent, get_engine
from ..engine.agent_engine import AgentEngine
from ..engine.models.agent import AgentDef, AgentLimits
from ..engine.models.skill import SkillDef
from ..engine.store.sqlalchemy_store import SQLAlchemyStore
from ..engine_runtime.gemini_engine import GeminiEngine
from ..roles.planner_role import PlannerRole
from ..roles.project_role import ProjectRole
from ..roles.verifier_role import VerifierRole
from ..roles.responder_role import ResponderRole
from ..roles.direct_role import DirectRole

# New components
from ..config.skills.default_skills import SKILL_DEFS, ALL_SKILL_NAMES
from ..config.tools.default_catalog import get_core_tools, get_delegation_tool
from ..prompting.prompt_context_loader import load_prompt_components
from ..integrations.tool_reflection import register_and_reflect_integrations
from ..skills.noop import NoOpSkill

logger = logging.getLogger(__name__)

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

    # 2. Register all core tools
    for tool_def, tool_impl in get_core_tools():
        engine.register_tool(tool_def, tool_impl)
        
    # 2b. Register integration tools and reflect them into Skills/Prompts
    # We copy SKILL_DEFS to modify it dynamically for this request
    dynamic_skills = [s.model_copy() for s in SKILL_DEFS]
    
    integration_tools_text = await register_and_reflect_integrations(
        user_id, db_session, engine, dynamic_skills
    )

    # 3. Create GeminiEngine
    gemini_engine = GeminiEngine(
        api_key=api_key,
        tool_registry=engine.tools,
        model=preferred_model,
    )

    # 5. Register engine runtime via public API
    engine.register_engine(gemini_engine)

    # 5b. Register delegation tool (requires engine reference — _orchestrator must exist)
    delegation_tool_def, delegation_tool_impl = get_delegation_tool(engine)
    engine.register_tool(delegation_tool_def, delegation_tool_impl)

    # 6. Register model config
    engine.register_model("default", preferred_model or "gemini-3-pro-preview")

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

    # 11. Resolve skills and graph from the project's default agent assignment (if any)
    #
    # graph_name is currently PINNED to "direct_assistant" for all projects.
    # The resolved_graph_id below is fetched from the agent record in DB so that
    # future dynamic graph routing only requires removing the override line.
    #   TODO: replace `graph_name = "direct_assistant"` with `graph_name = resolved_graph_id`
    #         once multi-graph support is fully tested.
    agent_skills = ALL_SKILL_NAMES
    resolved_graph_id: str = "direct_assistant"  # default
    try:
        assignment_res = await db_session.execute(
            select(ProjectAgentAssignment).where(
                ProjectAgentAssignment.project_id == project_id,
                ProjectAgentAssignment.is_default == True,
            )
        )
        assignment = assignment_res.scalar_one_or_none()
        if assignment:
            user_agent_res = await db_session.execute(
                select(UserAgent).where(UserAgent.id == assignment.agent_id)
            )
            user_agent = user_agent_res.scalar_one_or_none()
            if user_agent:
                # skill_ids=[] (empty list) means "all skills" — created by default
                # on project creation. Only override when the list is non-empty.
                if user_agent.skill_ids:
                    agent_skills = user_agent.skill_ids
                    logger.info(
                        "Project %s: using agent '%s' skills: %s",
                        project_id, user_agent.display_name, agent_skills,
                    )
                if user_agent.graph_id:
                    resolved_graph_id = user_agent.graph_id
                    logger.debug(
                        "Project %s: agent '%s' has graph_id='%s' "
                        "(currently overridden to 'direct_assistant' — see TODO above)",
                        project_id, user_agent.display_name, resolved_graph_id,
                    )
    except Exception as e:
        logger.warning("Failed to resolve default agent config for project %s: %s", project_id, e)

    # 12. Register agent
    # NOTE: graph_name is pinned to "direct_assistant" regardless of resolved_graph_id.
    #       To enable dynamic routing: swap the hardcoded value for `resolved_graph_id`.
    agent_def = AgentDef(
        name=f"project_{project_id}",
        graph_name="direct_assistant",  # TODO: use `resolved_graph_id` for dynamic graph routing
        default_model="default",
        skills=agent_skills,
        limits=AgentLimits(max_turns=25),
    )
    agent_id = engine.register_agent(agent_def)

    # Store prompt data
    engine._prompt_data = prompt_data  # type: ignore[attr-defined]

    # 13. Load delegation sub-agents from DB and register them in the engine.
    # Sub-agents are seeded at user registration (shared/seed.py).
    # If missing (pre-existing users), seed them lazily here.
    _SUB_AGENT_NAMES = ["researcher", "writer", "reviewer"]
    # Max turns per sub-agent (DB has no limits field; use sensible defaults).
    _SUB_AGENT_MAX_TURNS: dict[str, int] = {
        "researcher": 15,
        "writer": 15,
        "reviewer": 10,
    }
    try:
        # Fetch all known sub-agents for this user in one query
        sub_agents_result = await db_session.execute(
            select(UserAgent).where(
                UserAgent.user_id == user_id,
                UserAgent.display_name.in_(_SUB_AGENT_NAMES),
                UserAgent.status == "active",
            )
        )
        sub_agents_by_name = {
            row.display_name: row for row in sub_agents_result.scalars().all()
        }

        # Lazy-seed any missing sub-agents (handles users registered before this feature)
        missing = [n for n in _SUB_AGENT_NAMES if n not in sub_agents_by_name]
        if missing:
            logger.info(
                "Sub-agents %s not found for user %s — seeding now", missing, user_id
            )
            from shared.seed import seed_user_agents
            await asyncio.to_thread(seed_user_agents, get_engine(), user_id)

            # Re-fetch after seeding
            sub_agents_result2 = await db_session.execute(
                select(UserAgent).where(
                    UserAgent.user_id == user_id,
                    UserAgent.display_name.in_(_SUB_AGENT_NAMES),
                    UserAgent.status == "active",
                )
            )
            sub_agents_by_name = {
                row.display_name: row for row in sub_agents_result2.scalars().all()
            }

        for sub_name in _SUB_AGENT_NAMES:
            row = sub_agents_by_name.get(sub_name)
            if row is None:
                logger.warning("Sub-agent '%s' still missing after seed — skipping", sub_name)
                continue
            sub_def = AgentDef(
                name=sub_name,
                graph_name=row.graph_id or "direct_assistant",
                default_model="default",
                skills=row.skill_ids if row.skill_ids else ["investigation"],
                limits=AgentLimits(max_turns=_SUB_AGENT_MAX_TURNS.get(sub_name, 15)),
            )
            engine.register_agent(sub_def)
            logger.debug(
                "Registered sub-agent '%s' (graph=%s, skills=%s)",
                sub_name, sub_def.graph_name, sub_def.skills,
            )
    except Exception as exc:
        logger.warning("Failed to load delegation sub-agents from DB: %s", exc)

    return engine, agent_id
