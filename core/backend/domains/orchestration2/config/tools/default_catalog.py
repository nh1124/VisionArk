from typing import Any
from ...engine.models.tool import ToolDef

# Import all tools
from ...tools.library.files import (
    WriteFileTool, ReadFileChunkTool, ListFilesTool, DeleteFileTool,
    ApplyTextPatchTool, MoveFileTool, CopyFileTool, MakeDirectoryTool,
    GetFileStatTool, ImportGitHubRepoTool,
)
from ...tools.library.search import (
    GoogleSearchTool, ResearchURLTool, SearchPlacesTool, DeepResearchTool,
    DeepResearchStatusTool, DeepResearchCancelTool,
)
from ...tools.library.ai import (
    GenerateImageTool, MermaidVisualizerTool, ExecuteCodeTool,
)
from ...tools.library.browser import (
    BrowserOpenTool, BrowserClickTool, BrowserFillTool, BrowserScreenshotTool,
)
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
    GetProjectHealthTool, SetTimerTool, ScheduleRecurringPromptTool,
    ScheduleMonitorJobTool, ListMonitorJobsTool, UpdateMonitorJobTool,
    PauseMonitorJobTool, ResumeMonitorJobTool, TestMonitorJobOnceTool,
    ListMonitorJobRunsTool, ListMonitorAlertsTool,
    RaiseContinueTool, WaitTool,
)
from ...tools.library.delegation import ListMembersTool
from ...tools.library.writer import RecursiveWriterTool
from ...tools.library.shell import RunSafeShellTool
from ...tools.library.native import (
    ListNativeDevicesTool, RunNativeJobTool,
    CheckExecutionResultTool, WaitForExecutionTool,
)

from ...tools.library.markdown import (
    ReadMDSectionTool, InitPlanTool, UpdatePlanProgressTool,
    GetCurrentStatusTool, UpdateMDSectionTool,
)
from ...tools.library.document import RenderPdfTool

def get_delegation_tools(engine: Any) -> list[tuple[ToolDef, Any]]:
    """Return delegation-related tool (definition, implementation) pairs."""
    from ...tools.library.delegation import (
        DelegateTaskTool,
        ListDelegationsTool,
        ReceiveDelegationResultsTool,
        WaitForDelegationTool,
    )

    tools = [
        DelegateTaskTool(engine),
        WaitForDelegationTool(engine),
        ReceiveDelegationResultsTool(engine),
        ListDelegationsTool(engine),
    ]
    return [(tool.definition, tool) for tool in tools]


def get_delegation_tool(engine: Any) -> tuple[ToolDef, Any]:
    """Backward-compatible helper returning the primary delegation tool."""
    return get_delegation_tools(engine)[0]


def get_core_tools() -> list[tuple[ToolDef, Any]]:
    """Return all tool (definition, implementation) pairs."""
    tool_classes = [
        # Files
        WriteFileTool, ReadFileChunkTool, ListFilesTool, DeleteFileTool,
        ApplyTextPatchTool, MoveFileTool, CopyFileTool, MakeDirectoryTool,
        GetFileStatTool, ImportGitHubRepoTool,
        # Search
        GoogleSearchTool, ResearchURLTool, SearchPlacesTool, DeepResearchTool,
        DeepResearchStatusTool, DeepResearchCancelTool,
        # AI
        GenerateImageTool, MermaidVisualizerTool, ExecuteCodeTool,
        # Browser
        BrowserOpenTool, BrowserClickTool, BrowserFillTool, BrowserScreenshotTool,
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
        GetProjectHealthTool, SetTimerTool, ScheduleRecurringPromptTool,
        ScheduleMonitorJobTool, ListMonitorJobsTool, UpdateMonitorJobTool,
        PauseMonitorJobTool, ResumeMonitorJobTool, TestMonitorJobOnceTool,
        ListMonitorJobRunsTool, ListMonitorAlertsTool,
        RaiseContinueTool, WaitTool,
        # Members (delegation)
        ListMembersTool,
        # Writer
        RecursiveWriterTool,
        # Shell
        RunSafeShellTool,
        # Native device execution (Run Center integrated)
        ListNativeDevicesTool, RunNativeJobTool,
        CheckExecutionResultTool, WaitForExecutionTool,

        # Markdown
        ReadMDSectionTool, InitPlanTool, UpdatePlanProgressTool,
        GetCurrentStatusTool, UpdateMDSectionTool,

        # Document output
        RenderPdfTool,
    ]

    result = []
    for cls in tool_classes:
        instance = cls()
        result.append((instance.definition, instance))
    return result
