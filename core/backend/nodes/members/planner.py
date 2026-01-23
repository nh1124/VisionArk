from typing import Any, Dict, Optional
from nodes.members.generic_member_node import GenericMemberNode

class PlannerNode(GenericMemberNode):
    """
    The Strategist.
    Focus: PLAN.md integrity and strategic alignment.
    """
    role_name = "planner"
    display_name = "Planner"
    description = "Project planning, roadmap management, and visualization."
    default_tools = [
        "init_plan",
        "update_plan_progress",
        "get_current_status",
        "update_md_section",
        "generate_mermaid_visualizer",
        "save_artifact",
        "read_reference",
        "list_files",
        "update_node_description"
    ]
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)

    async def on_exit(self, result: Any):
        pass
