from typing import Any, Dict, List, Optional
from nodes.system.system_node import SystemNode
from models.message import Message, MessageRole
from tools.tool_utils import get_tool_by_name

class GenericSystemNode(SystemNode):
    """
    A generic system node that configures itself from a DB Node (SYSTEM type).
    Provides privileged cross-project access.
    """
    # Registration Metadata
    role_name = "GenericSystem"
    display_name = "Generic System Node"
    description = "A base class for system-level specialist nodes."
    default_tools = ["ask_node"]
    trigger_patterns = [] # List of regex strings
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, status_callback)
        self.node = node
        self.role_name = node.role_name
        self.display_name = node.display_name or self.role_name.title()
        
        # 1. Load tools from profile
        self.tools = []
        registered_names = set()

        if node.tools:
            for tool_name in node.tools:
                tool = get_tool_by_name(tool_name)
                if tool:
                    self.tools.append(tool)
                    registered_names.add(tool.name)
                else:
                    print(f"[GenericSystemNode] Warning: Tool '{tool_name}' not found for system node '{self.role_name}'")
        
        # 2. Add core 'ask_node' tool if not already present
        if "ask_node" not in registered_names:
            from tools.library.system import AskNodeTool
            self.tools.append(AskNodeTool())

    async def load_system_prompt(self, role_name: Optional[str] = None, components: Optional[List[str]] = None) -> str:
        """
        Prioritize DB prompt, then fallback to asset lookup.
        """
        if components is None:
            # Default for system nodes: less philosophy, more tool logic
            components = ["identity", "protocol_tool_usage", "formatting"]
            
        db_prompt = self.node.system_prompt
        
        if db_prompt:
            base_prompt = await super().load_system_prompt(role_name=None, components=components)
            return f"{base_prompt}\n\n## Your Role: {self.display_name}\n{db_prompt}"
        
        return await super().load_system_prompt(role_name or self.role_name, components=components)

    async def on_execute(self, message: str) -> Any:
        system_prompt = await self.load_system_prompt()
        
        # System requests are usually single-shot from other nodes
        history = [Message(role=MessageRole.USER, content=message)]
        
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context=self.context
        )
        
        # Return full Message to preserve sub_messages for frontend tool history display
        return llm_response
