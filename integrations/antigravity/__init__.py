"""Antigravity CLI integration for VisionArk.

Provides agent tools for running Antigravity CLI commands
on connected native devices.

Activation: register service_name='antigravity' in ServiceRegistry (is_active=True).
"""

from .agent_tools import AntigravityCheckRuntimeTool, AntigravityRunTool


async def get_tools(user_id: str, db):
    """Return Antigravity tools if the service is active for the user."""
    from sqlalchemy import select
    from shared.database import ServiceRegistry

    res = await db.execute(
        select(ServiceRegistry).where(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name == "antigravity",
            ServiceRegistry.is_active == True,  # noqa: E712
        )
    )
    if not res.scalars().first():
        return []

    return [AntigravityCheckRuntimeTool(), AntigravityRunTool()]


def get_skill_defs():
    """Return SkillDef list for this integration."""
    from .skills import SKILL_DEFS
    return SKILL_DEFS


__all__ = ["AntigravityCheckRuntimeTool", "AntigravityRunTool", "get_tools", "get_skill_defs"]
