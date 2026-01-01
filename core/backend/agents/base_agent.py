"""
Base agent class - now abstract with proper separation of concerns
Removes 10-message limit to use full Gemini context
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from pathlib import Path

from llm import get_provider
from models.message import Message, MessageRole, AttachedFile
from models.database import Node, ChatSession, ChatMessage, AgentProfile
from datetime import datetime
from uuid import uuid4
import json
from services.knowledge_core_service import KnowledgeCoreService
from services.context_manager import ContextManager



class BaseAgent(ABC):
    """Abstract base class for all AI agents"""
    
    def __init__(self, node_id: str, db_session, api_key: Optional[str] = None, user_id: Optional[str] = None):
        self.node_id = node_id
        self.db_session = db_session
        self.user_id = user_id  # Store for API key refresh
        self.conversation_history: List[Message] = []
        self.llm = get_provider(api_key=api_key)
        self.system_prompt = None
        
        # Agent-level tool storage (persists across LLM refreshes)
        self._agent_tool_definitions: List = []
        self._agent_tool_functions: dict = {}
        
        # Initialize active chat session
        self.current_session_id = self._get_or_create_active_session()
        
        # Load conversation history from DB
        self._load_history_from_db()
    
    def set_agent_tools(self, definitions: List, functions: dict):
        """Store tools at agent level (persists across LLM refreshes)"""
        self._agent_tool_definitions = definitions
        self._agent_tool_functions = functions
    
    def refresh_llm(self, api_key: str):
        """Refresh the LLM provider with a new API key (tools persist at agent level)"""
        if api_key:
            self.llm = get_provider(api_key=api_key)
            # No need to re-setup tools - they're stored at agent level now
    
    @abstractmethod
    def load_system_prompt(self) -> str:
        """
        Each agent type implements its own prompt loading logic
        Hub loads from hub_data/system_prompt.md
        Spoke loads from spokes/{name}/system_prompt.md
        """
        pass
    
    @abstractmethod
    def get_node_name(self) -> str:
        """Return the name (slug) of the node"""
        pass
    
    def chat(self, user_message: str, attached_files: List[AttachedFile] = None, preferred_model: Optional[str] = None, tool_context: dict = None, meta_info: Optional[str] = None) -> str:
        """
        Generic chat logic - same for all agents
        NOW SENDS ALL MESSAGES
        """
        # Load system prompt if not loaded
        if not self.system_prompt:
            self.system_prompt = self.load_system_prompt()
        
        # Create structured message
        msg = Message(
            role=MessageRole.USER,
            content=user_message,
            attached_files=attached_files or [],
            meta_info=meta_info
        )
        
        # Add to history
        self.conversation_history.append(msg)
        
        # --- KnowledgeCore Integration (Context) ---
        kc_prompt_augmentation = ""
        if self.user_id:
            kc_service = KnowledgeCoreService(self.db_session, self.user_id)
            context = kc_service.get_context(query=user_message, agent_id=self.get_node_name())
            if context and context.get("summary"):
                kc_prompt_augmentation = f"\n\n# Context from KnowledgeCore\n{context['summary']}"
                print(f"[{self.get_node_name()}] Augmented prompt with KnowledgeCore context")
        
        # Convert ALL messages to LLM format (NO LIMIT!)
        llm_messages = [m.to_llm_message() for m in self.conversation_history]
        
        # Format for LLM provider
        effective_system_prompt = self.system_prompt + kc_prompt_augmentation
        messages = self.llm.format_messages(
            effective_system_prompt,
            llm_messages  # ✅ ALL messages, not just last 10!
        )
        
        # Get response from LLM - pass agent-level tools directly
        response = self.llm.complete(
            messages, 
            preferred_model=preferred_model,
            tool_context=tool_context,
            attached_files=attached_files,
            tool_definitions=self._agent_tool_definitions,  # Pass tools directly
            tool_functions=self._agent_tool_functions       # Pass functions directly
        )
        
        # Create assistant message
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        
        # Add to history
        self.conversation_history.append(assistant_msg)
        
        # Save both messages to DB
        self._save_to_db(msg)
        self._save_to_db(assistant_msg)
        
        # --- KnowledgeCore Integration (Ingestion) ---
        if self.user_id:
            # Re-init or reuse kc_service
            kc_service = KnowledgeCoreService(self.db_session, self.user_id)
            kc_service.ingest_message(text=user_message, role="user", agent_id=self.get_node_name())
            kc_service.ingest_message(text=response.content, role="assistant", agent_id=self.get_node_name())
            print(f"[{self.get_node_name()}] Ingested messages to KnowledgeCore")
        
        return response.content
    
    def _get_or_create_active_session(self) -> str:
        """Get the latest active session or create a new one"""
        session = self.db_session.query(ChatSession).filter(
            ChatSession.node_id == self.node_id,
            ChatSession.is_archived == False
        ).order_by(ChatSession.created_at.desc()).first()
        
        if not session:
            session_id = str(uuid4())
            new_session = ChatSession(
                id=session_id,
                node_id=self.node_id,
                title="New Session",
                is_archived=False
            )
            self.db_session.add(new_session)
            self.db_session.commit()
            return session_id
        
        return session.id

    def _save_to_db(self, message: Message):
        """Save a message to the ChatMessage table"""
        # Convert attached files to meta_payload
        files_meta = [f.format_for_display() for f in message.attached_files]
        meta_payload = {
            "attached_files": files_meta,
            "meta_info": message.meta_info
        }
        
        db_message = ChatMessage(
            id=str(uuid4()),
            session_id=self.current_session_id,
            role=message.role.value,
            content=message.content,
            meta_payload=meta_payload,
            created_at=message.timestamp
        )
        self.db_session.add(db_message)
        self.db_session.commit()
    
    def _load_history_from_db(self):
        """Load conversation history from the active session in DB"""
        self.conversation_history = []
        
        # Fetch all messages from current session
        db_messages = self.db_session.query(ChatMessage).filter(
            ChatMessage.session_id == self.current_session_id
        ).order_by(ChatMessage.created_at.asc()).all()
        
        for db_msg in db_messages:
            # Reconstruct attached files (metadata only)
            files = []
            if db_msg.meta_payload and "attached_files" in db_msg.meta_payload:
                for f_data in db_msg.meta_payload["attached_files"]:
                    files.append(AttachedFile(
                        filename=f_data["name"],
                        file_type=f_data["type"],
                        size_bytes=f_data["size"]
                    ))
            
            msg = Message(
                role=MessageRole(db_msg.role),
                content=db_msg.content,
                timestamp=db_msg.created_at,
                attached_files=files,
                meta_info=db_msg.meta_payload.get("meta_info") if db_msg.meta_payload else None
            )
            self.conversation_history.append(msg)
            
        # Optional: Load summary from parent sessions if context rotation is needed
        # (Phase 3 logic can be expanded here)
    
    def _load_latest_summary(self, context_type: str, context_name: str) -> str:
        """Load the latest archived summary for this context"""
        if not self.user_id:
            return ""
            
        try:
            manager = ContextManager(
                user_id=self.user_id,
                context_type=context_type,
                context_name=context_name,
                session=self.db_session
            )
            summary = manager.get_latest_summary()
            if summary:
                return f"\n\n# Summary from Previous Session\n\n{summary}\n"
        except Exception as e:
            print(f"[{self.get_node_name()}] Failed to load latest summary: {e}")
            
        return ""
    
    def chat_with_context(self, context_message: str, preferred_model: Optional[str] = None) -> str:
        """
        Special chat method for injecting context or notifications.
        Acts as a normal chat but can be used for automated messages.
        """
        return self.chat(context_message, preferred_model=preferred_model)

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
