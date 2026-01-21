from typing import Any
from nodes.base_node import BaseNode

from models.message import Message, MessageRole

class PlannerNode(BaseNode):
    """
    The Strategist.
    Focus: PLAN.md integrity and strategic alignment.
    """
    
    def __init__(self, context: Any):
        super().__init__(context)
        from tools.library.markdown import InitPlanTool, UpdatePlanProgressTool, GetCurrentStatusTool, UpdateMDSectionTool
        from tools.library.ai import MermaidVisualizerTool
        from tools.library.files import SaveArtifactTool, ReadReferenceTool, ListFilesTool
        from tools.library.members import UpdateNodeDescriptionTool
        
        self.tools = [
            InitPlanTool(),
            UpdatePlanProgressTool(),
            GetCurrentStatusTool(),
            UpdateMDSectionTool(),
            MermaidVisualizerTool(),
            SaveArtifactTool(),
            ReadReferenceTool(),
            ListFilesTool(),
            UpdateNodeDescriptionTool()
        ]

    async def on_enter(self):
        pass

    async def on_execute(self, message: str) -> Any:
        # 1. Load Prompt
        system_prompt = await self.load_system_prompt("planner")
        
        # 2. Call LLM with Tools
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=[Message(role=MessageRole.USER, content=message)],
            tool_context=self.context
        )
        
        return llm_response.content or ""

    async def on_exit(self, result: Any):
        pass
