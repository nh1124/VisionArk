from typing import Any, Dict, List, Optional
from nodes.base_node import BaseNode
from models.message import Message
from tools.tool_utils import get_tool_by_name

class DynamicMemberNode(BaseNode):
    """
    A generic member node that configures itself from a DB Node (MEMBER type).
    """
    
    def __init__(self, context: Dict[str, Any], node: Any, status_callback: Optional[Any] = None):
        super().__init__(context, status_callback)
        self.node = node
        self.role_name = node.role_name
        self.display_name = node.display_name or self.role_name.title()
        
        # Load tools from profile
        self.tools = []
        if node.tools:
            for tool_name in node.tools:
                tool = get_tool_by_name(tool_name)
                if tool:
                    self.tools.append(tool)
                else:
                    print(f"[DynamicMemberNode] Warning: Tool '{tool_name}' not found for member '{self.role_name}'")
        
        # Always allow self-description update
        from tools.library.members import UpdateNodeDescriptionTool
        self.tools.append(UpdateNodeDescriptionTool())

    async def load_system_prompt(self, role_name: Optional[str] = None) -> str:
        """
        Prioritize DB prompt, then fallback to asset lookup.
        """
        # If the node has a system prompt, use it as the 'role' part
        db_prompt = self.node.system_prompt
        
        # We still want the global prompt
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

    async def pre_process(self):
        pass

    async def process(self, message: str) -> Any:
        # Load Prompt
        system_prompt = await self.load_system_prompt()
        
        # Construct History (usually delegation is a single-shot or limited history)
        # For dynamic workers, we might want to pass more history, but let's stick to the prompt-based execution.
        history = [Message(role="user", content=message)]
        
        # Call LLM with Tools
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context=self.context
        )
        
        return llm_response.content or ""

    async def post_process(self, result: Any):
        pass
