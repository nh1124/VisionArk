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
        """Append a message to a specific chat session."""
        message = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            role=role,
            content=content,
            meta_payload=meta_payload or {},
            created_at=datetime.utcnow()
        )
        db_session.add(message)
        await db_session.commit()
        return message.id

    @staticmethod
    async def notify_node_completion(
        db_session: AsyncSession,
        session_id: str,
        node_display_name: str,
        result_summary: str,
        task_id: str = None
    ):
        """Formatted notification for node work completion."""
        content = f"🤖 **{node_display_name}** has completed background work:\n\n{result_summary}"
        meta_payload = {
            "type": "node_callback",
            "node_name": node_display_name,
            "task_id": task_id,
            "timestamp": datetime.utcnow().isoformat()
        }
        return await CallbackService.append_message(db_session, session_id, content, meta_payload=meta_payload)

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
