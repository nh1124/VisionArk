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
import time
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
        
        # --- Inject current time ---
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S (%A)')
        time_context = f"\n\n## Current Context\n- **Current Date & Time**: {current_time_str}\n"

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
            try:
                kc_service = KnowledgeCoreService(self.db_session, self.user_id)
                t0 = time.time()
                context = kc_service.get_context(query=user_message, agent_id=self.get_node_name())
                print(f"[{self.get_node_name()}/Timing] KC get_context: {time.time()-t0:.2f}s")
                if context and context.get("summary"):
                    kc_prompt_augmentation = f"\n\n# Context from KnowledgeCore\n{context['summary']}"
                    print(f"[{self.get_node_name()}] Augmented prompt with KnowledgeCore context")
            except Exception as e:
                print(f"[{self.get_node_name()}] KnowledgeCore context fetch failed: {e}")
        
        # Convert ALL messages to LLM format (NO LIMIT!)
        llm_messages = [m.to_llm_message() for m in self.conversation_history]
        
        # Format for LLM provider
        effective_system_prompt = self.system_prompt + time_context + kc_prompt_augmentation
        messages = self.llm.format_messages(
            effective_system_prompt,
            llm_messages  # ✅ ALL messages, not just last 10!
        )
        
        # Get response from LLM - pass agent-level tools directly
        try:
            t0 = time.time()
            
            # Merge meta_info into tool_context for function injection
            effective_tool_context = (tool_context or {}).copy()
            if meta_info:
                effective_tool_context['meta_info'] = meta_info
                
            response = self.llm.complete(
                messages, 
                preferred_model=preferred_model,
                tool_context=effective_tool_context,
                attached_files=attached_files,
                tool_definitions=self._agent_tool_definitions,  # Pass tools directly
                tool_functions=self._agent_tool_functions       # Pass functions directly
            )
            print(f"[{self.get_node_name()}/Timing] LLM complete: {time.time()-t0:.2f}s")
        except Exception as e:
            # Log the error and return a graceful error message
            import traceback
            error_msg = f"LLM call failed: {str(e)}"
            print(f"[{self.get_node_name()}] ERROR: {error_msg}")
            print(traceback.format_exc())
            
            # Remove the user message from history since we couldn't process it
            if self.conversation_history and self.conversation_history[-1] == msg:
                self.conversation_history.pop()
            
            # Return error response
            return (f"⚠️ I encountered an error processing your message: {str(e)}", [])
        
        # Create assistant message
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response.content
        )
        
        # Add to history
        self.conversation_history.append(assistant_msg)
        
        # Save both messages to DB
        try:
            self._save_to_db(msg)
            self._save_to_db(assistant_msg)
        except Exception as e:
            print(f"[{self.get_node_name()}] Failed to save messages to DB: {e}")
        
        # --- KnowledgeCore Integration (Ingestion) - Run in Background ---
        if self.user_id:
            import threading
            
            def _background_ingest(user_id, user_msg, assistant_msg, node_name):
                """Background task for KC ingestion to avoid blocking response"""
                try:
                    # Create a new DB engine/session for the background thread
                    from models.database import get_engine, get_session
                    bg_session = get_session(get_engine())
                    try:
                        kc_service = KnowledgeCoreService(bg_session, user_id)
                        t0 = time.time()
                        # Run both ingests sequentially in the background thread (since it's already background)
                        kc_service.ingest_message(text=user_msg, role="user", agent_id=node_name)
                        kc_service.ingest_message(text=assistant_msg, role="assistant", agent_id=node_name)
                        print(f"[{node_name}/Background] KC ingest completed: {time.time()-t0:.2f}s")
                    finally:
                        bg_session.close()
                except Exception as e:
                    print(f"[{node_name}/Background] KC ingestion failed: {e}")
            
            # Start background thread for ingestion
            thread = threading.Thread(
                target=_background_ingest,
                args=(self.user_id, user_message, response.content, self.get_node_name()),
                daemon=True
            )
            thread.start()
            print(f"[{self.get_node_name()}] KC ingestion started in background")
        
        # Return content and tool_calls separately
        return (response.content, response.tool_calls or [])
    
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
                        filename=f_data.get("name") or f_data.get("filename"),
                        file_type=f_data.get("type") or f_data.get("file_type"),
                        size_bytes=f_data.get("size") or f_data.get("size_bytes", 0)
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
