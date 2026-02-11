from typing import Any, Dict, List, Optional
from domains.orchestration.nodes.system.generic_system_node import GenericSystemNode

class ProjectManagerNode(GenericSystemNode):
    """
    System-level node for multi-project management and health monitoring.
    """
    role_name = "project_manager"
    display_name = "Project Manager"
    description = "Specialized node for managing project lifecycles, monitoring health, and system-wide orchestration."
    default_tools = [
        "ask_node", 
        "list_user_projects", 
        "update_project", 
        "get_project_health",
        "broadcast_system_message"
    ]
    trigger_patterns = [
        {"value": r"(manage|list|show)\s+(my\s+)?projects", "description": "Listing or managing projects"},
        {"value": r"project\s+health", "description": "Checking project health"},
        {"value": r"update\s+project\s+\w+", "description": "Updating project metadata"}
    ]

    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)
        # Tools are already loaded by GenericSystemNode from self.node.tools or self.default_tools

    async def load_system_prompt(self, role_name: Optional[str] = None, components: Optional[List[str]] = None) -> str:
        """
        Custom system prompt for the Project Manager.
        """
        if components is None:
            components = ["identity", "protocol_tool_usage", "formatting"]
            
        base_prompt = await super().load_system_prompt(role_name=None, components=components)
        
        manager_instructions = """
## Your Role: Project Manager
You are the central authority for project management within VisionArk. Your goal is to help the user maintain a healthy and organized workspace.

### Guidelines:
1. **Lifecycle Management**: Use 'list_user_projects' to understand the user's landscape. Use 'update_project' to change status or priority.
2. **Health Monitoring**: Use 'get_project_health' to diagnose issues in specific projects.
3. **Proactive Advice**: If you notice a project has no specialist nodes or is inactive, suggest improvements.
4. **Cross-Project Context**: You have system-level access. You can see all projects and their relationships.
5. **System Interaction**: You can broadcast messages to all projects if there are system-wide updates.

When asked about projects, provide clear, structured summaries and actionable insights.
"""
        return f"{base_prompt}\n{manager_instructions}"
