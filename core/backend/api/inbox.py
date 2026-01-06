"""
Inbox API endpoints
Message fetching, processing, and triage
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, Dict

from models.database import InboxQueue, get_async_db
from services.inbox_handler import InboxHandler
from services.auth import resolve_identity, Identity

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
async def get_pending_messages(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Fetch all unprocessed inbox messages for this user"""
    handler = InboxHandler(db, user_id=identity.user_id)
    messages = await handler.get_pending_messages()
    
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
async def push_message(
    msg: PushMessage,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Push a <meta-action> message from Spoke to Hub inbox
    Internal endpoint used by Spoke agents
    """
    handler = InboxHandler(db, user_id=identity.user_id)
    queue_id = await handler.push_to_inbox(msg.source_spoke, msg.meta_action_xml)
    
    if queue_id is None:
        raise HTTPException(status_code=400, detail="Failed to parse meta-action XML")
    
    return {"queue_id": queue_id, "message": "Message queued successfully"}


@router.post("/process")
async def process_message(
    msg: ProcessMessage,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Process an inbox message (accept/reject/edit)"""
    from datetime import datetime
    
    # Get the message
    result = await db.execute(select(InboxQueue).filter(
        InboxQueue.id == msg.message_id,
        InboxQueue.user_id == identity.user_id
    ))
    inbox_msg = result.scalars().first()
    
    if not inbox_msg:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Update message status directly (handler logic is obsolete)
    inbox_msg.is_processed = True
    inbox_msg.processed_at = datetime.utcnow()
    
    if msg.action == "reject":
        inbox_msg.error_log = "Rejected by user"
    
    await db.commit()
    
    # If accepted, automatically notify Hub with full payload
    if msg.action == "accept":
        try:
            from api.agents import get_hub_agent
            import json
            
            # Format the message for Hub with technical details
            spoke = inbox_msg.source_spoke
            payload = inbox_msg.payload
            
            summary = payload.get('summary', 'No summary')
            request = payload.get('request', '')
            lbs_updates = payload.get('lbs_updates', [])
            
            notification = (
                f"📢 **Inbox Update Received: {spoke}**\n"
                f"I have accepted an update from the Spoke: **{spoke}**.\n\n"
                f"**Summary:** {summary}\n"
            )
            
            if request:
                notification += f"**Request:** {request}\n"
            
            if lbs_updates:
                notification += "\n**LBS Updates Recommended by Spoke:**\n"
                for i, update in enumerate(lbs_updates, 1):
                    action = update.get('action', 'update')
                    name = update.get('name', 'Unnamed Task')
                    load = update.get('load_score', '?')
                    due = update.get('due_date', 'N/A')
                    notification += f"{i}. {action.upper()} Task '{name}' (Load: {load}, Due: {due})\n"
                
                notification += "\n**Technical Payload (for your tools):**\n"
                notification += f"```json\n{json.dumps(payload, indent=2)}\n```\n"
            
            notification += (
                "\n---\n"
                "Please analyze this update and use your tools (like `create_task`, `update_task_details`, or `complete_lbs_task`) to reflect these changes in our LBS system as you see fit. "
                "Provide a brief assessment of how this affects our project priority."
            )
            
            # Send to Hub and get response
            hub = await get_hub_agent(identity.user_id, db)
            hub_response = await hub.chat(notification) # Use chat to allow tool calls
            
            # Hub's return from chat is (response_text, tool_calls)
            response_text = hub_response[0] if isinstance(hub_response, tuple) else hub_response
            
            return {
                "message": f"Message {msg.action}ed successfully",
                "hub_notified": True,
                "hub_response": response_text
            }
        except Exception as e:
            print(f"Failed to notify Hub: {e}")
            import traceback
            traceback.print_exc()
            return {"message": f"Message {msg.action}ed successfully", "hub_notified": False}
    
    return {"message": f"Message {msg.action}ed successfully"}


@router.post("/accept-all")
async def accept_all_messages(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Accept all pending inbox messages at once"""
    from datetime import datetime
    
    result = await db.execute(select(InboxQueue).filter(
        InboxQueue.user_id == identity.user_id,
        InboxQueue.is_processed == False
    ))
    pending = result.scalars().all()
    
    if not pending:
        return {"message": "No pending messages to accept", "count": 0}
    
    accepted_messages = []
    
    for msg in pending:
        msg.is_processed = True
        msg.processed_at = datetime.utcnow()
        accepted_messages.append({
            "spoke": msg.source_spoke,
            "summary": msg.payload.get('summary', 'No summary'),
            "request": msg.payload.get('request', ''),
            "payload": msg.payload
        })
    
    await db.commit()
    
    # Automatically notify Hub about all accepted messages
    hub_response = None
    if accepted_messages:
        try:
            from api.agents import get_hub_agent
            import json
            
            # Format notification for Hub
            notification = (
                f"📢 **Batch Inbox Processing Complete**\n"
                f"I have just accepted **{len(accepted_messages)}** pending updates from multiple Spokes.\n\n"
                f"**Consolidated Summary of Updates:**\n"
            )
            for i, msg_data in enumerate(accepted_messages, 1):
                notification += f"\n{i}. **[{msg_data['spoke']}]** {msg_data['summary']}"
                if msg_data['request']:
                    notification += f" (Request: {msg_data['request']})"
            
            notification += "\n\n**Technical Details (for your reference):**\n"
            notification += "```json\n" + json.dumps([m['payload'] for m in accepted_messages], indent=2) + "\n```\n"

            notification += (
                "\n\n---\n"
                "Please perform a global re-evaluation of our status based on these combined updates. "
                "Use your tools to adjust the LBS schedule or create new tasks as necessary."
            )
            
            # Send to Hub and get response
            hub = await get_hub_agent(identity.user_id, db)
            hub_chat_res = await hub.chat(notification)
            hub_response = hub_chat_res[0] if isinstance(hub_chat_res, tuple) else hub_chat_res
            
        except Exception as e:
            print(f"Failed to notify Hub: {e}")
    
    return {
        "message": f"✅ Accepted {len(accepted_messages)} messages",
        "accepted": len(accepted_messages),
        "hub_notified": hub_response is not None,
        "hub_response": hub_response
    }


@router.get("/count")
async def get_unread_count(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get count of unread inbox messages for this user"""
    from sqlalchemy import func
    result = await db.execute(select(func.count()).select_from(InboxQueue).filter(
        InboxQueue.user_id == identity.user_id,
        InboxQueue.is_processed == False
    ))
    count = result.scalar()
    return {"unread_count": count}
