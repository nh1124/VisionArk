"""Codex CLI integration for VisionArk.

Provides agent tools for running coding tasks via the OpenAI Codex CLI
on connected native devices.

Activation: register service_name='codex' in ServiceRegistry (is_active=True).
"""

from . import _handler  # noqa: F401  — registers @lrj_registry.register("cli.run_shell")
from .agent_tools import (
    CodexCheckRuntimeTool,
    CodexRunTool,
    CodexJobWaitTool,
    CodexJobStatusTool,
    CodexJobOutputTool,
    CodexApprovalTool,
    CodexJobCancelTool,
)


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

    return [
        CodexCheckRuntimeTool(),
        CodexRunTool(),
        CodexJobWaitTool(),
        CodexJobStatusTool(),
        CodexJobOutputTool(),
        CodexApprovalTool(),
        CodexJobCancelTool(),
    ]


def get_skill_defs():
    """Return SkillDef list for this integration."""
    from .skills import SKILL_DEFS
    return SKILL_DEFS


__all__ = [
    "CodexCheckRuntimeTool",
    "CodexRunTool",
    "CodexJobWaitTool",
    "CodexJobStatusTool",
    "CodexJobOutputTool",
    "CodexApprovalTool",
    "CodexJobCancelTool",
    "get_tools",
    "get_skill_defs",
]
