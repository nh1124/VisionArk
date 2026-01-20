from typing import Any
from nodes.base_node import BaseNode

from models.message import Message

class PlannerNode(BaseNode):
    """
    The Strategist.
    Focus: PLAN.md integrity and strategic alignment.
    """
    
    def __init__(self, context: Any):
        super().__init__(context)
        from tools.library.markdown import InitPlanTool, UpdatePlanProgressTool, GetCurrentStatusTool
        from tools.library.ai import MermaidVisualizerTool
        from tools.library.files import SaveArtifactTool, ReadReferenceTool, ListFilesTool
        
        self.tools = [
            InitPlanTool(),
            UpdatePlanProgressTool(),
            GetCurrentStatusTool(),
            MermaidVisualizerTool(),
            SaveArtifactTool(),
            ReadReferenceTool(),
            ListFilesTool()
        ]

    async def pre_process(self):
        pass

    async def process(self, message: str) -> Any:
        # 1. Load Prompt
        system_prompt = await self.load_system_prompt("planner")
        
        # 2. Call LLM with Tools
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=[Message(role="user", content=message)],
            tool_context=self.context
        )
        
        return llm_response.content or ""

    async def post_process(self, result: Any):
        pass
