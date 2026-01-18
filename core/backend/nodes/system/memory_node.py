from typing import Any, Dict, Optional, List
from nodes.base_node import BaseNode
from utils.paths import get_user_root_dir
from models.message import Message
import os

class MemoryNode(BaseNode):
    """
    The Librarian.
    Responsible for fetching context (Profile, Plan, KC) and saving logs.
    """
    
    def __init__(self, context: Dict[str, Any]):
        super().__init__(context)
        self.user_dir = get_user_root_dir(self.user_id)
        
    async def pre_process(self):
        pass

    async def get_history(self, session_id: str) -> List[Message]:
        """Load conversation history from DB."""
        if not session_id:
            return []
            
        from models.database import get_async_engine, get_async_session_maker, ChatMessage
        from sqlalchemy import select
        from models.message import Message, MessageRole, AttachedFile
        from datetime import datetime
        
        history = []
        engine = get_async_engine()
        async_session = get_async_session_maker(engine)
        
        async with async_session() as db:
            result = await db.execute(
                select(ChatMessage).filter(
                    ChatMessage.session_id == session_id
                ).order_by(ChatMessage.created_at.asc())
            )
            db_messages = result.scalars().all()
            
            for db_msg in db_messages:
                try:
                    files = []
                    if db_msg.meta_payload and isinstance(db_msg.meta_payload, dict) and "attached_files" in db_msg.meta_payload:
                        files = [AttachedFile.from_dict(f) for f in db_msg.meta_payload["attached_files"] if isinstance(f, dict)]
                    
                    role_val = db_msg.role.lower() if db_msg.role else "user"
                    try:
                        role_enum = MessageRole(role_val)
                    except ValueError:
                        role_enum = MessageRole.USER

                    msg = Message(
                        role=role_enum,
                        content=db_msg.content or "",
                        timestamp=db_msg.created_at or datetime.now(),
                        attached_files=files,
                        meta_info=db_msg.meta_payload.get("meta_info") if (db_msg.meta_payload and isinstance(db_msg.meta_payload, dict)) else None
                    )
                    history.append(msg)
                except Exception as e:
                    print(f"[MemoryNode] Error loading message {db_msg.id}: {e}")
                    
        return history

    async def save_messages(self, session_id: str, messages: List[Message]):
        """Save a batch of messages to DB."""
        from models.database import get_async_engine, get_async_session_maker, ChatMessage
        from uuid import uuid4
        
        engine = get_async_engine()
        async_session = get_async_session_maker(engine)
        
        async with async_session() as db:
            for msg in messages:
                files_meta = [f.to_dict() for f in msg.attached_files]
                
                # Build meta_payload with tool_calls at root level for frontend
                meta_payload = {
                    "attached_files": files_meta,
                    "meta_info": msg.meta_info
                }
                
                # Also copy tool_calls to root level for frontend compatibility
                if msg.meta_info and isinstance(msg.meta_info, dict) and "tool_calls" in msg.meta_info:
                    meta_payload["tool_calls"] = msg.meta_info["tool_calls"]
                
                db_msg = ChatMessage(
                    id=str(uuid4()),
                    session_id=session_id,
                    role=msg.role.value,
                    content=msg.content or "",
                    meta_payload=meta_payload,
                    created_at=msg.timestamp
                )
                db.add(db_msg)
            await db.commit()

    async def get_or_create_session(self, node_id: str, user_id: str) -> str:
        """Get active session or create new one."""
        from models.database import get_async_engine, get_async_session_maker, ChatSession
        from sqlalchemy import select
        from uuid import uuid4
        
        engine = get_async_engine()
        async_session = get_async_session_maker(engine)
        
        async with async_session() as db:
            # Check for active session
            # Note: We might want slightly different logic for "nodes" vs "agents"
            # For now, replicate Agent logic: find latest unarchived session for this node
            result = await db.execute(
                select(ChatSession).filter(
                    ChatSession.node_id == node_id,
                    ChatSession.is_archived == False
                ).order_by(ChatSession.created_at.desc())
            )
            session = result.scalars().first()
            
            if not session:
                session_id = str(uuid4())
                new_session = ChatSession(
                    id=session_id,
                    node_id=node_id,
                    title="New Node Session",
                    is_archived=False
                )
                db.add(new_session)
                await db.commit()
                return session_id
            
            return session.id

    def _load_user_profile(self) -> str:
        try:
            profile_path = self.user_dir / "profile.md"
            if profile_path.exists():
                return profile_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"[MemoryNode] Failed to load profile: {e}")
        return ""

    def _load_plan(self, project_id: Optional[str]) -> str:
        # TODO: Define where PLAN.md lives. Assuming root of user dir or project dir.
        # For now, look for PLAN.md in user dir
        try:
            plan_path = self.user_dir / "PLAN.md"
            if plan_path.exists():
                return plan_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"[MemoryNode] Failed to load plan: {e}")
        return ""

    async def get_context(self) -> Dict[str, Any]:
        """Load full context (Profile, Plan, etc.)"""
        # Load Profile (user-level)
        profile_text = self._load_user_profile()
        
        # Load Plan (project-level ideally, or user level for now)
        # Assuming project_id available in context if needed, but for now user global.
        plan_text = self._load_plan(None)
        
        return {
            "profile": profile_text,
            "plan": plan_text
        }

    async def process(self, message: str) -> Any:
        # MemoryNode is mostly passive (called by others)
        return None

    async def post_process(self, result: Any):
        pass
