"""
Context Management Service
Handles log rotation, summarization, and context archiving
"""
import os
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from llm import get_provider
from llm.base_provider import Message
from utils.paths import get_spoke_dir, get_user_hub_dir


class ContextManager:
    """Manages conversation context rotation and archiving (per-user)"""
    
    def __init__(self, user_id: str, context_type: str, context_name: str, session: Optional[AsyncSession] = None):
        """
        Initialize context manager
        
        Args:
            user_id: User ID for scoped paths
            context_type: "hub" or "spoke"
            context_name: Hub or spoke name
            session: Database session for tracking
        """
        self.user_id = user_id
        self.context_type = context_type
        self.context_name = context_name
        self.session = session
        
        if context_type == "hub":
            self.base_dir = get_user_hub_dir(user_id)
        else:
            self.base_dir = get_spoke_dir(user_id, context_name)
        
        self.chat_log_path = self.base_dir / "chat.log"
        self.logs_archive_dir = self.base_dir / "logs"
        self.logs_archive_dir.mkdir(parents=True, exist_ok=True)
        
        # Will be initialized on demand with user API key
        self._llm = None
    
    async def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Load conversation history from database (preferred) or chat log (fallback)
        """
        if self.session:
            from models.database import Node, ChatSession, ChatMessage
            from sqlalchemy import select
            
            try:
                # 1. Find the Node
                node_result = await self.session.execute(select(Node).filter(
                    Node.user_id == self.user_id,
                    Node.name == self.context_name,
                    Node.node_type == self.context_type.upper()
                ))
                node = node_result.scalars().first()
                if not node:
                    return []
                
                # 2. Get active session
                session_result = await self.session.execute(select(ChatSession).filter(
                    ChatSession.node_id == node.id,
                    ChatSession.is_archived == False
                ).order_by(ChatSession.created_at.desc()))
                chat_session = session_result.scalars().first()
                if not chat_session:
                    return []
                
                # 3. Get messages
                msg_result = await self.session.execute(select(ChatMessage).filter(
                    ChatMessage.session_id == chat_session.id
                ).order_by(ChatMessage.created_at.asc()))
                db_messages = msg_result.scalars().all()
                
                return [
                    {"role": m.role, "content": m.content}
                    for m in db_messages
                ]
            except Exception as e:
                print(f"[ContextManager] DB history fetch failed: {e}")
                # Fall through to legacy log check
        
        # Legacy: Load conversation history from chat log
        if not self.chat_log_path.exists():
            return []
    
    async def _get_llm(self):
        """Lazy load LLM with user context"""
        if self._llm:
            return self._llm
            
        from models.database import UserSettings
        from sqlalchemy import select
        
        result = await self.session.execute(select(UserSettings).filter(UserSettings.user_id == self.user_id))
        settings = result.scalars().first()
        api_key = settings.gemini_api_key if settings else None
        
        self._llm = get_provider(api_key=api_key)
        return self._llm

    async def generate_summary(self, conversation: List[Dict[str, str]]) -> str:
        """
        Generate AI summary of conversation asynchronously
        """
        if not conversation:
            return "No conversation to summarize."
        
        summary_prompt = """You are summarizing a conversation for context preservation. Extract:
1. **Decisions Made**: Key choices and conclusions
2. **Pending Issues**: Unresolved problems or open questions
3. **Key Facts**: Important information to preserve

Format as markdown with these sections. Be concise but comprehensive.

Conversation to summarize:
---
"""
        for msg in conversation:
            summary_prompt += f"\n{msg['role'].capitalize()}: {msg['content']}\n"
        
        summary_prompt += "\n---\nGenerate the summary now:"
        
        try:
            llm = await self._get_llm()
            messages = [Message(role="user", content=summary_prompt)]
            response = await llm.complete_async(messages, temperature=0.3)
            return response.content
        except Exception as e:
            return f"Summary generation failed: {str(e)}\n\nConversation had {len(conversation)} messages."
    
    async def archive_context(self, force: bool = False) -> Dict:
        """
        Archive current context asynchronously. 
        Supports injecting external 'conversation' data or defaults to get_conversation_history().
        """
        conversation = await self.get_conversation_history()
        
        if not conversation and not force:
            return {
                "archived": False,
                "reason": "empty_conversation",
                "message": "Chat log is empty"
            }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = await self.generate_summary(conversation)
        summary_path = self.logs_archive_dir / f"archived_summary_{timestamp}.md"
        await asyncio.to_thread(summary_path.write_text, summary, encoding='utf-8')
        
        if self.chat_log_path.exists():
            # Only rotate files if we didn't use injected conversation (Legacy Sync)
            archived_log_path = self.logs_archive_dir / f"chat_{timestamp}.log"
            await asyncio.to_thread(shutil.move, str(self.chat_log_path), str(archived_log_path))
            await asyncio.to_thread(self.chat_log_path.touch)
        else:
            # If we had injected data or no log file, just record None for log path
            archived_log_path = None
        
        if self.session:
            await self._save_archive_record(summary_path, archived_log_path, len(conversation))
        
        return {
            "archived": True,
            "timestamp": timestamp,
            "summary_path": str(summary_path),
            "log_path": str(archived_log_path) if archived_log_path else None,
            "message_count": len(conversation),
            "message": f"✅ Archived {len(conversation)} messages. Context refreshed."
        }
    
    async def get_latest_summary(self) -> Optional[str]:
        """Get the most recent archived summary asynchronously"""
        summaries = sorted(self.logs_archive_dir.glob("archived_summary_*.md"))
        
        if not summaries:
            return None
        
        latest_summary = summaries[-1]
        # Use asyncio.to_thread for file I/O
        return await asyncio.to_thread(latest_summary.read_text, encoding='utf-8')
    
    async def get_stats(self) -> Dict:
        """Get context statistics"""
        history = await self.get_conversation_history()
        archives = await self.get_archive_history()
        
        return {
            "context_type": self.context_type,
            "context_name": self.context_name,
            "current_messages": len(history),
            "archived_contexts": len(archives),
            "should_archive": len(history) > 30,  # Threshold for recommendation
            "latest_summary_available": len(archives) > 0
        }
    
    async def get_archive_history(self) -> List[Dict]:
        """Get list of all archived contexts asynchronously"""
        if self.session:
            from models.database import ArchivedContext
            from sqlalchemy import select
            
            try:
                result = await self.session.execute(
                    select(ArchivedContext).filter(
                        ArchivedContext.spoke_name == self.context_name,
                        ArchivedContext.user_id == self.user_id
                    ).order_by(ArchivedContext.archived_at.desc())
                )
                archives = result.scalars().all()
                
                return [
                    {
                        "id": row.id,
                        "archived_at": row.archived_at,
                        "summary_path": row.summary_path,
                        "log_path": row.log_path,
                        "message_count": row.token_count
                    }
                    for row in archives
                ]
            except Exception as e:
                print(f"[ContextManager] DB archive fetch failed: {e}")
                # Fall through to filesystem check
        
        # Fallback: list from filesystem
        summaries = sorted(self.logs_archive_dir.glob("archived_summary_*.md"))
        return [
            {
                "summary_path": str(s),
                "archived_at": datetime.fromtimestamp(s.stat().st_mtime).isoformat()
            }
            for s in summaries
        ]
    
    async def _save_archive_record(self, summary_path: Path, log_path: Path, message_count: int):
        """Save archive metadata to database asynchronously using ORM"""
        if not self.session:
            return
        
        from models.database import ArchivedContext, Node
        from sqlalchemy import select
        
        try:
            # Try to find node_id for better indexing
            result = await self.session.execute(
                select(Node.id).filter(
                    Node.user_id == self.user_id,
                    Node.name == self.context_name,
                    Node.node_type == self.context_type.upper()
                )
            )
            node_id = result.scalars().first()
            
            new_record = ArchivedContext(
                user_id=self.user_id,
                node_id=node_id,
                spoke_name=self.context_name,
                archived_at=datetime.utcnow(),
                summary_path=str(summary_path),
                log_path=str(log_path) if log_path else None,
                token_count=message_count
            )
            
            self.session.add(new_record)
            await self.session.commit()
            print(f"[ContextManager] Archived context record saved for {self.context_name}")
        except Exception as e:
            print(f"Failed to save archive record: {e}")
            await self.session.rollback()
