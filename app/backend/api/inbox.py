"""
Inbox API endpoints
Message fetching, processing, and triage
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, Dict

from models.database import InboxQueue
from services.inbox_handler import InboxHandler
from services.auth import resolve_identity, Identity, get_db

router = APIRouter(prefix="/api/inbox", tags=["Inbox"])


# Pydantic models
class PushMessage(BaseModel):
    source_spoke: str
    meta_action_xml: str


class ProcessMessage(BaseModel):
    message_id: int
    action: str  # accept, reject, edit_accept
    user_edits: Optional[Dict] = None


# Endpoints
@router.get("/pending")
def get_pending_messages(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Fetch all unprocessed inbox messages"""
    handler = InboxHandler(db)
    messages = handler.get_pending_messages()
    
    return [
        {
            "id": msg.id,
            "source_spoke": msg.source_spoke,
            "message_type": msg.message_type,
            "payload": msg.payload,
            "received_at": msg.received_at.isoformat(),
            "is_processed": msg.is_processed
        }
        for msg in messages
    ]


@router.post("/push")
def push_message(
    msg: PushMessage,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Push a <meta-action> message from Spoke to Hub inbox
    Internal endpoint used by Spoke agents
    """
    handler = InboxHandler(db)
    queue_id = handler.push_to_inbox(msg.source_spoke, msg.meta_action_xml)
    
    if queue_id is None:
        raise HTTPException(status_code=400, detail="Failed to parse meta-action XML")
    
    return {"queue_id": queue_id, "message": "Message queued successfully"}


@router.post("/process")
def process_message(
    msg: ProcessMessage,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Process an inbox message (accept/reject/edit)"""
    handler = InboxHandler(db)
    
    # Get the message before processing to read its content
    from models.database import InboxQueue
    inbox_msg = db.query(InboxQueue).filter(InboxQueue.id == msg.message_id).first()
    
    if not inbox_msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    success = handler.process_message(msg.message_id, msg.action, msg.user_edits)
    
    if not success:
        raise HTTPException(status_code=404, detail="Processing failed")
    
    # If accepted, automatically notify Hub
    if msg.action == "accept":
        try:
            from api.agents import get_hub_agent
            
            # Format the message for Hub
            spoke = inbox_msg.source_spoke
            summary = inbox_msg.payload.get('summary', 'No summary')
            request = inbox_msg.payload.get('request', '')
            
            notification = f"📬 New message from {spoke}:\n{summary}"
            if request:
                notification += f"\n*Request:* {request}"
            
            # Send to Hub and get response
            hub = get_hub_agent(db)
            hub_response = hub.chat_with_context(notification)
            
            return {
                "message": f"Message {msg.action}ed successfully",
                "hub_notified": True,
                "hub_response": hub_response
            }
        except Exception as e:
            print(f"Failed to notify Hub: {e}")
            return {"message": f"Message {msg.action}ed successfully", "hub_notified": False}
    
    return {"message": f"Message {msg.action}ed successfully"}


@router.post("/accept-all")
def accept_all_messages(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Accept all pending inbox messages at once"""
    handler = InboxHandler(db)
    pending = handler.get_pending_messages()
    
    if not pending:
        return {"message": "No pending messages to accept", "count": 0}
    
    accepted_count = 0
    failed_count = 0
    accepted_messages = []
    
    for msg in pending:
        success = handler.process_message(msg.id, "accept")
        if success:
            accepted_count += 1
            accepted_messages.append({
                "spoke": msg.source_spoke,
                "summary": msg.payload.get('summary', 'No summary'),
                "request": msg.payload.get('request', '')
            })
        else:
            failed_count += 1
    
    # Automatically notify Hub about all accepted messages
    hub_response = None
    if accepted_count > 0:
        try:
            from api.agents import get_hub_agent
            
            # Format notification for Hub
            notification = f"📬 Accepted {accepted_count} messages from Spokes:\n\n"
            for msg_data in accepted_messages:
                notification += f"**From {msg_data['spoke']}:**\n{msg_data['summary']}\n"
                if msg_data['request']:
                    notification += f"*Request:* {msg_data['request']}\n"
                notification += "\n"
            
            # Send to Hub and get response
            hub = get_hub_agent(db)
            hub_response = hub.chat_with_context(notification)
            
        except Exception as e:
            print(f"Failed to notify Hub: {e}")
    
    return {
        "message": f"✅ Accepted {accepted_count} messages" + (f", {failed_count} failed" if failed_count > 0 else ""),
        "accepted": accepted_count,
        "failed": failed_count,
        "hub_notified": hub_response is not None,
        "hub_response": hub_response
    }


@router.get("/count")
def get_unread_count(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get count of unread inbox messages"""
    count = db.query(InboxQueue).filter(InboxQueue.is_processed == False).count()
    return {"unread_count": count}
