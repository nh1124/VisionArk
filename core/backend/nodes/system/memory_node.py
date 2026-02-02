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
        print(f"📖 [MemoryNode] Fetching history for session: {session_id}")
        """Load conversation history from DB."""
        if not session_id:
            return []
            
        from models.database import AsyncSessionLocal, ChatMessage, ChatSubMessage, ToolUsage
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload, joinedload
        from models.message import Message, MessageRole, AttachedFile, ToolCall, SubMessage
        from datetime import datetime
        
        history = []
        
        async with AsyncSessionLocal() as db:
            from sqlalchemy import select
            from sqlalchemy.orm import load_only
            import json
            
            # 1. Fetch ChatMessages (Surgical)
            msg_stmt = (
                select(ChatMessage)
                .filter(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.asc())
                .options(load_only(ChatMessage.id, ChatMessage.role, ChatMessage.content, ChatMessage.meta_payload, ChatMessage.created_at))
            )
            msg_res = await db.execute(msg_stmt)
            db_messages = msg_res.scalars().all()
            if not db_messages:
                return []
            
            msg_ids = [m.id for m in db_messages]
            
            # 2. Fetch SubMessages (Surgical)
            sub_stmt = (
                select(ChatSubMessage)
                .filter(ChatSubMessage.message_id.in_(msg_ids))
                .order_by(ChatSubMessage.turn_index.asc())
                .options(load_only(ChatSubMessage.id, ChatSubMessage.message_id, ChatSubMessage.content, ChatSubMessage.meta_payload, ChatSubMessage.created_at))
            )
            sub_res = await db.execute(sub_stmt)
            db_subs = sub_res.scalars().all()
            
            sub_map = {}
            for sub in db_subs:
                if sub.message_id not in sub_map: sub_map[sub.message_id] = []
                sub_map[sub.message_id].append(sub)
                
            # 3. Fetch ToolUsages (Surgical)
            tu_stmt = (
                select(ToolUsage)
                .filter(ToolUsage.message_id.in_(msg_ids))
                .options(load_only(ToolUsage.id, ToolUsage.message_id, ToolUsage.sub_message_id, ToolUsage.name, ToolUsage.args, ToolUsage.result, ToolUsage.is_success, ToolUsage.meta_payload))
            )
            tu_res = await db.execute(tu_stmt)
            db_tus = tu_res.scalars().all()
            
            tu_map = {}
            for tu in db_tus:
                key = (tu.message_id, tu.sub_message_id)
                if key not in tu_map: tu_map[key] = []
                tu_map[key].append(tu)
            
            # 4. Assemble
            for db_msg in db_messages:
                try:
                    # Attached Files
                    meta = db_msg.meta_payload or {}
                    if isinstance(meta, str):
                        try:
                            meta = json.loads(meta)
                        except:
                            meta = {}
                    
                    files = []
                    if meta and isinstance(meta, dict) and "attached_files" in meta:
                        files = [AttachedFile.from_dict(f) for f in meta["attached_files"] if isinstance(f, dict)]
                    
                    # Role
                    role_val = db_msg.role.lower() if db_msg.role else "user"
                    try:
                        role_enum = MessageRole(role_val)
                    except ValueError:
                        role_enum = MessageRole.USER
                    
                    # SubMessages
                    sub_messages_list = []
                    for db_sub in sub_map.get(db_msg.id, []):
                        # Tools
                        tools = []
                        sm_tus = tu_map.get((db_msg.id, db_sub.id), [])
                        for tu in sm_tus:
                            tools.append(ToolCall(
                                name=tu.name,
                                args=tu.args or {},
                                result=tu.result,
                                is_success=bool(tu.is_success),
                                attachments=tu.meta_payload.get("attachments", []) if (tu.meta_payload and isinstance(tu.meta_payload, dict)) else []
                            ))
                        
                        sub_messages_list.append(SubMessage(
                            sub_id=db_sub.id,
                            content=db_sub.content or "",
                            tool_calls=tools,
                            meta_info=db_sub.meta_payload or {},
                            timestamp=db_sub.created_at or datetime.now()
                        ))
                    
                    history.append(Message(
                        role=role_enum,
                        content=db_msg.content or "",
                        timestamp=db_msg.created_at or datetime.now(),
                        attached_files=files,
                        sub_messages=sub_messages_list,
                        meta_info=meta.get("meta_info") if (meta and isinstance(meta, dict)) else None
                    ))
                except Exception as e:
                    print(f"[MemoryNode] Error assembling message {db_msg.id}: {e}")
                    
        return history
                    
        return history

    async def save_messages(self, session_id: str, messages: List[Message]):
        """Save a batch of messages to DB and ingest messages to KC."""
        from models.database import get_async_engine, get_async_session_maker, ChatMessage
        from uuid import uuid4
        from tools.utils import get_kc_service
        from models.message import MessageRole
        from models.database import ToolUsage, ChatSubMessage
        
        engine = get_async_engine()
        async_session = get_async_session_maker(engine)
        
        node_id = await self._get_node_id()
        
        async with async_session() as db:
            kc_svc = get_kc_service(self.user_id, db)
            print(f"💾 [MemoryNode] Saving {len(messages)} messages for session {session_id}")
            
            for msg in messages:
                files_meta = [f.to_dict() for f in msg.attached_files]
                
                meta_payload = {
                    "attached_files": files_meta,
                    "meta_info": msg.meta_info
                }
                
                message_id = str(uuid4())
                db_msg = ChatMessage(
                    id=message_id,
                    session_id=session_id,
                    role=msg.role.value,
                    content=msg.content or "",
                    meta_payload=meta_payload,
                    created_at=msg.timestamp
                )
                db.add(db_msg)
                
                
                # Save SubMessages
                if hasattr(msg, 'sub_messages') and msg.sub_messages:
                    num_subs = len(msg.sub_messages)
                    print(f"  - Message ({msg.role}): {num_subs} sub_messages found.")
                    for idx, sm in enumerate(msg.sub_messages):
                        sub_id = sm.sub_id or str(uuid4())
                        db_sub = ChatSubMessage(
                            id=sub_id,
                            message_id=message_id,
                            turn_index=idx,
                            content=sm.content,
                            meta_payload=sm.meta_info,
                            created_at=sm.timestamp
                        )
                        db.add(db_sub)
                        
                        # Save ToolCalls within SubMessage
                        if sm.tool_calls:
                            for tc in sm.tool_calls:
                                db_tu = ToolUsage(
                                    id=str(uuid4()),
                                    message_id=message_id,
                                    sub_message_id=sub_id,
                                    name=tc.name,
                                    args=tc.args,
                                    result=tc.result,
                                    is_success=tc.is_success,
                                    meta_payload={"attachments": tc.attachments} if tc.attachments else {}
                                )
                                print(f"    * Saved ToolCall: {tc.name} (with {len(tc.attachments) if tc.attachments else 0} attachments)")
                                db.add(db_tu)
                        print(f"  - Saved SubMessage {idx}: {sm.content[:50] if sm.content else ''}... with {len(sm.tool_calls) if sm.tool_calls else 0} tool calls.")
                
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
