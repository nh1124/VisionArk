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
        
        self.llm = get_provider()
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Load conversation history from chat log
        """
        if not self.chat_log_path.exists():
            return []
        
        messages = []
        current_role = None
        current_content = []
        
        with open(self.chat_log_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith("User:"):
                    if current_role:
                        messages.append({
                            "role": current_role,
                            "content": "\n".join(current_content)
                        })
                    current_role = "user"
                    current_content = [line[5:].strip()]
                elif line.startswith("Assistant:"):
                    if current_role:
                        messages.append({
                            "role": current_role,
                            "content": "\n".join(current_content)
                        })
                    current_role = "assistant"
                    current_content = [line[10:].strip()]
                elif line and current_role:
                    current_content.append(line)
        
        if current_role and current_content:
            messages.append({
                "role": current_role,
                "content": "\n".join(current_content)
            })
        
        return messages
    
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
        for msg in conversation[-50:]:
            summary_prompt += f"\n{msg['role'].capitalize()}: {msg['content']}\n"
        
        summary_prompt += "\n---\nGenerate the summary now:"
        
        try:
            messages = [Message(role="user", content=summary_prompt)]
            response = await self.llm.complete_async(messages, temperature=0.3)
            return response.content
        except Exception as e:
            return f"Summary generation failed: {str(e)}\n\nConversation had {len(conversation)} messages."
    
    async def archive_context(self, force: bool = False) -> Dict:
        """
        Archive current context and rotate logs asynchronously
        """
        if not self.chat_log_path.exists():
            return {
                "archived": False,
                "reason": "no_chat_log",
                "message": "No chat history to archive"
            }
        
        conversation = await asyncio.to_thread(self.get_conversation_history)
        
        if not conversation and not force:
            return {
                "archived": False,
                "reason": "empty_conversation",
                "message": "Chat log is empty"
            }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        summary = await self.generate_summary(conversation)
        summary_path = self.base_dir / f"archived_summary_{timestamp}.md"
        await asyncio.to_thread(summary_path.write_text, summary, encoding='utf-8')
        
        archived_log_path = self.logs_archive_dir / f"chat_{timestamp}.log"
        await asyncio.to_thread(shutil.move, str(self.chat_log_path), str(archived_log_path))
        
        await asyncio.to_thread(self.chat_log_path.touch)
        
        if self.session and self.context_type == "spoke":
            await self._save_archive_record(summary_path, archived_log_path, len(conversation))
        
        return {
            "archived": True,
            "timestamp": timestamp,
            "summary_path": str(summary_path),
            "log_path": str(archived_log_path),
            "message_count": len(conversation),
            "message": f"✅ Archived {len(conversation)} messages. Context refreshed."
        }
    
    async def get_latest_summary(self) -> Optional[str]:
        """Get the most recent archived summary asynchronously"""
        summaries = sorted(self.base_dir.glob("archived_summary_*.md"))
        
        if not summaries:
            return None
        
        latest_summary = summaries[-1]
        # Use asyncio.to_thread for file I/O
        return await asyncio.to_thread(latest_summary.read_text, encoding='utf-8')
    
    async def get_stats(self) -> Dict:
        """Get context statistics"""
        history = await asyncio.to_thread(self.get_conversation_history)
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
        if self.context_type == "spoke" and self.session:
            query = text("""
                SELECT id, archived_at, summary_path, log_path, token_count
                FROM archived_contexts
                WHERE spoke_name = :spoke_name AND user_id = :user_id
                ORDER BY archived_at DESC
            """)
            
            result = await self.session.execute(query, {
                "spoke_name": self.context_name,
                "user_id": self.user_id
            })
            
            return [
                {
                    "id": row.id,
                    "archived_at": row.archived_at,
                    "summary_path": row.summary_path,
                    "log_path": row.log_path,
                    "message_count": row.token_count
                }
                for row in result
            ]
        
        # Fallback: list from filesystem
        summaries = sorted(self.base_dir.glob("archived_summary_*.md"))
        return [
            {
                "summary_path": str(s),
                "archived_at": datetime.fromtimestamp(s.stat().st_mtime).isoformat()
            }
            for s in summaries
        ]
    
    async def _save_archive_record(self, summary_path: Path, log_path: Path, message_count: int):
        """Save archive metadata to database asynchronously"""
        if not self.session:
            return
        
        try:
            query = text("""
                INSERT INTO archived_contexts (spoke_name, user_id, archived_at, summary_path, log_path, token_count)
                VALUES (:spoke_name, :user_id, :archived_at, :summary_path, :log_path, :token_count)
            """)
            
            await self.session.execute(query, {
                "spoke_name": self.context_name,
                "user_id": self.user_id,
                "archived_at": datetime.now(),
                "summary_path": str(summary_path),
                "log_path": str(log_path),
                "token_count": message_count
            })
            await self.session.commit()
        except Exception as e:
            print(f"Failed to save archive record: {e}")
            await self.session.rollback()
