from datetime import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from models.database import ChatMessage

class CallbackService:
    """Service to post background updates and notifications to chat sessions."""
    
    @staticmethod
    async def append_message(
        db_session: AsyncSession, 
        session_id: str, 
        content: str, 
        role: str = "assistant",
        meta_payload: dict = None
    ):
        """Append a message to a specific chat session and broadcast via Redis."""
        import json
        from queue_system.manager import QueueManager
        
        msg_id = str(uuid.uuid4())
        message = ChatMessage(
            id=msg_id,
            session_id=session_id,
            role=role,
            content=content,
            meta_payload=meta_payload or {},
            created_at=datetime.utcnow()
        )
        db_session.add(message)
        await db_session.commit()

        # Redis Broadcast for Real-time UI
        try:
            queue_manager = QueueManager()
            payload = {
                "type": "new_message",
                "session_id": session_id,
                "data": {
                    "id": msg_id,
                    "role": role,
                    "content": content,
                    "meta_payload": meta_payload or {},
                    "created_at": message.created_at.isoformat()
                }
            }
            queue_manager.client.publish(f"chat:{session_id}", json.dumps(payload))
            print(f"[CallbackService] Broadcasted message to chat:{session_id}")
        except Exception as be:
            print(f"⚠️ [CallbackService] Redis broadcast failed: {be}")
            
        return msg_id

    @staticmethod
    async def notify_node_completion(
        db_session: AsyncSession,
        session_id: str,
        node_display_name: str,
        result: any,
        task_id: str = None
    ):
        """
        Formatted notification for node work completion.
        Supports both string summaries and full Message objects (preserving thinking steps).
        """
        from models.message import Message
        from models.database import ChatSubMessage, ToolUsage

        content = ""
        sub_messages = []
        
        if isinstance(result, Message):
            content = result.content or ""
            sub_messages = result.sub_messages
        else:
            content = str(result)

        display_content = f"🤖 **{node_display_name}** has completed background work:\n\n{content}"
        meta_payload = {
            "type": "node_callback",
            "node_name": node_display_name,
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        # 1. Save and broadcast main message
        message_id = await CallbackService.append_message(db_session, session_id, display_content, meta_payload=meta_payload)

        # 2. Save Sub-messages (Thinking Steps) if present
        if sub_messages:
            for idx, sm in enumerate(sub_messages):
                sub_id = sm.sub_id or str(uuid.uuid4())
                db_sub = ChatSubMessage(
                    id=sub_id,
                    message_id=message_id,
                    turn_index=idx,
                    content=sm.content,
                    meta_payload=sm.meta_info,
                    created_at=sm.timestamp
                )
                db_session.add(db_sub)
                
                # Save ToolCalls within SubMessage
                if sm.tool_calls:
                    for tc in sm.tool_calls:
                        db_tu = ToolUsage(
                            id=str(uuid.uuid4()),
                            message_id=message_id,
                            sub_message_id=sub_id,
                            name=tc.name,
                            args=tc.args,
                            result=tc.result,
                            is_success=tc.is_success,
                            meta_payload={"attachments": tc.attachments} if tc.attachments else {}
                        )
                        db_session.add(db_tu)
            
            await db_session.commit()
            print(f"[CallbackService] Saved {len(sub_messages)} thinking steps for background task.")

        return message_id

    @staticmethod
    async def notify_node_failure(
        db_session: AsyncSession,
        session_id: str,
        node_display_name: str,
        error_message: str,
        task_id: str = None
    ):
        """Formatted notification for node work failure."""
        content = f"❌ **{node_display_name}** failed to complete background work:\n\n{error_message}"
        meta_payload = {
            "type": "node_callback_failure",
            "node_name": node_display_name,
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        return await CallbackService.append_message(db_session, session_id, content, meta_payload=meta_payload)
