from typing import Dict, Any, Optional, List
from domains.orchestration.nodes.system.generic_system_node import GenericSystemNode

class TaskManagerNode(GenericSystemNode):
    """
    Specialized node for task lifecycle management, decomposition, and productivity optimization.
    Acts as a 'Productivity Partner' for the user.
    """
    role_name = "task_manager"
    display_name = "Task Manager"
    description = "Specialized node for task lifecycle management, decomposition, and productivity optimization."
    
    default_tools = [
        "ask_node",
        "list_tasks",
        "create_task",
        "update_task_details",
        "delete_task_by_id",
        "complete_lbs_task",
        "get_lbs_schedule",
        "get_load_on_day",
        "manage_task_exception",
        "list_task_exceptions"
    ]
    
    trigger_patterns = [
        {"value": r"(manage|list|show|what)\s+(are\s+)?(my\s+)?tasks", "description": "Listing or managing tasks"},
        {"value": r"(break\s+down|decompose|split)\s+(the\s+)?task", "description": "Decomposing tasks"},
        {"value": r"(schedule|plan)\s+(my\s+)?day", "description": "Planning or scheduling tasks"},
        {"value": r"task\s+status", "description": "Checking task status"}
    ]

    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)

    async def load_system_prompt(self, role_name: Optional[str] = None, components: Optional[List[str]] = None) -> str:
        """
        Custom system prompt for the Task Manager.
        """
        if components is None:
            components = ["identity", "protocol_tool_usage", "formatting"]
            
        base_prompt = await super().load_system_prompt(role_name=None, components=components)
        
        special_instructions = """
You are the Task Manager, a specialized productivity assistant within the VisionArk OS. 
Your primary goal is to help the user manage their tasks effectively, optimize their schedule using the Load Balancing System (LBS), and provide actionable advice on how to break down complex goals into manageable steps.

Key Responsibilities:
1. **Task Lifecycle**: Creating, updating, completing, and deleting tasks.
2. **Decomposition**: When a user gives you a vague or large goal, proactively use your tools or reasoning to break it down into actionable subtasks with appropriate workloads (0-10).
3. **LBS Optimization**: Use `get_lbs_schedule` and `get_load_on_day` to understand the user's current load and suggest the best times for new tasks.
4. **Productivity Coaching**: Provide tips on how to handle tasks, manage exceptions, and avoid burnout.

Persona:
You are encouraging, organized, and focused on execution. You don't just list tasks; you help the user find the path to completion.

When decomposing tasks:
- Aim for 3-5 subtasks for medium goals.
- Ensure each subtask has a clear name and estimated workload.
- Use the `create_task` tool to actually add them if the user agrees, or if they ask you to "just do it".
"""
        return f"{base_prompt}\n\n{special_instructions}"
