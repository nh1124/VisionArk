from typing import Any, Dict, List, Optional
from nodes.base_node import BaseNode
from models.message import Message, MessageRole

class GenericMemberNode(BaseNode):
    """
    A generic member node that configures itself from a DB Node (MEMBER type).
    Scoped to a specific project_id.
    """
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, status_callback)
        self.node = node
        self.role_name = node.role_name
        self.display_name = node.display_name or self.role_name.title()
        
        # Load tools from profile
        from tools.tool_utils import get_tool_by_name
        self.tools = []
        if node.tools:
            import json
            tools_list = node.tools
            if isinstance(tools_list, str):
                try:
                    tools_list = json.loads(tools_list)
                except Exception as e:
                    print(f"[GenericMemberNode] Error parsing tools for {self.role_name}: {e}")
                    tools_list = []
            
            for tool_name in tools_list:
                tool = get_tool_by_name(tool_name)
                if tool:
                    self.tools.append(tool)
                else:
                    print(f"[GenericMemberNode] Warning: Tool '{tool_name}' not found for member node '{self.role_name}'")
        
        # Always allow agents to register routing hooks
        from tools import SubscribeIntentTool
        self.tools.append(SubscribeIntentTool())

    async def load_system_prompt(self, role_name: Optional[str] = None, components: Optional[List[str]] = None) -> str:
        """
        Prioritize DB prompt, then fallback to asset lookup.
        Uses modular components for consistency.
        """
        if components is None:
            # Default components for Member Nodes
            components = ["identity", "protocol_grounding", "protocol_tool_usage", "formatting"]
            
        db_prompt = self.node.system_prompt
        
        if db_prompt:
            # Still load components even if DB prompt exists to ensure protocols are enforced
            base_prompt = await super().load_system_prompt(role_name=None, components=components)
            # Remove the "Available Tools" section from super if we want to customize, 
            # but super() handles it well. We just append the specific role prompt.
            return f"{base_prompt}\n\n## Your Specific Role: {self.display_name}\n{db_prompt}"
        
        return await super().load_system_prompt(role_name or self.role_name, components=components)

    async def on_execute(self, message: str) -> Any:
        system_prompt = await self.load_system_prompt()
        
        history = [Message(role=MessageRole.USER, content=message)]
        
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context=self.context
        )
        
        return llm_response.content or ""
