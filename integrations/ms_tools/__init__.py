"""MS Office integration for VisionArk.

Provides tools for Word, Excel, PowerPoint, and Microsoft Graph authentication.
PDF rendering has moved to core (render_pdf is a core tool).

Tools are always available for local file operations.
Microsoft Graph API features require AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID.
"""
from .agent_tools import (
    WordTool,
    ExcelTool,
    PptTool,
    MsAuthManagerTool,
)


async def get_tools(user_id: str, db):
    """Return MS Office tools.

    These tools work in offline/local-file mode without any activation check.
    Graph API features are gated by environment credentials at call time.
    Note: render_pdf is a core tool and is not included here.
    """
    return [
        WordTool(),
        ExcelTool(),
        PptTool(),
        MsAuthManagerTool(),
    ]


def get_skill_defs():
    """Return SkillDef list for this integration."""
    from .skills import SKILL_DEFS
    return SKILL_DEFS


__all__ = [
    "WordTool",
    "ExcelTool",
    "PptTool",
    "MsAuthManagerTool",
    "get_tools",
    "get_skill_defs",
]
