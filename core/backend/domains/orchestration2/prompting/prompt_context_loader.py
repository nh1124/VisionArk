from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

async def fetch_project_skills(db: AsyncSession, project_id: str) -> list[Any]:
    """Fetch active skills attached to the project agent."""
    from shared.database import ProjectSkill, Skill, ProjectAgent as AgentModel

    try:
        # Find project agent
        agent_res = await db.execute(
            select(AgentModel).filter(
                AgentModel.project_id == project_id,
                AgentModel.role_name == "project",
                AgentModel.status == "active",
            )
        )
        agent = agent_res.scalars().first()
        if not agent:
            return []

        # Find attached active skills
        skill_res = await db.execute(
            select(Skill)
            .join(ProjectSkill, ProjectSkill.skill_id == Skill.id)
            .filter(ProjectSkill.agent_id == agent.id, Skill.is_active == True)
        )
        return skill_res.scalars().all()
    except Exception as e:
        logger.warning("Failed to fetch project skills: %s", e)
        return []


def _build_planner_capabilities(skills: list[Any], tool_registry: Any) -> str:
    """Generate a snapshot of available capabilities for the planner."""
    lines = ["## Available Capabilities"]
    
    # 1. List Skills
    if skills:
        lines.append("\n### Skills (High-level groupings)")
        for s in skills:
            # Handle both SkillDef objects and DB models
            name = getattr(s, "name", "")
            desc = getattr(s, "description", "")
            lines.append(f"- **{name}**: {desc}")
            
    # 2. List Tools by Skill
    lines.append("\n### Tools (Actionable commands)")
    
    # Map skill -> tools
    skill_tools_map: dict[str, list[str]] = {}
    
    # Initialize with skills
    for s in skills:
        name = getattr(s, "name", "")
        skill_tools_map[name] = []
        
        # Tools list can be in .tools (SkillDef) or .metadata_payload["tools"] (DB model)
        tools = getattr(s, "tools", [])
        if not tools and hasattr(s, "metadata_payload"):
             tools = s.metadata_payload.get("tools", [])
             
        for t_name in tools:
            skill_tools_map[name].append(t_name)

    # Collect all registered tools to get descriptions
    for skill_name, tool_names in skill_tools_map.items():
        if not tool_names:
            continue
            
        lines.append(f"\n#### Skill: {skill_name}")
        for t_name in tool_names:
            try:
                # We need tool registry to get description
                tool_def = tool_registry.get_def(t_name)
                desc = tool_def.description.split("\n")[0] if tool_def.description else "No description"
                lines.append(f"- `{t_name}`: {desc}")
            except Exception:
                # Tool might be in skill def but not registered in engine
                lines.append(f"- `{t_name}`: (Tool definition not found)")

    return "\n".join(lines)


async def load_prompt_components(
    db: AsyncSession, 
    project_id: str, 
    user_id: str, 
    skills: list[Any],
    engine: Any | None = None,  # Added engine
    all_skills: list[Any] | None = None # Added all_skills
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

    # 4. Skills text (from passed skills)
    if skills:
        texts = []
        skill_map = {}
        for s in skills:
            content = f"### {s.name}\n{s.content}"
            texts.append(content)
            skill_map[s.name] = content
        
        result["skills_text"] = "\n\n".join(texts)
        result["skill_definitions"] = skill_map

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

    # 6. Planner capabilities (snapshot)
    if engine and all_skills:
        try:
            result["planner_capabilities"] = _build_planner_capabilities(all_skills, engine.tools)
        except Exception as e:
            logger.warning("Failed to build planner capabilities: %s", e)

    return result
