"""Codex CLI integration for VisionArk.

Provides agent tools for running coding tasks via the OpenAI Codex CLI
on connected native devices.

Activation: register service_name='codex' in ServiceRegistry (is_active=True).
"""

from .agent_tools import CodexCheckRuntimeTool, CodexRunTool


async def get_tools(user_id: str, db):
    """Return Codex tools if the service is active for the user."""
    from sqlalchemy import select
    from shared.database import ServiceRegistry

    res = await db.execute(
        select(ServiceRegistry).where(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name == "codex",
            ServiceRegistry.is_active == True,  # noqa: E712
        )
    )
    if not res.scalars().first():
        return []

    return [CodexCheckRuntimeTool(), CodexRunTool()]


def get_skill_defs():
    """Return SkillDef list for this integration."""
    from .skills import SKILL_DEFS
    return SKILL_DEFS


__all__ = ["CodexCheckRuntimeTool", "CodexRunTool", "get_tools", "get_skill_defs"]
