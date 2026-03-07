"""Claude CLI integration for VisionArk.

Provides agent tools for running the Anthropic Claude CLI
on connected native devices.

Activation: register service_name='claude' in ServiceRegistry (is_active=True).
"""

from .agent_tools import ClaudeCheckRuntimeTool, ClaudeRunTool


async def get_tools(user_id: str, db):
    """Return Claude CLI tools if the service is active for the user."""
    from sqlalchemy import select
    from shared.database import ServiceRegistry

    res = await db.execute(
        select(ServiceRegistry).where(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name == "claude",
            ServiceRegistry.is_active == True,  # noqa: E712
        )
    )
    if not res.scalars().first():
        return []

    return [ClaudeCheckRuntimeTool(), ClaudeRunTool()]


def get_skill_defs():
    """Return SkillDef list for this integration."""
    from .skills import SKILL_DEFS
    return SKILL_DEFS


__all__ = ["ClaudeCheckRuntimeTool", "ClaudeRunTool", "get_tools", "get_skill_defs"]
