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

from infrastructure.llm import get_provider
from infrastructure.llm.base_provider import Message
from shared.paths import get_project_dir, get_prompts_dir


class ContextManager:
    """Manages conversation context rotation and archiving (per-user)"""
    
    def __init__(self, user_id: str, context_type: str, project_id: str, db_session: Optional[AsyncSession] = None):
        """
        Initialize context manager
        
        Args:
            user_id: User ID for scoped paths
            context_type: "project" (formerly hub/spoke)
            project_id: Project UUID or identifier
            db_session: Database session for tracking
        """
        self.user_id = user_id
        self.context_type = context_type
        self.project_id = project_id
        self.db_session = db_session
        
        # V5: ID-based Unified Project Paths
        # Hub is treated as a project with ID 'hub'
        target_id = project_id
        self.base_dir = get_project_dir(user_id, target_id)
        
        self.chat_log_path = self.base_dir / "chat.log"
        self.logs_archive_dir = self.base_dir / "logs"
        self.logs_archive_dir.mkdir(parents=True, exist_ok=True)
        
        # For legacy DB compatibility (project_name field)
        self.context_name = None # Will resolve on demand if needed
        
        # Will be initialized on demand with user API key
        self._llm = None
    
    async def get_conversation_history(self) -> List[Dict[str, str]]:
        """
        Load conversation history from database (preferred) or chat log (fallback)
        """
        if self.db_session:
            from shared.database import Project, ChatSession, ChatMessage
            from sqlalchemy import select
            
            try:
                # 1. Find the Project by ID
                proj_result = await self.db_session.execute(select(Project).filter(
                    Project.user_id == self.user_id,
                    Project.id == self.project_id
                ))
                proj = proj_result.scalars().first()
                if not proj:
                    return []
                
                # 2. Get active session
                session_result = await self.db_session.execute(select(ChatSession).filter(
                    ChatSession.project_id == proj.id,
                    ChatSession.is_archived == False
                ).order_by(ChatSession.created_at.desc()))
                chat_session = session_result.scalars().first()
                if not chat_session:
                    return []
                
                # 3. Get messages
                msg_result = await self.db_session.execute(select(ChatMessage).filter(
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
            
        from shared.database import UserSettings
        from sqlalchemy import select
        
        result = await self.db_session.execute(select(UserSettings).filter(UserSettings.user_id == self.user_id))
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
        
        # Load summary prompt from assets
        prompts_dir = get_prompts_dir()
        summary_prompt_path = prompts_dir / "system" / "summary.md"
        
        if summary_prompt_path.exists():
            try:
                template = await asyncio.to_thread(summary_prompt_path.read_text, encoding='utf-8')
                
                # Format conversation for the prompt
                conv_text = ""
                for msg in conversation:
                    conv_text += f"\n{msg['role'].capitalize()}: {msg['content']}\n"
                
                summary_prompt = template.replace("{{conversation}}", conv_text)
            except Exception as e:
                print(f"⚠️ Failed to load summary prompt from {summary_prompt_path}: {e}")
                summary_prompt = self._get_default_summary_prompt(conversation)
        else:
            summary_prompt = self._get_default_summary_prompt(conversation)
        
        try:
            llm = await self._get_llm()
            messages = [Message(role="user", content=summary_prompt)]
            response = await llm.complete_async(messages, temperature=0.3)
            return response.content
        except Exception as e:
            return f"Summary generation failed: {str(e)}\n\nConversation had {len(conversation)} messages."

    def _get_default_summary_prompt(self, conversation: List[Dict[str, str]]) -> str:
        """Fallback hardcoded summary prompt"""
        prompt = """You are summarizing a conversation for context preservation. Extract:
1. **Decisions Made**: Key choices and conclusions
2. **Pending Issues**: Unresolved problems or open questions
3. **Key Facts**: Important information to preserve

Format as markdown with these sections. Be concise but comprehensive.

Conversation to summarize:
---
"""
        for msg in conversation:
            prompt += f"\n{msg['role'].capitalize()}: {msg['content']}\n"
        
        prompt += "\n---\nGenerate the summary now:"
        return prompt

    def export_history_to_markdown(self, conversation: List[Dict[str, str]]) -> str:
        """Format chat messages into a Markdown string for file export"""
        lines = ["# Chat Export", f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]
        for msg in conversation:
            role = msg.get("role", "unknown").capitalize()
            # We don't have timestamps for all items in the dict list usually, 
            # so we skip them or use placeholder if needed.
            lines.append(f"### {role}")
            lines.append(msg.get("content", ""))
            lines.append("")
        return "\n".join(lines)
    
    async def archive_context(self, force: bool = False, overlap_count: int = 10) -> Dict:
        """
        Archive current context asynchronously. 
        
        Args:
            force: Whether to force archiving even if conversation is empty.
            overlap_count: Number of latest messages to keep for context overlap.
        """
        conversation = await self.get_conversation_history()
        
        if not conversation and not force:
            return {
                "archived": False,
                "reason": "empty_conversation",
                "message": "Chat history is empty"
            }
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # 1. Export conversation to Markdown file
        history_md = self.export_history_to_markdown(conversation)
        archived_log_path = self.logs_archive_dir / f"chat_{timestamp}.md"
        await asyncio.to_thread(archived_log_path.write_text, history_md, encoding='utf-8')

        # 2. Generate summary
        summary = await self.generate_summary(conversation)
        summary_path = self.logs_archive_dir / f"archived_summary_{timestamp}.md"
        await asyncio.to_thread(summary_path.write_text, summary, encoding='utf-8')
        
        # 3. Rotate legacy file if exists
        if self.chat_log_path.exists():
            legacy_archived_path = self.logs_archive_dir / f"chat_{timestamp}.log"
            await asyncio.to_thread(shutil.move, str(self.chat_log_path), str(legacy_archived_path))
            await asyncio.to_thread(self.chat_log_path.touch)
        
        # 4. Save to database & Archive Session
        if self.db_session:
            await self._save_archive_record(summary_path, archived_log_path, len(conversation))
            
            # V5: Cleanup session-bound subscriptions before archiving the session
            from shared.database import ChatSession
            from sqlalchemy import select
            session_result = await self.db_session.execute(
                select(ChatSession).filter(ChatSession.project_id == self.project_id, ChatSession.is_archived == False)
            )
            active_session = session_result.scalars().first()
            if active_session:
                await self._cleanup_session_subscriptions(active_session.id)
            
            await self._mark_session_archived()
        
        # Extract overlapping messages
        overlap_msgs = conversation[-overlap_count:] if len(conversation) > overlap_count else conversation

        return {
            "archived": True,
            "timestamp": timestamp,
            "summary_path": str(summary_path),
            "log_path": str(archived_log_path),
            "message_count": len(conversation),
            "summary": summary,
            "overlap_messages": overlap_msgs,
            "message": f"✅ Archived {len(conversation)} messages. Context refreshed."
        }

    async def _mark_session_archived(self):
        """Mark the active session as archived in DB"""
        if not self.db_session:
            return
            
        from shared.database import Project, ChatSession
        from sqlalchemy import select, update
        
        try:
            # Find the project
            proj_result = await self.db_session.execute(select(Project).filter(
                Project.user_id == self.user_id,
                Project.id == self.project_id
            ))
            proj = proj_result.scalars().first()
            if not proj:
                return
            proj_id, proj_name = proj.id, proj.name

            # Mark all non-archived sessions for this project as archived
            # (Usually there's only one active session)
            await self.db_session.execute(
                update(ChatSession)
                .where(ChatSession.project_id == proj_id, ChatSession.is_archived == False)
                .values(is_archived=True, updated_at=datetime.utcnow())
            )
            await self.db_session.commit()
            print(f"[ContextManager] Session archived in DB for project {proj_name}")
        except Exception as e:
            print(f"[ContextManager] Failed to mark session archived: {e}")
            await self.db_session.rollback()
    
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
        if self.db_session:
            from shared.database import ArchivedContext
            from sqlalchemy import select
            
            try:
                result = await self.db_session.execute(
                    select(ArchivedContext).filter(
                        ArchivedContext.project_id == self.project_id,
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
        if not self.db_session:
            return
        
        from shared.database import ArchivedContext, Project
        from sqlalchemy import select
        
        try:
            # Try to find project
            result = await self.db_session.execute(
                select(Project).filter(
                    Project.user_id == self.user_id,
                    Project.id == self.project_id
                )
            )
            proj = result.scalars().first()
            if not proj:
                return
            
            new_record = ArchivedContext(
                user_id=self.user_id,
                project_id=proj.id,
                archived_at=datetime.utcnow(),
                summary_path=str(summary_path),
                log_path=str(log_path) if log_path else None,
                token_count=message_count
            )
            
            self.db_session.add(new_record)
            await self.db_session.commit()
            print(f"[ContextManager] Archived context record saved for project {proj.name}")
        except Exception as e:
            print(f"Failed to save archive record: {e}")
            await self.db_session.rollback()

    async def _cleanup_session_subscriptions(self, session_id: str):
        """Find and remove all subscriptions in the project's nodes bound to this session_id"""
        from shared.database import Node
        from sqlalchemy import select
        from sqlalchemy.orm.attributes import flag_modified

        try:
            # Fetch all nodes for this project
            stmt = select(Node).filter(Node.project_id == self.project_id)
            res = await self.db_session.execute(stmt)
            nodes = res.scalars().all()

            for node in nodes:
                meta = node.meta_payload or {}
                updated = False

                for key in ["trigger_patterns", "semantic_interests"]:
                    lst = meta.get(key, [])
                    if not lst: continue
                    
                    new_lst = []
                    for item in lst:
                        if isinstance(item, dict) and item.get("session_id") == session_id:
                            updated = True
                            continue
                        new_lst.append(item)
                    
                    if updated:
                        meta[key] = new_lst
                
                if updated:
                    node.meta_payload = meta
                    flag_modified(node, "meta_payload")
                    print(f"[ContextManager] Removed session-bound subscriptions from node {node.display_name}")

            await self.db_session.commit()
        except Exception as e:
            print(f"[ContextManager] Subscription cleanup failed: {e}")
            await self.db_session.rollback()
