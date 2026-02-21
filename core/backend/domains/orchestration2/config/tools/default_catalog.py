from typing import Any
from ...engine.models.tool import ToolDef

# Import all tools
from ...tools.library.files import (
    SaveArtifactTool, ReadReferenceTool, ListFilesTool,
    DeleteArtifactTool, ImportGitHubRepoTool,
)
from ...tools.library.search import (
    GoogleSearchTool, ResearchURLTool, SearchPlacesTool, DeepResearchTool,
)
from ...tools.library.ai import (
    GenerateImageTool, MermaidVisualizerTool, ExecuteCodeTool,
)
from ...tools.library.browser import (
    BrowserOpenTool, BrowserClickTool, BrowserFillTool, BrowserScreenshotTool,
)
from ...tools.library.canvas import UpdateCanvasTool
from ...tools.library.governance import GetProjectRulesTool, UpdateProjectRulesTool
from ...tools.library.notes import ListNotesTool, ReadNoteTool, CreateNoteTool
from ...tools.library.workspace import (
    ListWorkspaceItemsTool, ReadWorkspaceItemTool,
    CreateWorkspaceItemTool, UpdateWorkspaceItemTool, DeleteWorkspaceItemTool,
    CreateWorkspaceDirectoryTool, ReadWorkspaceFileTool, MoveWorkspaceItemTool,
)
from ...tools.library.system import (
    ListAgentsTool, GetAgentProfileTool,
    ListUserProjectsTool, UpdateProjectTool,
    GetProjectHealthTool, SetTimerTool, RaiseContinueTool,
)
from ...tools.library.members import (
    ListMembersTool, ManageMemberTool, UpdateAgentDescriptionTool,
)
from ...tools.library.writer import RecursiveWriterTool
from ...tools.library.shell import RunSafeShellTool

from ...tools.library.markdown import (
    ReadMDSectionTool, InitPlanTool, UpdatePlanProgressTool,
    GetCurrentStatusTool, UpdateMDSectionTool,
)

def get_core_tools() -> list[tuple[ToolDef, Any]]:
    """Return all tool (definition, implementation) pairs."""
    tool_classes = [
        # Files
        SaveArtifactTool, ReadReferenceTool, ListFilesTool,
        DeleteArtifactTool, ImportGitHubRepoTool,
        # Search
        GoogleSearchTool, ResearchURLTool, SearchPlacesTool, DeepResearchTool,
        # AI
        GenerateImageTool, MermaidVisualizerTool, ExecuteCodeTool,
        # Browser
        BrowserOpenTool, BrowserClickTool, BrowserFillTool, BrowserScreenshotTool,
        # Canvas
        UpdateCanvasTool,
        # Governance
        GetProjectRulesTool, UpdateProjectRulesTool,
        # Notes
        ListNotesTool, ReadNoteTool, CreateNoteTool,
        # Workspace
        ListWorkspaceItemsTool, ReadWorkspaceItemTool,
        CreateWorkspaceItemTool, UpdateWorkspaceItemTool, DeleteWorkspaceItemTool,
        CreateWorkspaceDirectoryTool, ReadWorkspaceFileTool, MoveWorkspaceItemTool,
        # System
        ListAgentsTool, GetAgentProfileTool,
        ListUserProjectsTool, UpdateProjectTool,
        GetProjectHealthTool, SetTimerTool, RaiseContinueTool,
        # Members
        ListMembersTool, ManageMemberTool, UpdateAgentDescriptionTool,
        # Writer
        RecursiveWriterTool,
        # Shell
        RunSafeShellTool,

        # Markdown
        ReadMDSectionTool, InitPlanTool, UpdatePlanProgressTool,
        GetCurrentStatusTool, UpdateMDSectionTool,
    ]

    result = []
    for cls in tool_classes:
        instance = cls()
        result.append((instance.definition, instance))
    return result
