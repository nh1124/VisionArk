from typing import Any
from nodes.base_node import BaseNode

from tools import PLANNER_TOOL_DEFINITIONS, TOOL_FUNCTIONS
from models.message import Message

class PlannerNode(BaseNode):
    """
    The Strategist.
    Focus: PLAN.md integrity and strategic alignment.
    """
    
    async def pre_process(self):
        pass

    async def process(self, message: str) -> Any:
        # 1. Load Prompt
        system_prompt = self.load_system_prompt("planner")
        
        # 2. Call LLM with Tools
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=[Message(role="user", content=message)], 
            tool_definitions=PLANNER_TOOL_DEFINITIONS, 
            tool_functions=TOOL_FUNCTIONS
        )
        
        return llm_response.content or ""

    async def post_process(self, result: Any):
        pass
