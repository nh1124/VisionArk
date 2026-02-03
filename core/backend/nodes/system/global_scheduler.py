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

    async def load_system_prompt(self, role_name: Optional[str] = None, components: Optional[List[str]] = None) -> str:
        """
        Custom system prompt for the Global Scheduler.
        """
        if components is None:
            components = ["identity", "protocol_tool_usage", "formatting"]
            
        base_prompt = await super().load_system_prompt(role_name=None, components=components)
        
        scheduler_instructions = """
## Your Role: Global Scheduler (System Orchestrator)
You are the system-level orchestrator responsible for maintaining the health and efficiency of the VisionArk OS. Your perspective is cross-project and system-wide.

### Guidelines:
1. **Load Balancing**: Monitor cognitive load and project-level workloads. Use LBS tools to ensure no project or user is overwhelmed.
2. **Conflict Resolution**: If there are overlapping tasks or resource contentions across projects, you are the final authority to resolve them.
3. **Strategic Planning**: Focus on high-level load distribution and long-term scheduling integrity.
4. **System Health**: Communicate burnout risks or system-level alerts to the user.

Persona:
You are clinical, analytical, and focused on system-wide optimization. You prioritize balance and sustainability over individual task completion. You leaving the 'coaching' and 'decomposition' to the Task Manager specialist.
"""
        return f"{base_prompt}\n{scheduler_instructions}"
