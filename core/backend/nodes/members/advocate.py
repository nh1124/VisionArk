from typing import Any, List, Dict, Optional
from nodes.members.generic_member_node import GenericMemberNode

class AdvocateNode(GenericMemberNode):
    """
    The Taskmaster.
    Focus: Task extraction and LBS Proposal.
    """
    role_name = "advocate"
    display_name = "Advocate"
    description = "Task extraction, prioritization, and scheduling advocacy."
    default_tools = [
        "get_current_condition",
        "update_user_condition",
        "save_artifact",
        "read_reference",
        "list_files",
        "search_knowledge",
        "ingest_knowledge",
        "update_node_description"
    ]
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, node, status_callback)
        # We need a reference to Scheduler to propose tasks
        from nodes.system.scheduler_node import SchedulerNode
        self.scheduler = SchedulerNode(context)

    async def process_messages(self, messages: List[Any]):
        """
        Analyze recent chat history for actionable tasks.
        """
        if not messages:
            return
            
        print("[Advocate] Analyzing recent messages for tasks...")
        
        # 1. Load Prompt (Advocate Role contains JSON schema)
        system_prompt = await self.load_system_prompt("advocate")
        
        # 2. Call LLM (using BaseNode's capability)
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt, 
            message_history=messages[-5:], # Analyze last 5 messages context
            tool_context=self.context
        )
        
        # 3. Parse JSON
        import json
        import re
        
        try:
            # Get content from response
            response_text = llm_response.content or ""
            
            # Clean md blocks
            text = response_text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            data = json.loads(text)
            tasks = data.get("tasks", [])
            
            if not tasks:
                print("[Advocate] No tasks found.")
                return

            print(f"[Advocate] Found {len(tasks)} tasks: {tasks}")
            
            # 4. Delegate to Scheduler
            for task in tasks:
                 # Clean up keys for Scheduler
                 draft_task = {
                     "title": task.get("title"),
                     "load": task.get("estimated_duration", 0.5), # Map duration to load score approx
                     "due_date": task.get("due_date_hint"),
                     "priority": task.get("priority")
                 }
                 result = await self.scheduler.propose_task(draft_task)
                 print(f"[Advocate] Scheduler result for '{task.get('title')}': {result}")
                 
        except json.JSONDecodeError:
            print(f"[Advocate] Failed to parse JSON from LLM: {response_text}")
        except Exception as e:
            print(f"[Advocate] Error processing tasks: {e}")
