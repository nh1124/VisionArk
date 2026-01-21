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
            for tool_name in node.tools:
                tool = get_tool_by_name(tool_name)
                if tool:
                    self.tools.append(tool)
                else:
                    print(f"[GenericMemberNode] Warning: Tool '{tool_name}' not found for member node '{self.role_name}'")

    async def load_system_prompt(self, role_name: Optional[str] = None) -> str:
        """
        Prioritize DB prompt, then fallback to asset lookup.
        """
        db_prompt = self.node.system_prompt
        
        from utils.paths import get_prompts_dir
        prompts_dir = get_prompts_dir()
        global_path = prompts_dir / "system" / "global.md"
        global_text = ""
        try:
            if global_path.exists():
                global_text = global_path.read_text(encoding='utf-8')
        except: pass
        
        if db_prompt:
            return f"{global_text}\n\n## Your Role: {self.display_name}\n{db_prompt}"
        
        return await super().load_system_prompt(role_name or self.role_name)

    async def on_execute(self, message: str) -> Any:
        system_prompt = await self.load_system_prompt()
        
        history = [Message(role=MessageRole.USER, content=message)]
        
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context=self.context
        )
        
        return llm_response.content or ""
