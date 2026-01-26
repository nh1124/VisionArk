import hmac
import hashlib
import base64
import json
from fastapi import APIRouter, Request, Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import get_async_db, ExternalIdentity, ServiceRegistry, User, Project, Node
from .client import LineClient
from uuid import uuid4

router = APIRouter()

ROUTER_PREFIX = "/line"
ROUTER_TAGS = ["LINE"]

async def verify_signature(request: Request, channel_secret: str, signature: str = Header(None, alias="X-Line-Signature")):
    """Verify LINE Messaging API signature."""
    if not signature or not channel_secret:
        raise HTTPException(status_code=401, detail="Missing signature or channel secret")
        
    body = await request.body()
    hash_obj = hmac.new(channel_secret.encode('utf-8'), body, hashlib.sha256)
    digest = base64.b64encode(hash_obj.digest()).decode('utf-8')
    
    if not hmac.compare_digest(digest, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

@router.post("/{reg_user_id}/webhook")
async def line_webhook(
    reg_user_id: str,
    request: Request,
    x_line_signature: str = Header(None, alias="X-Line-Signature"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Entry point for LINE Messaging API webhooks.
    reg_user_id: The ID of the VisionArk user who owns this LINE bot integration.
    """
    # 1. Fetch the service registry to get the channel secret
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == reg_user_id,
        ServiceRegistry.service_name == "line"
    ))
    service = result.scalars().first()
    if not service or not service.is_active:
        raise HTTPException(status_code=404, detail="LINE integration not found or inactive for this user")

    channel_secret = service.config.get("channel_secret")
    if not channel_secret:
        raise HTTPException(status_code=500, detail="Channel secret not configured")

    # 2. Verify Signature
    body = await request.body()
    hash_obj = hmac.new(channel_secret.encode('utf-8'), body, hashlib.sha256)
    digest = base64.b64encode(hash_obj.digest()).decode('utf-8')
    
    if not hmac.compare_digest(digest, x_line_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 3. Process Events
    payload = json.loads(body.decode('utf-8'))
    events = payload.get("events", [])
    
    from queue_system.manager import QueueManager
    queue = QueueManager()

    for event in events:
        source = event.get("source", {})
        line_user_id = source.get("userId")
        
        if not line_user_id:
            continue
            
        # Identity Mapping: Who is sending this?
        print(f"[debug] Checking identity for line_user_id: {line_user_id}", flush=True)
        id_result = await db.execute(select(ExternalIdentity).filter(
            ExternalIdentity.issuer == "line",
            ExternalIdentity.subject == line_user_id
        ))
        identity = id_result.scalars().first()
        print(f"[debug] Identity lookup result: {identity}", flush=True)
        
        if not identity:
            # Auto-link the sender to the bot owner for now (simple setup)
            # In a more complex setup, we'd verify this link.
            print(f"[debug] Identity not found. Creating new identity for {reg_user_id}", flush=True)
            identity = ExternalIdentity(
                user_id=reg_user_id,
                issuer="line",
                subject=line_user_id
            )
            db.add(identity)
            try:
                await db.commit()
                print(f"[LINE Webhook] Auto-linked new identity: {line_user_id} -> {reg_user_id}", flush=True)
            except Exception as e:
                print(f"[ERROR] Failed to commit identity: {e}", flush=True)
                await db.rollback()
        
        actual_user_id = identity.user_id
        
        if event.get("type") == "message":
            msg_text = event.get("message", {}).get("text")
            reply_token = event.get("replyToken")
            
            if msg_text:
                print(f"[LINE Webhook] Received from {actual_user_id}: {msg_text}")
                
                # Check for dedicated project
                project_id = identity.project_id
                
                if not project_id:
                    print(f"[LINE Webhook] Creating dedicated project for {line_user_id}")
                    try:
                        # 1. Get Profile for naming (with fallback)
                        display_name = f"LINE User {line_user_id[:8]}"
                        try:
                            line_client = LineClient(service.api_key)
                            profile = await line_client.get_profile(line_user_id)
                            if profile.get("displayName"):
                                display_name = profile.get("displayName")
                        except Exception as pe:
                            print(f"[LINE Webhook] Warning: Could not fetch profile for {line_user_id}: {pe}")
                        
                        # 2. Create Project
                        project_id = str(uuid4())
                        new_project = Project(
                            id=project_id,
                            user_id=reg_user_id, # The VisionArk owner
                            name=f"LINE: {display_name}",
                            status="active"
                        )
                        db.add(new_project)
                        
                        # 3. Create Orchestrator Node
                        new_node = Node(
                            id=str(uuid4()),
                            project_id=project_id,
                            node_type="PROJECT",
                            display_name="Orchestrator",
                            system_prompt=f"You are a specialized AI assistant for {display_name} via LINE. Help them manage their tasks and information.",
                            status="active"
                        )
                        db.add(new_node)
                        
                        # Flush to ensure Project exists for the foreign key constraint
                        await db.flush()
                        
                        # 4. Link Identity
                        identity.project_id = project_id
                        await db.commit()
                        print(f"[LINE Webhook] Created project {project_id} for LINE user {display_name}")
                    except Exception as e:
                        print(f"[ERROR] Project creation failed: {e}")
                        await db.rollback()
                        # Fallback for this message: project_id remains None, 
                        # but ProjectNode will now fallback to latest project.
                        project_id = None

                # Enqueue task for Worker
                queue.enqueue(
                    user_id=actual_user_id,
                    message=msg_text,
                    context={
                        "project_id": project_id,
                        "user_id": actual_user_id,
                        "external_reply_channel": "line",
                        "line_reply_token": reply_token,
                        "line_user_id": line_user_id,
                        "registry_user_id": reg_user_id # Who owns the bot
                    }
                )
                
    return {"status": "ok"}
