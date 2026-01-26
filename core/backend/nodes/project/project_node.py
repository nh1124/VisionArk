from typing import Any, Dict, List, Optional
from nodes.base_node import BaseNode
from nodes.system.memory_node import MemoryNode
from models.database import get_async_db
from models.message import Message, MessageRole, AttachedFile
from datetime import datetime
from uuid import uuid4

class ProjectNode(BaseNode):
    """
    The Orchestrator.
    Manages the project lifecycle, chat with user, and delegation to members.
    """
    
    def __init__(self, context: Dict[str, Any], status_callback: Optional[Any] = None):
        super().__init__(context, status_callback)
        self.memory = MemoryNode(context)
        self.session_id = None
        self.node_id = None
        
        # New Class-Based Tools
        from tools.library.system import AskNodeTool, ListNodesTool, GetNodeProfileTool
        from tools.library.lbs import (
            ListTasksTool, CompleteLBSTaskTool, DeleteTaskTool,
            GetLBSScheduleTool, GetLoadOnDayTool, GetLoadInPeriodTool,
            GetTaskHistoryTool, ManageTaskExceptionTool, ListExceptionsTool
        )
        from tools.library.files import SaveArtifactTool, ReadReferenceTool, ListFilesTool, DeleteArtifactTool, ImportGitHubRepoTool
        from tools.library.knowledge import SearchKnowledgeTool, IngestKnowledgeTool
        from tools.library.search import GoogleSearchTool, DeepResearchTool
        from tools.library.ai import GenerateImageTool
        from tools.library.condition import GetCurrentConditionTool, UpdateUserConditionTool
        from tools.library.markdown import UpdateMDSectionTool
        from tools.library.members import ListMembersTool, ManageMemberTool, UpdateNodeDescriptionTool
        from tools.library.writer import RecursiveWriterTool
        from tools.library.shell import RunSafeShellTool
        from tools.library.routing import SubscribeIntentTool
        from tools.library.canvas import UpdateCanvasTool
        
        self.tools = [
            AskNodeTool(),
            ListNodesTool(),
            GetNodeProfileTool(),
            ListMembersTool(),
            ManageMemberTool(),
            UpdateNodeDescriptionTool(),
            SubscribeIntentTool(),
            RecursiveWriterTool(),

            ListTasksTool(),
            CompleteLBSTaskTool(),
            DeleteTaskTool(),
            GetLBSScheduleTool(),
            GetLoadOnDayTool(),
            GetLoadInPeriodTool(),
            GetTaskHistoryTool(),
            ManageTaskExceptionTool(),
            ListExceptionsTool(),

            SaveArtifactTool(),
            DeleteArtifactTool(),
            ReadReferenceTool(),
            ListFilesTool(),
            ImportGitHubRepoTool(),
            RunSafeShellTool(),
            SearchKnowledgeTool(),
            IngestKnowledgeTool(),
            GoogleSearchTool(),
            DeepResearchTool(),
            GenerateImageTool(),
            GetCurrentConditionTool(),
            UpdateUserConditionTool(),
            UpdateMDSectionTool(),
            UpdateCanvasTool()
        ]

    async def on_enter(self):
        # 1. Base initialization (Session, API Key, Model)
        await super().on_enter()
        session = self.context.get('db_session')
        
        try:
            # 2. Fetch Project
            from sqlalchemy import select
            from models.database import Node, Project
            
            project_id = self.context.get('project_id')
            if project_id:
                result = await session.execute(select(Project).filter(
                    Project.user_id == self.user_id,
                    Project.id == project_id
                ))
                project = result.scalars().first()
            else:
                raise ValueError(f"No project found for user {self.user_id} and project_id {project_id}")

            if project:
                self.project_id = project.id 
                self.context['project_id'] = self.project_id
            else:
                raise ValueError(f"No active project found for user {self.user_id}") 
            print(f"[ProjectNode] Project ID: {self.project_id}")

            # 3. Get Orchestrator Node ID (V6: and PROJECT type)
            result = await session.execute(select(Node).filter(
                Node.project_id == self.project_id,
                Node.node_type == "PROJECT"
            ))
            orchestrator_node = result.scalars().first()
            if orchestrator_node:
                self.node_id = orchestrator_node.id
            else:
                self.node_id = self.project_id

            self.session_id = await self.memory.get_or_create_session(self.project_id, self.user_id)
            self.context['session_id'] = self.session_id
            self.context['node_id'] = self.node_id
            
            # 4. Load Context (Profile, etc.)
            self.context_data = await self.memory.get_context()
            
        except Exception as e:
            print(f"[ProjectNode] Error in on_enter: {e}")
            raise


    async def on_execute(self, message: str) -> Any:
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
        system_prompt = await self.load_system_prompt(
            role_name="project",
            components=["identity", "protocol_grounding", "protocol_tool_usage", "formatting"]
        )
        
        # Inject Profile from Context (if loaded in on_enter)
        if hasattr(self, "context_data") and self.context_data:
            profile_text = self.context_data.get("profile", "")
            if profile_text:
                system_prompt += f"\n\n## User Profile\n{profile_text}"
                
        # Inject Knowledge Core Context
        knowledge_context = await self.memory.get_knowledge_context(message)
        if knowledge_context:
            system_prompt += f"\n\n## Relevant Knowledge\n{knowledge_context}"

        # --- AUTO-ARCHIVING CHECK ---
        # Limit context to prevent "infinite context" crash
        # ARCHIVE_THRESHOLD: Hard limit where archiving is forced
        # SOFT_THRESHOLD: Warning limit where system is notified to wrap up
        ARCHIVE_THRESHOLD = 50
        SOFT_THRESHOLD = 40
        OVERLAP_COUNT = 8

        if len(history) >= ARCHIVE_THRESHOLD:
            print(f"[ProjectNode] Context size ({len(history)}) exceeded limit ({ARCHIVE_THRESHOLD}). Archiving...")
            
            from services.context_manager import ContextManager
            
            # 1. Initialize Context Manager
            cm = ContextManager(
                user_id=self.user_id,
                context_type="project", 
                project_id=self.project_id,
                db_session=self.context.get('db_session')
            )
            
            # 2. Archive & Summarize (with overlap)
            result = await cm.archive_context(force=True, overlap_count=OVERLAP_COUNT)
            
            if result.get("archived"):
                summary = result.get("summary", "Context archived.")
                overlap_messages = result.get("overlap_messages", [])
                
                # 3. Create NEW Session
                new_session_id = await self.memory.get_or_create_session(self.project_id, self.user_id)
                self.session_id = new_session_id
                self.context['session_id'] = new_session_id
                
                # 4. Inject Summary into new history as System Message
                from datetime import timedelta
                base_time = datetime.now() - timedelta(seconds=1)
                
                summary_msg = Message(
                    role=MessageRole.SYSTEM,
                    content=f"**PREVIOUS CONTEXT SUMMARY**:\n{summary}\n\nThe previous session was archived to maintain performance. Below are the last {len(overlap_messages)} messages for continuity.",
                    timestamp=base_time
                )
                
                # Convert overlap dicts back to Message objects if needed
                from models.message import MessageRole as MR
                carry_over_msgs = []
                for i, m_dict in enumerate(overlap_messages):
                    carry_over_msgs.append(Message(
                        role=MR(m_dict['role']),
                        content=m_dict['content'],
                        timestamp=base_time + timedelta(milliseconds=10 * (i + 1))
                    ))
                
                all_initial_msgs = [summary_msg] + carry_over_msgs
                await self.memory.save_messages(self.session_id, all_initial_msgs)
                
                # 4.5 Update triggering message timestamp to follow archival genesis
                current_msg.timestamp = datetime.now()
                
                # 5. Reset local history for this turn
                history = all_initial_msgs + [current_msg]
                
                print(f"[ProjectNode] Context archived successfully. New Session: {new_session_id}")
        
        elif len(history) >= SOFT_THRESHOLD:
            # Inject a silent system warning to the LLM
            warning_msg = Message(
                role=MessageRole.SYSTEM,
                content=f"[SYSTEM WARNING]: Conversation memory is at {len(history)}/{ARCHIVE_THRESHOLD} messages. "
                        "Archiving will occur soon. Please ensure any critical information or pending tasks are clearly stated or summarized.",
                timestamp=datetime.now()
            )
            # We don't save this to DB yet, just inject into prompt for this turn
            history.insert(-1, warning_msg)
            print(f"[ProjectNode] Soft threshold ({SOFT_THRESHOLD}) reached. Warning injected.")
            
        # Inject Active Team Roster (Meta-Cognition)
        roster_text = ""
        from models.database import AsyncSessionLocal, Node, Project
        from sqlalchemy import select, or_, and_
        async with AsyncSessionLocal() as db:
            # 1. System Nodes
            system_res = await db.execute(select(Node).filter(
                Node.node_type == "SYSTEM",
                Node.status == "active"
            ))
            system_nodes = system_res.scalars().all()
            
            # 2. Member Nodes (Current Project only)
            member_res = await db.execute(select(Node).filter(
                Node.project_id == self.project_id,
                Node.node_type == "MEMBER",
                Node.status == "active"
            ))
            member_nodes = member_res.scalars().all()
            
            # 3. Peer Projects (Other projects belonging to user)
            project_res = await db.execute(
                select(Node).join(Project, Node.project_id == Project.id).filter(
                    Project.user_id == self.user_id,
                    Node.node_type == "PROJECT",
                    Node.id != self.node_id,
                    Node.status == "active"
                )
            )
            peer_projects = project_res.scalars().all()
            
            if system_nodes or member_nodes or peer_projects:
                roster_text = "\n\n## Active Team Roster\nYou can communicate with these nodes using the 'ask_node' tool and their Target ID (UUID):\n"
                
                if system_nodes:
                    roster_text += "\n### System Nodes (Infrastructure)\n"
                    for m in system_nodes:
                        desc = m.description or "Provides core system capabilities."
                        roster_text += f"- **{m.display_name}** ({m.role_name})\n  - Target ID: `{m.id}`\n  - {desc}\n"
                
                if member_nodes:
                    roster_text += "\n### Project Specialists (Internal Delegation)\n"
                    for m in member_nodes:
                        desc = m.description or "Specialist for " + m.role_name
                        roster_text += f"- **{m.display_name}** ({m.role_name})\n  - Target ID: `{m.id}`\n  - {desc}\n"
                        
                if peer_projects:
                    roster_text += "\n### Peer Projects (Cross-Project Collaboration)\n"
                    for m in peer_projects:
                        desc = m.description or "Collaborative project node."
                        roster_text += f"- **{m.display_name}**\n  - Target ID: `{m.id}`\n  - {desc}\n"
        
        if roster_text:
            system_prompt += roster_text
        
        # 5. Check API Key
        if not self.context.get("api_key"):
            return "❌ No API Key found. Please configure your Gemini API Key in Settings > AI Config."

        llm_response = await self.chat_with_tools(
            system_prompt=system_prompt,
            message_history=history,
            tool_context={
                'user_id': self.user_id,
                'db_session': self.context.get('db_session'),  # For tools that need DB access
                'session_id': self.session_id,
                'node_id': self.node_id,
                'project_id': self.project_id,
                'context_data': self.context_data  # Pass full context data if needed
            }
        )
        
        # Extract content and tool_calls from response
        response_text = llm_response.content or ""
        tool_calls = llm_response.tool_calls if hasattr(llm_response, 'tool_calls') else None
        
        # Fallback for empty responses to avoid UI "No response" error
        if not response_text.strip() and not tool_calls:
             response_text = "I have processed your request."
        elif not response_text.strip() and tool_calls:
             pass 
        
        # Final safety net
        if not response_text.strip():
             response_text = "Task completed."

        # 5. Save History (User + Assistant) with tool_calls metadata
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response_text,
            timestamp=datetime.now(),
            meta_info={"tool_calls": tool_calls} if tool_calls else None
        )
        await self.memory.save_messages(self.session_id, [current_msg, assistant_msg])
        
        return response_text

    async def on_exit(self, result: Any):
        # Advocate is now handled by System AI Router for deep analysis.
        # Direct trigger removed to prevent duplicate analysis.
        pass

