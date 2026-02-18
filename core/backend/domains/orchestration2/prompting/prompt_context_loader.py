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


async def load_prompt_components(
    db: AsyncSession, project_id: str, user_id: str, skills: list[Any]
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
