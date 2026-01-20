from typing import Any
from nodes.base_node import BaseNode
from models.message import Message

class ResearcherNode(BaseNode):
    """
    The Investigator.
    Focus: External knowledge and Search.
    """
    
    def __init__(self, context: Any):
        super().__init__(context)
        from tools.library.search import GoogleSearchTool, ResearchURLTool, SearchPlacesTool
        from tools.library.files import SaveArtifactTool, ReadReferenceTool, ListFilesTool
        from tools.library.knowledge import SearchKnowledgeTool, IngestKnowledgeTool
        
        self.tools = [
            GoogleSearchTool(),
            ResearchURLTool(),
            SearchPlacesTool(),
            SaveArtifactTool(),
            ReadReferenceTool(),
            ListFilesTool(),
            SearchKnowledgeTool(),
            IngestKnowledgeTool()
        ]

    async def pre_process(self):
        pass

    async def process(self, message: str) -> Any:
        # 1. Load Prompt
        system_prompt = await self.load_system_prompt("researcher")
        
        # 2. Call LLM with Tools
        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=[Message(role="user", content=message)],
            tool_context=self.context
        )
        
        return llm_response.content or ""

    async def post_process(self, result: Any):
        pass
