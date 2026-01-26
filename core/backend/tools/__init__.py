# New Class-Based Tool Architecture
from .base import BaseTool
from .library.system import AskNodeTool, ListNodesTool, GetNodeProfileTool, BroadcastSystemMessageTool
from integrations.lbs.agent_tools import (
    ListTasksTool, CreateTaskTool, UpdateTaskTool, DeleteTaskTool, 
    CompleteLBSTaskTool, GetLBSScheduleTool, GetLoadOnDayTool, 
    GetLoadInPeriodTool, ManageTaskExceptionTool, ListExceptionsTool
)
from .library.files import SaveArtifactTool, ReadReferenceTool, ListFilesTool, DeleteArtifactTool, ImportGitHubRepoTool
from integrations.knowledge_core.agent_tools import SearchKnowledgeTool, IngestKnowledgeTool

async def get_integration_tools(user_id: str, db) -> list:
    """Helper to fetch all active integration tools for a user (dynamic discovery)."""
    import pkgutil
    import importlib
    from pathlib import Path
    
    tools = []
    # Path to integrations directory (core/backend/integrations)
    integrations_path = Path(__file__).parent.parent / "integrations"
    
    # Iterate over all packages in integrations/
    for module_info in pkgutil.iter_modules([str(integrations_path)]):
        if module_info.ispkg:
            try:
                # Import module dynamically (e.g. integrations.line)
                module = importlib.import_module(f"integrations.{module_info.name}")
                
                # Check for get_tools function
                if hasattr(module, "get_tools"):
                    # Call get_tools(user_id, db)
                    module_tools = await module.get_tools(user_id, db)
                    if module_tools:
                        tools.extend(module_tools)
            except ImportError as e:
                print(f"⚠️ Failed to import integration {module_info.name}: {e}")
            except Exception as e:
                print(f"❌ Error loading tools for {module_info.name}: {e}")
                
    return tools
from .library.search import GoogleSearchTool, ResearchURLTool, SearchPlacesTool, DeepResearchTool
from .library.markdown import InitPlanTool, UpdatePlanProgressTool, GetCurrentStatusTool, ReadMDSectionTool, UpdateMDSectionTool
from .library.ai import GenerateImageTool, MermaidVisualizerTool, ExecuteCodeTool
from .library.condition import GetCurrentConditionTool, UpdateUserConditionTool
from .library.members import ListMembersTool, ManageMemberTool, UpdateNodeDescriptionTool
from .library.writer import RecursiveWriterTool
from .library.routing import MulticastMessageTool, SubscribeIntentTool
from .library.shell import RunSafeShellTool

__all__ = [
    "BaseTool",
    "AskNodeTool",
    "ListNodesTool",
    "GetNodeProfileTool",
    "BroadcastSystemMessageTool",
    "ListTasksTool",
    "CreateTaskTool",
    "UpdateTaskTool",
    "DeleteTaskTool",
    "CompleteLBSTaskTool",
    "GetLBSScheduleTool",
    "GetLoadOnDayTool",
    "GetLoadInPeriodTool",
    "SaveArtifactTool",
    "ReadReferenceTool",
    "ListFilesTool",
    "DeleteArtifactTool",
    "ImportGitHubRepoTool",
    "SearchKnowledgeTool",
    "IngestKnowledgeTool",
    "GoogleSearchTool",
    "ResearchURLTool",
    "SearchPlacesTool",
    "InitPlanTool",
    "UpdatePlanProgressTool",
    "GetCurrentStatusTool",
    "ReadMDSectionTool",
    "GenerateImageTool",
    "MermaidVisualizerTool",
    "ExecuteCodeTool",
    "GetCurrentConditionTool",
    "UpdateUserConditionTool",
    "ListMembersTool",
    "ManageMemberTool",
    "UpdateNodeDescriptionTool",
    "DeepResearchTool",
    "RecursiveWriterTool",
    "ManageTaskExceptionTool",
    "ListExceptionsTool",
    "MulticastMessageTool",
    "SubscribeIntentTool",
    "RunSafeShellTool",
    "UpdateMDSectionTool",
    "SendLineMessageTool"
]
