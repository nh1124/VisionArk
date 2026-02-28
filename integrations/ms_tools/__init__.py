"""MS Office integration for VisionArk.

Provides tools for Word, Excel, PowerPoint, PDF rendering,
and Microsoft Graph authentication.

Tools are always available for local file operations.
Microsoft Graph API features require AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID.
"""
from .agent_tools import (
    RenderPdfTool,
    WordTool,
    ExcelTool,
    PptTool,
    MsAuthManagerTool,
)


async def get_tools(user_id: str, db):
    """Return all MS Office tools.

    These tools work in offline/local-file mode without any activation check.
    Graph API features are gated by environment credentials at call time.
    """
    return [
        RenderPdfTool(),
        WordTool(),
        ExcelTool(),
        PptTool(),
        MsAuthManagerTool(),
    ]


def get_skill_defs():
    """Return SkillDef list for this integration.

    Called by tool_reflection when it is extended to support per-integration
    skill registration. Until then, this is a no-op declaration.
    """
    from .skills import SKILL_DEFS
    return SKILL_DEFS


__all__ = [
    "RenderPdfTool",
    "WordTool",
    "ExcelTool",
    "PptTool",
    "MsAuthManagerTool",
    "get_tools",
    "get_skill_defs",
]
