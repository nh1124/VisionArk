from typing import Any, Dict, List, Optional
from nodes.base_node import BaseNode
from nodes.members.planner import PlannerNode
from nodes.members.researcher import ResearcherNode
from nodes.members.advocate import AdvocateNode
from nodes.system.memory_node import MemoryNode
from models.database import get_async_db
from models.message import Message, MessageRole, AttachedFile
from datetime import datetime
from uuid import uuid4

class ProjectNode(BaseNode):
    """
    The Orchestrator (formerly HubAgent).
    Manages the project lifecycle, chat with user, and delegation to members.
    """
    
    def __init__(self, context: Dict[str, Any], status_callback: Optional[Any] = None):
        super().__init__(context, status_callback)
        # Members will be initialized dynamically in pre_process
        self.members = {}
        self.memory = MemoryNode(context)
        self.session_id = None
        self.node_id = None
        
        # New Class-Based Tools
        from tools.library.system import AskNodeTool, DelegateTaskTool
        from tools.library.lbs import ListTasksTool, CreateTaskTool, UpdateTaskTool, CompleteLBSTaskTool
        from tools.library.files import SaveArtifactTool, ReadReferenceTool, ListFilesTool
        from tools.library.knowledge import SearchKnowledgeTool, IngestKnowledgeTool
        from tools.library.search import GoogleSearchTool
        from tools.library.ai import GenerateImageTool
        from tools.library.condition import GetCurrentConditionTool, UpdateUserConditionTool
        from tools.library.members import ListMembersTool, ManageMemberTool
        
        self.tools = [
            AskNodeTool(),
            DelegateTaskTool(),
            ListMembersTool(),
            ManageMemberTool(),

            ListTasksTool(),
            CreateTaskTool(),
            UpdateTaskTool(),
            CompleteLBSTaskTool(),
            SaveArtifactTool(),
            ReadReferenceTool(),
            ListFilesTool(),
            SearchKnowledgeTool(),
            IngestKnowledgeTool(),
            GoogleSearchTool(),
            GenerateImageTool(),
            GetCurrentConditionTool(),
            UpdateUserConditionTool()
        ]

    async def pre_process(self):
        # 1. Ensure Project Node exists & Get Session
        from models.database import get_async_engine, get_async_session_maker
        from sqlalchemy import select
        from models.database import Node, Project
        
        # Use context session if available, else create one
        session = self.context.get('db_session')
        should_close = False
        if not session:
            engine = get_async_engine()
            async_session_cls = get_async_session_maker(engine)
            session = async_session_cls()
            should_close = True
            
        try:
            # Fetch Project
            project_id = self.context.get('project_id')
            result = await session.execute(select(Project).filter(
                Project.user_id == self.user_id,
                Project.id == project_id
            ))
            project = result.scalars().first()
            if project:
                self.project_id = project.id # Use self.project_id instead of self.node_id for clarity
                self.context['project_id'] = self.project_id
            else:
                raise ValueError(f"Project '{project_id}' not found for user {self.user_id}") 
                
            # 2. Get/Create Session
            # Map self.project_id to the Orchestrator Node ID (V6: and PROJECT type)
            result = await session.execute(select(Node).filter(
                Node.project_id == self.project_id,
                Node.node_type == "PROJECT"
            ))
            orchestrator_node = result.scalars().first()
            if orchestrator_node:
                self.node_id = orchestrator_node.id
            else:
                # Fallback if no specific projector node exists yet (should not happen after migration)
                self.node_id = self.project_id

            self.session_id = await self.memory.get_or_create_session(self.project_id, self.user_id)
            self.context['session_id'] = self.session_id
            self.context['node_id'] = self.node_id
            
            # 3. Load Context (Profile, etc.)
            self.context_data = await self.memory.get_context()
            
            # 4. Get API Key
            from models.database import UserSettings
            # Property handles decryption and '********' check
            result = await session.execute(select(UserSettings).filter(UserSettings.user_id == self.user_id))
            settings = result.scalars().first()
            
            if settings and settings.gemini_api_key:
                self.context['api_key'] = settings.gemini_api_key
                # DEBUG LOG
                k = self.context['api_key']
                masked_key = f"{k[:4]}...{k[-4:]}" if k and len(k) > 8 else "INVALID"
                print(f"[ProjectNode] Loaded API Key for user {self.user_id}: {masked_key}", flush=True) # Ensure flush
            else:
                self.context['api_key'] = None
                print(f"[ProjectNode] No API Key found in settings for user {self.user_id}", flush=True)
            
            # 5. Load Members Dynamic
            await self._init_dynamic_members(session)
            
        finally:
            if should_close:
                await session.close()

    async def _init_dynamic_members(self, session):
        """Load member agents from database or fall back to defaults."""
        from nodes.members.dynamic_node import DynamicMemberNode
        from models.database import Node
        from sqlalchemy import select
        
        # Fetch all member nodes for this project
        result = await session.execute(select(Node).where(
            Node.project_id == self.project_id,
            Node.node_type == "MEMBER",
            Node.status == "active"
        ))
        member_nodes = result.scalars().all()
        
        dynamic_members = {}
        for node in member_nodes:
            if node.role_name:
                dynamic_members[node.role_name] = DynamicMemberNode(
                    self.context, 
                    node, 
                    status_callback=self.status_callback
                )
        
        # Hardcoded Fallbacks (Planner, Researcher, Advocate)
        # These will be used if no DB profile overrides them
        from nodes.members.planner import PlannerNode
        from nodes.members.researcher import ResearcherNode
        from nodes.members.advocate import AdvocateNode
        
        fallbacks = {
            "planner": PlannerNode(self.context),
            "researcher": ResearcherNode(self.context),
            "advocate": AdvocateNode(self.context)
        }
        
        for role, node in fallbacks.items():
            if role not in dynamic_members:
                dynamic_members[role] = node
                
        self.members = dynamic_members


    async def process(self, message: str) -> Any:
        print(f"[ProjectNode] Processing: {message}")
        
        # 1. Command/Delegate Check (Simple Routing)
        msg_lower = message.lower()
        if "research" in msg_lower or "check" in msg_lower:
            # Explicit delegation example
            # In V3 Final, ProjectNode can just use tools OR delegate.
            # Let's stick to LLM orchestrator for generality.
            pass

        # 2. Fetch History
        history = await self.memory.get_history(self.session_id)
        
        # 3. Construct current message
        current_msg = Message(
            role=MessageRole.USER,
            content=message,
            timestamp=datetime.now(),
            attached_files=self.context.get('attached_files', [])
        )
        history.append(current_msg)
        
        # 4. Chat with Tools (LLM)
        # Load System Prompt (Project Role)
        system_prompt = await self.load_system_prompt("project")
        
        # Inject Profile from Context (if loaded in pre_process)
        if hasattr(self, "context_data") and self.context_data:
            profile_text = self.context_data.get("profile", "")
            if profile_text:
                system_prompt += f"\n\n## User Profile\n{profile_text}"
                
        # Inject Knowledge Core Context
        knowledge_context = await self.memory.get_knowledge_context(message)
        if knowledge_context:
            system_prompt += f"\n\n## Relevant Knowledge\n{knowledge_context}"
        
        # 4. Check API Key
        if not self.context.get("api_key"):
            return "❌ No API Key found. Please configure your Gemini API Key in Settings > AI Config."

        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context={
                'user_id': self.user_id,
                'session': self.context.get('db_session'),  # For tools that need DB access
                'session_id': self.session_id,
                'node_id': self.node_id,
                'project_id': self.node_id,
                'context_data': self.context_data,  # Pass full context data if needed
                'members': self.members
            }
        )
        
        # Extract content and tool_calls from response
        response_text = llm_response.content or ""
        tool_calls = llm_response.tool_calls if hasattr(llm_response, 'tool_calls') else None
        # 5. Save History (User + Assistant) with tool_calls metadata
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response_text,
            timestamp=datetime.now(),
            meta_info={"tool_calls": tool_calls} if tool_calls else None
        )
        await self.memory.save_messages(self.session_id, [current_msg, assistant_msg])
        
        return response_text

    async def post_process(self, result: Any):
        # 1. Advocate: Check for tasks in the last exchange
        # Fetch last 2 messages (User + AI)
        history = await self.memory.get_history(self.session_id)
        recent = history[-2:] if len(history) >= 2 else history
        
        # Fire & Forget Advocate
        # Advocate will analyze and call Scheduler if needed
        import asyncio
        asyncio.create_task(self.members["advocate"].process_messages(recent))

