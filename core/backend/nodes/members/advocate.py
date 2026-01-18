from typing import Any, List
from nodes.base_node import BaseNode
from nodes.system.scheduler_node import SchedulerNode
from models.message import Message
from tools import ADVOCATE_TOOL_DEFINITIONS, TOOL_FUNCTIONS

class AdvocateNode(BaseNode):
    """
    The Taskmaster.
    Focus: Task extraction and LBS Proposal.
    """
    
    def __init__(self, context):
        super().__init__(context)
        # We need a reference to Scheduler to propose tasks
        self.scheduler = SchedulerNode(context)

    async def pre_process(self):
        pass

    async def process(self, message: str) -> Any:
        # Fallback for direct calls
        print(f"[Advocate] Extracting tasks from: {message}")
        return "Advocate: No new tasks detected."
        
    async def process_messages(self, messages: List[Message]):
        """
        Analyze recent chat history for actionable tasks.
        """
        if not messages:
            return
            
        print("[Advocate] Analyzing recent messages for tasks...")
        
        # 1. Load Prompt (Advocate Role contains JSON schema)
        system_prompt = self.load_system_prompt("advocate")
        
        # 2. Call LLM (using BaseNode's capability)
        # We need to format the messages for the LLM
        # We can reuse chat_with_tools but we want strict JSON and no tools.
        # So we use self.llm.complete_async direct if possible, or chat_with_tools with system prompt.
        # Let's use chat_with_tools as it handles history formatting, 
        # but we need to ensure we get JSON.
        
        # We'll use a temporary "system" prompt override strictly for this call.
        extraction_prompt = system_prompt
        
        # We need to initialize LLM if not present (BaseNode check)
        llm_response = await self.chat_with_tools(
            system_prompt=extraction_prompt, 
            message_history=messages[-5:], # Analyze last 5 messages context
            tool_definitions=ADVOCATE_TOOL_DEFINITIONS, 
            api_key=None, # Use default
            tool_context=self.context,
            tool_functions=TOOL_FUNCTIONS
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
