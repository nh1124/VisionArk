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
import asyncio
import threading
import traceback
from sqlalchemy import select, update
from sqlalchemy.future import select as async_select
from sqlalchemy.ext.asyncio import AsyncSession
from services.knowledge_core_service import KnowledgeCoreService
from services.context_manager import ContextManager



class BaseAgent(ABC):
    """Abstract base class for all AI agents"""
    
    def __init__(self, node_id: str, db_session: AsyncSession, api_key: Optional[str] = None, user_id: Optional[str] = None):
        self.node_id = node_id
        self.db_session = db_session
        self.user_id = user_id  # Store for API key refresh
        self.conversation_history: List[Message] = []
        self.llm = get_provider(api_key=api_key)
        self.system_prompt = None
        
        # Agent-level tool storage (persists across LLM refreshes)
        self._agent_tool_definitions: List = []
        self._agent_tool_functions: dict = {}
        
        self.current_session_id = None

    async def initialize(self):
        """Asynchronously initialize the agent (DB loading)"""
        if not self.current_session_id:
            self.current_session_id = await self._get_or_create_active_session()
        
        if not self.conversation_history:
            await self._load_history_from_db()
        
        if not self.system_prompt:
            self.system_prompt = await self.load_system_prompt()
    
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
    async def load_system_prompt(self) -> str:
        """Each agent type implements its own prompt loading logic"""
        pass
    
    @abstractmethod
    def get_node_name(self) -> str:
        """Return the name (slug) of the node"""
        pass
    
    async def chat(self, user_message: str, attached_files: List[AttachedFile] = None, preferred_model: Optional[str] = None, tool_context: dict = None, meta_info: Optional[str] = None) -> str:
        """
        Generic chat logic - same for all agents
        NOW SENDS ALL MESSAGES
        """
        # Load system prompt if not loaded
        if not self.system_prompt:
            self.system_prompt = await self.load_system_prompt()
        
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
                context = await kc_service.get_context(query=user_message, agent_id=self.get_node_name())
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
            llm_messages
        )
        
        # Get response from LLM - pass agent-level tools directly
        try:
            t0 = time.time()
            
            # Merge meta_info into tool_context for function injection
            effective_tool_context = (tool_context or {}).copy()
            if meta_info:
                effective_tool_context['meta_info'] = meta_info
                
            response = await self.llm.complete_async(
                messages, 
                preferred_model=preferred_model,
                tool_context=effective_tool_context,
                attached_files=attached_files,
                tool_definitions=self._agent_tool_definitions,
                tool_functions=self._agent_tool_functions
            )
            print(f"[{self.get_node_name()}/Timing] LLM complete: {time.time()-t0:.2f}s")
        except Exception as e:
            # Log the error and return a graceful error message
            error_msg = f"LLM call failed: {str(e)}"
            print(f"[{self.get_node_name()}] ERROR: {error_msg}")
            traceback.print_exc()
            
            # Remove the user message from history since we couldn't process it
            if self.conversation_history and self.conversation_history[-1] == msg:
                self.conversation_history.pop()
            
            # Return error response
            return (f"⚠️ I encountered an error processing your message: {str(e)}", [])
        
        assistant_msg = Message(
            role=MessageRole.ASSISTANT,
            content=response.content or ""
        )
        self.conversation_history.append(assistant_msg)
        
        try:
            await self._save_to_db(msg)
            
            files_meta = [f.format_for_display() for f in assistant_msg.attached_files]
            meta_payload = {
                "attached_files": files_meta,
                "meta_info": assistant_msg.meta_info,
                "tool_calls": response.tool_calls or []
            }
            
            db_assistant_message = ChatMessage(
                id=str(uuid4()),
                session_id=self.current_session_id,
                role=assistant_msg.role.value,
                content=assistant_msg.content or "",
                meta_payload=meta_payload,
                created_at=assistant_msg.timestamp
            )
            self.db_session.add(db_assistant_message)
            await self.db_session.commit()
        except Exception as e:
            print(f"[{self.get_node_name()}] Failed to save messages to DB: {e}")
        
        # --- KnowledgeCore Integration (Ingestion) - Async Task ---
        if self.user_id:
            async def _background_ingest(user_id, user_msg, assistant_msg, node_name):
                """Background task for KC ingestion"""
                try:
                    from models.database import get_async_engine, get_async_session_maker
                    engine = get_async_engine()
                    session_maker = get_async_session_maker(engine)
                    async with session_maker() as bg_session:
                        kc_service = KnowledgeCoreService(bg_session, user_id)
                        t0 = time.time()
                        await kc_service.ingest_message(text=user_msg, role="user", agent_id=node_name)
                        await kc_service.ingest_message(text=assistant_msg, role="assistant", agent_id=node_name)
                        print(f"[{node_name}/Background] KC ingest completed: {time.time()-t0:.2f}s")
                except Exception as e:
                    print(f"[{node_name}/Background] KC ingestion failed: {e}")
            
            # Start background ingestion
            asyncio.create_task(_background_ingest(self.user_id, user_message, response.content, self.get_node_name()))
            print(f"[{self.get_node_name()}] KC ingestion started as background task")
        
        return (response.content, response.tool_calls or [])
    
    async def _get_or_create_active_session(self) -> str:
        """Get the latest active session or create a new one"""
        result = await self.db_session.execute(
            select(ChatSession).filter(
                ChatSession.node_id == self.node_id,
                ChatSession.is_archived == False
            ).order_by(ChatSession.created_at.desc())
        )
        session = result.scalars().first()
        
        if not session:
            session_id = str(uuid4())
            new_session = ChatSession(
                id=session_id,
                node_id=self.node_id,
                title="New Session",
                is_archived=False
            )
            self.db_session.add(new_session)
            await self.db_session.commit()
            return session_id
        
        return session.id

    async def _save_to_db(self, message: Message):
        """Save a message to the ChatMessage table"""
        # Convert attached files to meta_payload
        files_meta = [f.to_dict() for f in message.attached_files]
        meta_payload = {
            "attached_files": files_meta,
            "meta_info": message.meta_info
        }
        
        db_message = ChatMessage(
            id=str(uuid4()),
            session_id=self.current_session_id,
            role=message.role.value,
            content=message.content or "", # Extra safety
            meta_payload=meta_payload,
            created_at=message.timestamp
        )
        self.db_session.add(db_message)
        await self.db_session.commit()
    
    async def _load_history_from_db(self):
        """Load conversation history from the active session in DB"""
        self.conversation_history = []
        
        # Fetch all messages from current session
        result = await self.db_session.execute(
            select(ChatMessage).filter(
                ChatMessage.session_id == self.current_session_id
            ).order_by(ChatMessage.created_at.asc())
        )
        db_messages = result.scalars().all()
        
        for db_msg in db_messages:
            try:
                # Reconstruct attached files using new robust from_dict
                files = []
                if db_msg.meta_payload and isinstance(db_msg.meta_payload, dict) and "attached_files" in db_msg.meta_payload:
                    files = [AttachedFile.from_dict(f) for f in db_msg.meta_payload["attached_files"] if isinstance(f, dict)]
                
                # Case-insensitive role mapping
                role_val = db_msg.role.lower() if db_msg.role else "user"
                try:
                    role_enum = MessageRole(role_val)
                except ValueError:
                    print(f"[{self.get_node_name()}] Warning: Invalid role '{db_msg.role}' in history. Defaulting to user.")
                    role_enum = MessageRole.USER

                msg = Message(
                    role=role_enum,
                    content=db_msg.content or "",
                    timestamp=db_msg.created_at or datetime.now(),
                    attached_files=files,
                    meta_info=db_msg.meta_payload.get("meta_info") if (db_msg.meta_payload and isinstance(db_msg.meta_payload, dict)) else None
                )
                self.conversation_history.append(msg)
            except Exception as e:
                print(f"[{self.get_node_name()}] Critical error loading history message {db_msg.id}: {e}")
                import traceback
                traceback.print_exc()
                # Continue loading other messages instead of crashing the whole history
                continue
            
        # Optional: Load summary from parent sessions if context rotation is needed
        # (Phase 3 logic can be expanded here)
    
    async def _load_latest_summary(self, context_type: str, context_name: str) -> str:
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
            summary = await manager.get_latest_summary()
            if summary:
                return f"\n\n# Summary from Previous Session\n\n{summary}\n"
        except Exception as e:
            print(f"[{self.get_node_name()}] Failed to load latest summary: {e}")
            
        return ""
    
    async def chat_stream(self, user_message: str, attached_files: List[AttachedFile] = None, preferred_model: Optional[str] = None, tool_context: dict = None, meta_info: Optional[str] = None):
        """
        Streaming version of chat logic.
        Yields events: status, content, tool_calls, final_response
        """
        if not self.system_prompt:
            self.system_prompt = await self.load_system_prompt()
        
        current_time_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S (%A)')
        time_context = f"\n\n## Current Context\n- **Current Date & Time**: {current_time_str}\n"

        msg = Message(
            role=MessageRole.USER,
            content=user_message,
            attached_files=attached_files or [],
            meta_info=meta_info
        )
        self.conversation_history.append(msg)
        
        kc_prompt_augmentation = ""
        if self.user_id:
            try:
                kc_service = KnowledgeCoreService(self.db_session, self.user_id)
                context = await kc_service.get_context(query=user_message, agent_id=self.get_node_name())
                if context and context.get("summary"):
                    kc_prompt_augmentation = f"\n\n# Context from KnowledgeCore\n{context['summary']}"
            except Exception as e:
                print(f"[{self.get_node_name()}] KnowledgeCore context fetch failed: {e}")
        
        llm_messages = [m.to_llm_message() for m in self.conversation_history]
        effective_system_prompt = self.system_prompt + time_context + kc_prompt_augmentation
        messages = self.llm.format_messages(effective_system_prompt, llm_messages)
        
        effective_tool_context = (tool_context or {}).copy()
        if meta_info:
            effective_tool_context['meta_info'] = meta_info

        # Track the final result for history saving
        final_content = ""
        final_tool_calls = []

        # DEBUG: Log before streaming
        print(f"[DEBUG chat_stream] Starting stream: model={preferred_model}, msg_len={len(user_message)}")

        # Stream from LLM - USE stream_chat_async
        async for event in self.llm.stream_chat_async(
            messages,
            preferred_model=preferred_model,
            tool_context=effective_tool_context,
            attached_files=attached_files,
            tool_definitions=self._agent_tool_definitions,
            tool_functions=self._agent_tool_functions
        ):
            # DEBUG: Log each event type
            print(f"[DEBUG chat_stream] Event: type={event.get('type')}, data_len={len(str(event.get('data', '')))}")
            
            if event["type"] == "content":
                final_content += event["data"]
            elif event["type"] == "final_response":
                final_tool_calls = event["data"].get("tool_calls", [])
            
            yield event

        # Save to DB after stream finishes
        try:
            await self._save_to_db(msg)
            
            assistant_msg = Message(
                role=MessageRole.ASSISTANT,
                content=final_content
            )
            self.conversation_history.append(assistant_msg)
            
            meta_payload = {
                "attached_files": [f.format_for_display() for f in assistant_msg.attached_files],
                "meta_info": assistant_msg.meta_info,
                "tool_calls": final_tool_calls
            }
            
            db_assistant_message = ChatMessage(
                id=str(uuid4()),
                session_id=self.current_session_id,
                role=assistant_msg.role.value,
                content=assistant_msg.content or "",
                meta_payload=meta_payload,
                created_at=assistant_msg.timestamp
            )
            self.db_session.add(db_assistant_message)
            await self.db_session.commit()
            
            # Start background ingestion
            if self.user_id:
                async def _background_ingest(user_id, user_msg, assistant_msg, node_name):
                    try:
                        from models.database import get_async_engine, get_async_session_maker
                        engine = get_async_engine()
                        session_maker = get_async_session_maker(engine)
                        async with session_maker() as bg_session:
                            kc_service = KnowledgeCoreService(bg_session, user_id)
                            await kc_service.ingest_message(text=user_msg, role="user", agent_id=node_name)
                            await kc_service.ingest_message(text=assistant_msg, role="assistant", agent_id=node_name)
                    except Exception as e:
                        print(f"[{node_name}/Background] KC ingestion failed: {e}")
                
                asyncio.create_task(_background_ingest(self.user_id, user_message, final_content, self.get_node_name()))
        except Exception as e:
            print(f"[{self.get_node_name()}] Failed to save streamed messages to DB: {e}")

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
