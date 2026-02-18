from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..engine.agent_engine import AgentEngine
from ..engine.models.agent import AgentDef, AgentLimits
from ..engine.models.skill import SkillDef
from ..engine.store.sqlalchemy_store import SQLAlchemyStore
from ..engine_runtime.gemini_engine import GeminiEngine
from ..roles.planner_role import PlannerRole
from ..roles.project_role import ProjectRole
from ..roles.verifier_role import VerifierRole
from ..roles.responder_role import ResponderRole

# New components
from ..config.skills.default_skills import SKILL_DEFS, ALL_SKILL_NAMES
from ..config.tools.default_catalog import get_core_tools
from ..prompting.prompt_context_loader import fetch_project_skills, load_prompt_components
from ..integrations.tool_reflection import register_and_reflect_integrations
from ..skills.noop import NoOpSkill

logger = logging.getLogger(__name__)

def _load_graph_yaml() -> str:
    """Load the project assistant graph definition."""
    # Assuming this file is in bootstrap/
    # And graph is in config/graphs/
    current_dir = Path(__file__).parent
    graph_path = current_dir.parent / "config" / "graphs" / "project_assistant.yaml"
    if not graph_path.exists():
        logger.error(f"Graph definition not found at {graph_path}")
        return ""
    return graph_path.read_text(encoding="utf-8")


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

    # 6. Register model config
    engine.register_model("default", preferred_model or "gemini-3-pro-preview")

    # 7. Register skills (for tool filtering)
    # 7a. Static Skills
    for skill_def in dynamic_skills:
        # Use simple NoOpSkill wrapper
        engine.register_skill(skill_def, NoOpSkill(skill_def))
    
    # 7b. DB Skills
    db_skills = await fetch_project_skills(db_session, project_id)
    db_skill_names = []
    
    for s in db_skills:
        try:
            # Create SkillDef from DB model
            meta = s.metadata_payload or {}
            tools_list = meta.get("tools", [])
            
            # Normalize tools list
            if not isinstance(tools_list, list):
                tools_list = []
            
            s_def = SkillDef(
                name=s.name,
                description=s.description or "",
                tools=tools_list,
                request_approval=meta.get("request_approval", False)
            )
            
            # Register if not exists
            if not engine.skills.has(s.name):
                engine.register_skill(s_def, NoOpSkill(s_def))
                db_skill_names.append(s.name)
                # Keep track of skill def for prompting
                dynamic_skills.append(s_def)
            else:
                logger.warning(f"DB Skill '{s.name}' skipped (shadows existing skill).")
                db_skill_names.append(s.name)

        except Exception as e:
            logger.warning(f"Failed to register DB skill {s.id}: {e}")

    # 8. Register roles
    engine.register_role(PlannerRole())
    engine.register_role(ProjectRole())
    engine.register_role(VerifierRole())
    engine.register_role(ResponderRole())

    # 9. Register graph
    graph_yaml = _load_graph_yaml()
    if graph_yaml:
        engine.register_graph(graph_yaml)
    else:
        logger.warning("Graph definition is empty or missing.")

    # 10. Pre-load prompt data
    prompt_data = await load_prompt_components(
        db_session, 
        project_id, 
        user_id, 
        db_skills,
        engine=engine,
        all_skills=dynamic_skills
    )
    if integration_tools_text:
        prompt_data["integration_tools_text"] = integration_tools_text

    # 11. Register agent
    # Assemble all skill names: Static + DB
    all_skill_names = ALL_SKILL_NAMES + db_skill_names

    agent_def = AgentDef(
        name=f"project_{project_id}",
        graph_name="project_assistant",
        default_model="default",
        skills=all_skill_names,
        limits=AgentLimits(max_turns=25),
    )
    agent_id = engine.register_agent(agent_def)

    # Store prompt data
    engine._prompt_data = prompt_data  # type: ignore[attr-defined]

    return engine, agent_id
