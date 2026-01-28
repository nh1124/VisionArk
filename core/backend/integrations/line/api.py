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
import secrets
import os
from datetime import datetime, timedelta
from .models import LineLinkingToken

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

@router.post("/link")
async def link_line_account(
    token: str,
    user_id: str,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Complete the account linking process.
    token: The unique linking token sent to LINE.
    user_id: The VisionArk user ID to link with.
    """
    # 1. Search for the token in the dedicated integration table
    stmt = select(LineLinkingToken).filter(
        LineLinkingToken.token == token,
        LineLinkingToken.expires_at > datetime.utcnow()
    )
    result = await db.execute(stmt)
    token_obj = result.scalars().first()

    if not token_obj:
        raise HTTPException(status_code=404, detail="Invalid or expired linking token")

    line_user_id = token_obj.line_user_id

    # 2. Check if identity already exists
    id_result = await db.execute(select(ExternalIdentity).filter(
        ExternalIdentity.issuer == "line",
        ExternalIdentity.subject == line_user_id
    ))
    existing_id = id_result.scalars().first()
    
    if existing_id:
        existing_id.user_id = user_id
    else:
        new_identity = ExternalIdentity(
            user_id=user_id,
            issuer="line",
            subject=line_user_id
        )
        db.add(new_identity)
    
    # 3. Cleanup token and Commit
    await db.delete(token_obj)
    await db.commit()
    
    return {"status": "success", "message": "LINE account linked successfully"}

@router.post("/webhook")
async def shared_line_webhook(
    request: Request,
    signature: str = Header(..., alias="X-Line-Signature"),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Universal LINE webhook for the Shared App model.
    Uses credentials from environment variables.
    """
    channel_secret = os.getenv("LINE_CHANNEL_SECRET", "").strip()
    channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    
    if not channel_secret or not channel_access_token:
        print("[ERROR] Shared LINE credentials missing in .env", flush=True)
        raise HTTPException(status_code=500, detail="LINE Shared App not configured")

    body = await request.body()
    body_str = body.decode("utf-8")
    
    # 1. Verify Signature
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    calc_signature = base64.b64encode(digest).decode("utf-8")
    
    if not hmac.compare_digest(calc_signature, signature):
        print(f"[LINE Webhook] Signature mismatch!", flush=True)
        print(f"  Received: {signature}", flush=True)
        print(f"  Calculated: {calc_signature}", flush=True)
        raise HTTPException(status_code=401, detail="Invalid signature")

    print("[LINE Webhook] Signature verified successfully", flush=True)

    # 2. Process Events
    data = json.loads(body_str)
    for event in data.get("events", []):
        if event.get("type") != "message":
            continue
            
        line_user_id = event["source"]["userId"]
        message_text = event["message"].get("text", "")
        reply_token = event.get("replyToken")
        
        # 3. Identity Lookup
        id_result = await db.execute(select(ExternalIdentity).filter(
            ExternalIdentity.issuer == "line",
            ExternalIdentity.subject == line_user_id
        ))
        identity = id_result.scalars().first()
        
        if not identity:
            # --- Secure Linking Flow ---
            token_str = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(minutes=15)
            
            # Store link token in the dedicated integration table
            new_token = LineLinkingToken(
                token=token_str,
                line_user_id=line_user_id,
                expires_at=expires_at
            )
            db.add(new_token)
            await db.commit()
            
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            link_url = f"{frontend_url}/integrations/line/link?token={token_str}"
            
            try:
                line_client = LineClient(channel_access_token)
                invitation_text = (
                    "Welcome to VisionArk Shared Bot! 🚀\n\n"
                    "Please link your account to start interacting:\n\n"
                    f"{link_url}"
                )
                await line_client.push_message(line_user_id, invitation_text)
            except Exception as se:
                print(f"[ERROR] Invitation failed: {se}", flush=True)
            continue

        # 4. Success: Dispatch message
        actual_user_id = identity.user_id
        print(f"[LINE Shared] Dispatching for user {actual_user_id}", flush=True)
        
        # Determine project (fallback to user's first project)
        if not identity.project_id:
            proj_result = await db.execute(select(Project).filter(Project.user_id == actual_user_id))
            proj = proj_result.scalars().first()
            if proj:
                identity.project_id = proj.id
                await db.commit()
        
        from queue_system.manager import QueueManager
        manager = QueueManager()
        manager.enqueue(
            task_type="user_message", # Use user_message to trigger AI routing/processing
            user_id=actual_user_id,
            message=message_text,
            context={
                "source": "line",
                "external_reply_channel": "line",
                "line_reply_token": reply_token,
                "line_user_id": line_user_id,
                "project_id": identity.project_id
            } 
        )
    
    return {"status": "ok"}

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
            # --- NEW: Secure Linking Flow ---
            # Instead of auto-linking, we generate a token and invite the user
            print(f"[debug] Identity not found for {line_user_id}. Sending invitation.", flush=True)
            
            token_str = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(minutes=15)

            # Store link token in the dedicated integration table
            new_token = LineLinkingToken(
                token=token_str,
                line_user_id=line_user_id,
                expires_at=expires_at
            )
            db.add(new_token)
            await db.commit()
            
            # Send invitation via LINE
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
            link_url = f"{frontend_url}/integrations/line/link?token={token_str}"
            
            try:
                line_client = LineClient(service.api_key)
                invitation_text = (
                    "Welcome to VisionArk! 🚀\n\n"
                    "To start using this assistant, please link your VisionArk account by clicking the link below:\n\n"
                    f"{link_url}\n\n"
                    "(This link expires in 15 minutes)"
                )
                await line_client.push_message(line_user_id, invitation_text)
                print(f"[LINE Webhook] Sent invitation to {line_user_id}", flush=True)
            except Exception as se:
                print(f"[ERROR] Failed to send invitation: {se}", flush=True)
            
            # Skip processing this message further as user is not yet linked
            continue
        
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
