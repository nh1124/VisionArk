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
        
    async def on_enter(self):
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
        """Save a batch of messages to DB and ingest messages to KC."""
        from models.database import get_async_engine, get_async_session_maker, ChatMessage
        from uuid import uuid4
        from tools.utils import get_kc_service
        from models.message import MessageRole
        
        engine = get_async_engine()
        async_session = get_async_session_maker(engine)
        
        node_id = await self._get_node_id()
        
        async with async_session() as db:
            kc_svc = get_kc_service(self.user_id, db)
            
            for msg in messages:
                files_meta = [f.to_dict() for f in msg.attached_files]
                
                meta_payload = {
                    "attached_files": files_meta,
                    "meta_info": msg.meta_info
                }
                
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
                
                # Ingest Messages to Knowledge Core
                if msg.content:
                    try:
                        # Ingest both USER and ASSISTANT messages
                        # User stable node_id as agent_id
                        kc_role = "user" if msg.role == MessageRole.USER else "assistant"
                        
                        await kc_svc.ingest_message(
                            text=msg.content,
                            role=kc_role,
                            scope="global",
                            agent_id=node_id
                        )
                    except Exception as e:
                        print(f"[MemoryNode] Ingestion failed: {e}")

            await db.commit()

    async def get_or_create_session(self, project_id: str, user_id: str) -> str:
        """Get active session or create new one."""
        from models.database import AsyncSessionLocal, ChatSession
        from sqlalchemy import select
        from uuid import uuid4
        
        async with AsyncSessionLocal() as db:
            # Check for active session
            result = await db.execute(
                select(ChatSession).filter(
                    ChatSession.project_id == project_id,
                    ChatSession.is_archived == False
                ).order_by(ChatSession.created_at.desc())
            )
            session = result.scalars().first()
            
            if not session:
                session_id = str(uuid4())
                new_session = ChatSession(
                    id=session_id,
                    project_id=project_id,
                    title="New Node Session",
                    is_archived=False
                )
                db.add(new_session)
                await db.commit()
                return session_id
            
            return session.id

    async def _get_node_id(self) -> str:
        """Resolve node_id from context or database."""
        # 1. Try context first (might be set by ProjectNode)
        node_id = self.context.get("node_id")
        if node_id:
            return node_id
            
        project_id = self.context.get("project_id")
        if not project_id:
            return None
            
        # 2. Query database for the orchestrator (PROJECT type) node
        from models.database import AsyncSessionLocal, Node
        from sqlalchemy import select
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Node).filter(
                    Node.project_id == project_id,
                    Node.node_type == "PROJECT"
                )
            )
            node = result.scalars().first()
            if node:
                # Cache in context for subsequent calls
                self.context["node_id"] = node.id
                return node.id
                
        # 3. Fallback to project_id (e.g. for user-less or legacy sessions)
        return project_id
            
    def _load_user_profile(self) -> str:
        try:
            profile_path = self.user_dir / "profile.md"
            if profile_path.exists():
                return profile_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"[MemoryNode] Failed to load profile: {e}")
        return ""

    def _load_plan(self, project_id: Optional[str]) -> str:
        """Load PLAN.md from project directory or user root."""
        from utils.paths import get_project_dir
        
        # 1. Try project-specific plan
        if project_id:
            try:
                project_dir = get_project_dir(self.user_id, project_id)
                plan_path = project_dir / "PLAN.md"
                if plan_path.exists():
                    print(f"[MemoryNode] Loading plan from project: {project_id}")
                    return plan_path.read_text(encoding='utf-8')
            except Exception as e:
                print(f"[MemoryNode] Failed to load project plan: {e}")

        # 2. Fallback to user root plan
        try:
            plan_path = self.user_dir / "PLAN.md"
            if plan_path.exists():
                print(f"[MemoryNode] Loading global plan from user root")
                return plan_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"[MemoryNode] Failed to load root plan: {e}")
        return ""

    async def get_knowledge_context(self, query: str) -> str:
        """Retrieve relevant context from Knowledge Core."""
        from models.database import AsyncSessionLocal
        from tools.utils import get_kc_service
        
        node_id = await self._get_node_id()
        
        async with AsyncSessionLocal() as db:
            kc_svc = get_kc_service(self.user_id, db)
            try:
                # Get context for the query, filtered by node_id (agent_id)
                kc_result = await kc_svc.get_context(
                    query=query,
                    agent_id=node_id
                )
                if kc_result:
                    print(f"[MemoryNode] Successfully retrieved knowledge context for: {query[:50]}... (agent_id={node_id})")
                    return kc_result
                return ""
            except Exception as e:
                print(f"[MemoryNode] KC Retrieval error: {e}")
                return ""

    async def get_context(self) -> Dict[str, Any]:
        """Load full context (Profile, Plan, KC, etc.)"""
        # Load Profile (user-level)
        profile_text = self._load_user_profile()
        
        # Load Plan (project-level or global)
        project_id = self.context.get("project_id")
        plan_text = self._load_plan(project_id)
        
        return {
            "profile": profile_text,
            "plan": plan_text
        }

    async def on_execute(self, message: str) -> Any:
        # MemoryNode is mostly passive (called by others)
        return None

    async def on_exit(self, result: Any):
        pass
