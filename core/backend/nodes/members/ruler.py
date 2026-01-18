from typing import Any
from nodes.base_node import BaseNode
from tools import RULER_TOOL_DEFINITIONS, TOOL_FUNCTIONS
from models.message import Message

class RulerNode(BaseNode):
    """
    The Organizer.
    Focus: File organization and Indexing.
    """
    
    async def pre_process(self):
        pass

    async def process(self, message: str) -> Any:
        # 1. Load Prompt
        system_prompt = self.load_system_prompt("ruler")
        
        # 2. Call LLM with Tools
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=[Message(role="user", content=message)],
            tool_definitions=RULER_TOOL_DEFINITIONS,
            tool_functions=TOOL_FUNCTIONS
        )
        
        return llm_response.content or ""

    async def post_process(self, result: Any):
        pass
