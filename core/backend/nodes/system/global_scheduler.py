from typing import Any, Dict, List, Optional
from nodes.system.generic_system_node import GenericSystemNode

class GlobalScheduler(GenericSystemNode):
    """
    Global Scheduler Node.
    Inherits from GenericSystemNode to load configuration from DB.
    Authorized to perform cross-project load balancing and LBS management.
    """
    # Registration Metadata
    role_name = "GlobalScheduler"
    display_name = "Global Scheduler"
    description = (
        "System-wide Load Balancer. Authorized to manage LBS tasks across all projects, "
        "monitor global cognitive load, and resolve scheduling conflicts."
    )
    default_tools = [
        "get_load_in_period", "broadcast_system_message",
        "list_tasks", "create_task", "update_task_details", 
        "delete_task_by_id", "complete_lbs_task", "get_lbs_schedule",
        "get_load_on_day", "manage_task_exception", "list_task_exceptions"
    ]
    trigger_patterns = [r"SYSTEM_ALERT:.*", r".*burnout.*"]

    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)
        # Note: GenericSystemNode already loads tools from node.tools in DB.
        # We can add hardcoded tools here if they are not in DB.

    # Specific GlobalScheduler logic can be added here if needed, 
    # but GenericSystemNode handles basic LLM processing.
