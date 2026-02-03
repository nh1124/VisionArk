import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from queue_system.manager import QueueManager
from models.database import get_async_db, ServiceRegistry, TaskType
from utils.encryption import encrypt_string
import httpx

router = APIRouter()
ROUTER_PREFIX = "/outlook"
ROUTER_TAGS = ["Outlook"]

@router.get("/auth")
async def outlook_auth(user_id: str):
    """Initiate Microsoft OAuth2 flow."""
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    redirect_uri = os.getenv("OUTLOOK_REDIRECT_URI", "http://localhost:8000/api/outlook/callback")
    scope = "https://graph.microsoft.com/Calendars.ReadWrite offline_access"
    
    auth_url = (
        f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?"
        f"client_id={client_id}&"
        f"response_type=code&"
        f"redirect_uri={redirect_uri}&"
        f"response_mode=query&"
        f"scope={scope}&"
        f"state={user_id}"
    )
    return {"auth_url": auth_url}

@router.get("/callback")
async def outlook_callback(code: str, state: str, db: AsyncSession = Depends(get_async_db)):
    """Handle Microsoft OAuth2 callback."""
    user_id = state
    client_id = os.getenv("OUTLOOK_CLIENT_ID")
    client_secret = os.getenv("OUTLOOK_CLIENT_SECRET")
    redirect_uri = os.getenv("OUTLOOK_REDIRECT_URI", "http://localhost:8000/api/outlook/callback")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=400, detail=f"Failed to get tokens: {resp.text}")
        
        data = resp.json()
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        # Save to ServiceRegistry
        from sqlalchemy import select
        result = await db.execute(
            select(ServiceRegistry).filter(
                ServiceRegistry.user_id == user_id,
                ServiceRegistry.service_name == "outlook"
            )
        )
        service = result.scalars().first()
        if not service:
            service = ServiceRegistry(
                user_id=user_id,
                service_name="outlook",
                base_url="https://graph.microsoft.com",
                is_active=True,
                config={"client_id": client_id, "client_secret": client_secret}
            )
            db.add(service)
        
        service.access_token_encrypted = encrypt_string(access_token)
        if refresh_token:
            service.refresh_token_encrypted = encrypt_string(refresh_token)
        
        await db.commit()

        # Trigger Initial Sync
        queue = QueueManager()
        await queue.enqueue(
            user_id=user_id,
            message="Initial sync after Outlook connection",
            context={"service_name": "outlook", "triggered_by": "auth_callback"},
            task_type="sync_outlook"
        )

    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}/settings?status=connected&service=outlook")

@router.post("/webhook")
async def outlook_webhook(request: Request, db: AsyncSession = Depends(get_async_db)):
    """
    Handle Microsoft Graph notifications.
    Handshake: MS sends 'validationToken' as query param.
    Notification: MS sends JSON body with 'value' list containing 'subscriptionId'.
    """
    # 1. Validation Handshake
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(validation_token)

    # 2. Notification Data
    body = await request.json()
    notifications = body.get("value", [])
    
    if not notifications:
        return {"status": "ok"}

    queue = QueueManager()
    
    for note in notifications:
        sub_id = note.get("subscriptionId")
        if not sub_id: continue
        
        # Identify user by subscription_id in ServiceRegistry config
        result = await db.execute(
            select(ServiceRegistry).filter(
                ServiceRegistry.service_name == "outlook",
                ServiceRegistry.config["webhook_subscription_id"].astext == sub_id
            )
        )
        service = result.scalars().first()
        if service:
            await queue.enqueue(
                user_id=service.user_id,
                message="Sync triggered for outlook",
                context={"service_name": "outlook", "triggered_by": "webhook"},
                task_type="sync_outlook"
            )

    return {"status": "received"}

@router.delete("/disconnect")
async def disconnect(user_id: str, db: AsyncSession = Depends(get_async_db)):
    """Remove Outlook connection."""
    from sqlalchemy import delete
    await db.execute(
        delete(ServiceRegistry).filter(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name == "outlook"
        )
    )
    await db.commit()
    return {"status": "disconnected"}

@router.get("/status")
async def get_status(user_id: str, db: AsyncSession = Depends(get_async_db)):
    """Check connectivity status."""
    from sqlalchemy import select
    result = await db.execute(
        select(ServiceRegistry).filter(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name == "outlook"
        )
    )
    service = result.scalars().first()
    return {"connected": service is not None and service.is_active}
