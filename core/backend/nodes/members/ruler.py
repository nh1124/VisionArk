from typing import Any
from nodes.base_node import BaseNode
from models.message import Message

class RulerNode(BaseNode):
    """
    The Organizer.
    Focus: File organization and Indexing.
    """
    
    def __init__(self, context: Any):
        super().__init__(context)
        from tools.library.lbs import ListTasksTool, CreateTaskTool, UpdateTaskTool, CompleteLBSTaskTool, GetLBSScheduleTool, GetLoadOnDayTool
        from tools.library.files import SaveArtifactTool, ReadReferenceTool, ListFilesTool
        
        self.tools = [
            ListTasksTool(),
            CreateTaskTool(),
            UpdateTaskTool(),
            CompleteLBSTaskTool(),
            GetLBSScheduleTool(),
            GetLoadOnDayTool(),
            SaveArtifactTool(),
            ReadReferenceTool(),
            ListFilesTool()
        ]

    async def on_enter(self):
        pass

    async def on_execute(self, message: str) -> Any:
        # 1. Load Prompt
        system_prompt = await self.load_system_prompt("ruler")
        
        # 2. Call LLM with Tools
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=[Message(role="user", content=message)],
            tool_context=self.context
        )
        
        return llm_response.content or ""

    async def on_exit(self, result: Any):
        pass
