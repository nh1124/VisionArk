from typing import Any, Dict, List, Optional
from nodes.system.generic_system_node import GenericSystemNode

class RouterNode(GenericSystemNode):
    """
    Intelligent System Router.
    Analyzes user intent and multicasts messages to relevant nodes.
    """
    role_name = "Router"
    display_name = "System AI Router"
    description = "Analyzes message patterns and multicasts tasks to specialized nodes using LLM analysis."
    default_tools = ["ask_node", "list_nodes"]

    async def on_execute(self, message: str) -> Any:
        """
        1. Load Router specific prompt.
        2. Analyze message intent.
        3. Decide on routing targets.
        4. Multicast using ask_node(blocking=False).
        """
        system_prompt = await self.load_system_prompt()
        
        # We use chat_with_tools to allow the LLM to 'decide' which nodes to notify
        # by calling ask_node tool.
        
        history = [
            {"role": "user", "content": f"Analyze and route the following message: '{message}'"}
        ]
        
        print(f"[RouterNode] Analyzing routing for: {message[:50]}...")
        
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context=self.context
        )
        
        return llm_response.content or "Routing analysis complete."
