"""
Context Management Service
Handles log rotation, summarization, and context archiving
"""
import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import text

from llm import get_provider
from llm.base_provider import Message
from utils.paths import get_spoke_dir, get_hub_dir


class ContextManager:
    """Manages conversation context rotation and archiving"""
    
    def __init__(self, context_type: str, context_name: str, session: Optional[Session] = None):
        """
        Initialize context manager
        
        Args:
            context_type: "hub" or "spoke"
            context_name: Hub or spoke name
            session: Database session for tracking
        """
        self.context_type = context_type
        self.context_name = context_name
        self.session = session
        
        if context_type == "hub":
            self.base_dir = get_hub_dir()
        else:
            self.base_dir = get_spoke_dir(context_name)
        
        self.chat_log_path = self.base_dir / "chat.log"
        self.logs_archive_dir = self.base_dir / "logs"
        self.logs_archive_dir.mkdir(parents=True, exist_ok=True)
        
        self.llm = get_provider()
    
    def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Load conversation history from chat log
        
        Returns:
            List of {"role": str, "content": str} messages
        """
        if not self.chat_log_path.exists():
            return []
        
        # Simple format: alternating user/assistant messages
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
        
        # Add last message
        if current_role and current_content:
            messages.append({
                "role": current_role,
                "content": "\n".join(current_content)
            })
        
        return messages
    
    def generate_summary(self, conversation: List[Dict[str, str]]) -> str:
        """
        Generate AI summary of conversation
        
        Args:
            conversation: List of messages
        
        Returns:
            Markdown-formatted summary
        """
        if not conversation:
            return "No conversation to summarize."
        
        # Build summarization prompt
        summary_prompt = """You are summarizing a conversation for context preservation. Extract:

1. **Decisions Made**: Key choices and conclusions
2. **Pending Issues**: Unresolved problems or open questions
3. **Key Facts**: Important information to preserve

Format as markdown with these sections. Be concise but comprehensive.

Conversation to summarize:
---
"""
        
        # Add conversation (limit to avoid token overflow)
        for msg in conversation[-50:]:  # Last 50 messages
            summary_prompt += f"\n{msg['role'].capitalize()}: {msg['content']}\n"
        
        summary_prompt += "\n---\nGenerate the summary now:"
        
        # Generate summary
        try:
            messages = [Message(role="user", content=summary_prompt)]
            response = self.llm.complete(messages, temperature=0.3)
            return response.content
        except Exception as e:
            return f"Summary generation failed: {str(e)}\n\nConversation had {len(conversation)} messages."
    
    def archive_context(self, force: bool = False) -> Dict:
        """
        Archive current context and rotate logs
        
        Args:
            force: Force archiving even if not needed
        
        Returns:
            Archive result with paths and stats
        """
        # Check if chat log exists
        if not self.chat_log_path.exists():
            return {
                "archived": False,
                "reason": "no_chat_log",
                "message": "No chat history to archive"
            }
        
        # Get conversation history
        conversation = self.get_conversation_history()
        
        if not conversation and not force:
            return {
                "archived": False,
                "reason": "empty_conversation",
                "message": "Chat log is empty"
            }
        
        # Generate timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Generate summary
        summary = self.generate_summary(conversation)
        summary_path = self.base_dir / f"archived_summary_{timestamp}.md"
        summary_path.write_text(summary, encoding='utf-8')
        
        # Move chat log to archive
        archived_log_path = self.logs_archive_dir / f"chat_{timestamp}.log"
        shutil.move(str(self.chat_log_path), str(archived_log_path))
        
        # Create new empty chat log
        self.chat_log_path.touch()
        
        # Track in database
        if self.session and self.context_type == "spoke":
            self._save_archive_record(summary_path, archived_log_path, len(conversation))
        
        return {
            "archived": True,
            "timestamp": timestamp,
            "summary_path": str(summary_path),
            "log_path": str(archived_log_path),
            "message_count": len(conversation),
            "message": f"✅ Archived {len(conversation)} messages. Context refreshed."
        }
    
    def get_latest_summary(self) -> Optional[str]:
        """Get the most recent archived summary"""
        summaries = sorted(self.base_dir.glob("archived_summary_*.md"))
        
        if not summaries:
            return None
        
        latest_summary = summaries[-1]
        return latest_summary.read_text(encoding='utf-8')
    
    def get_archive_history(self) -> List[Dict]:
        """Get list of all archived contexts"""
        if self.context_type == "spoke" and self.session:
            query = text("""
                SELECT id, archived_at, summary_path, log_path, token_count
                FROM archived_contexts
                WHERE spoke_name = :spoke_name
                ORDER BY archived_at DESC
            """)
            
            result = self.session.execute(query, {"spoke_name": self.context_name})
            
            return [
                {
                    "id": row[0],
                    "archived_at": row[1],
                    "summary_path": row[2],
                    "log_path": row[3],
                    "message_count": row[4]
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
    
    def _save_archive_record(self, summary_path: Path, log_path: Path, message_count: int):
        """Save archive metadata to database"""
        if not self.session:
            return
        
        try:
            query = text("""
                INSERT INTO archived_contexts (spoke_name, archived_at, summary_path, log_path, token_count)
                VALUES (:spoke_name, :archived_at, :summary_path, :log_path, :token_count)
            """)
            
            self.session.execute(query, {
                "spoke_name": self.context_name,
                "archived_at": datetime.now(),
                "summary_path": str(summary_path),
                "log_path": str(log_path),
                "token_count": message_count
            })
            self.session.commit()
        except Exception as e:
            print(f"Failed to save archive record: {e}")
