from typing import Any, Dict, Optional
from nodes.members.generic_member_node import GenericMemberNode

class RulerNode(GenericMemberNode):
    """
    The Organizer.
    Focus: File organization and Indexing.
    """
    role_name = "ruler"
    display_name = "Ruler"
    description = "Task management, scheduling, and file orchestration."
    default_tools = [
        "list_tasks",
        "create_task",
        "update_task",
        "complete_lbs_task",
        "get_lbs_schedule",
        "get_load_on_day",
        "save_artifact",
        "read_reference",
        "list_files"
    ]
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)

    async def on_exit(self, result: Any):
        pass
