import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from .client import GoogleCalendarClient
from queue_system.manager import QueueManager
from models.database import get_async_db, ServiceRegistry, TaskType
from utils.encryption import encrypt_string # Encrypt helper
import httpx

router = APIRouter()
ROUTER_PREFIX = "/google-calendar"
ROUTER_TAGS = ["Google Calendar"]

@router.get("/auth")
async def google_auth(user_id: str, db: AsyncSession = Depends(get_async_db)):
    """Initiate Google OAuth2 flow."""
    # This would usually redirect to Google's auth page.
    # For now, we'll return the URL the frontend should redirect to.
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/google-calendar/callback")
    scope = "https://www.googleapis.com/auth/calendar"
    
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}&"
        f"redirect_uri={redirect_uri}&"
        f"response_type=code&"
        f"scope={scope}&"
        f"access_type=offline&"
        f"prompt=consent&"
        f"state={user_id}"
    )
    return {"auth_url": auth_url}

@router.get("/callback")
async def google_callback(code: str, state: str, db: AsyncSession = Depends(get_async_db)):
    """Handle Google OAuth2 callback."""
    user_id = state
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/google-calendar/callback")

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
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
                ServiceRegistry.service_name == "google_calendar"
            )
        )
        service = result.scalars().first()
        if not service:
            service = ServiceRegistry(
                user_id=user_id,
                service_name="google_calendar",
                base_url="https://www.googleapis.com", 
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
            message="Initial sync after Google Calendar connection",
            context={"service_name": "google_calendar", "triggered_by": "auth_callback"},
            task_type="sync_google_calendar"
        )

    # Redirect back to frontend settings
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
    return RedirectResponse(url=f"{frontend_url}/settings?status=connected&service=google_calendar")

@router.post("/webhook")
async def google_webhook(request: Request, db: AsyncSession = Depends(get_async_db)):
    """
    Handle Google Calendar notifications.
    Google sends headers: X-Goog-Resource-ID, X-Goog-Channel-ID, X-Goog-Resource-State
    """
    channel_id = request.headers.get("X-Goog-Channel-ID")
    state = request.headers.get("X-Goog-Resource-State")
    
    if state == "sync": # Initial sync notification
        return {"status": "ok"}
        
    if not channel_id:
        raise HTTPException(status_code=400, detail="Missing channel ID")

    # Find user by channel_id in ServiceRegistry config
    from sqlalchemy import select
    from models.database import ServiceRegistry
    from services.sync_coordinator import SyncCoordinator
    
    # We search in JSON config for the channel_id
    # Note: For performance, a dedicated WebhookRegistry table is better, 
    # but using JSON search for simplicity in this iteration.
    result = await db.execute(
        select(ServiceRegistry).filter(
            ServiceRegistry.service_name == "google_calendar",
            ServiceRegistry.config["webhook_channel_id"].astext == channel_id
        )
    )
    service = result.scalars().first()
    
    if service:
        queue = QueueManager()
        await queue.enqueue(
            user_id=service.user_id,
            message="Sync triggered for google_calendar",
            context={"service_name": "google_calendar", "triggered_by": "webhook"},
            task_type="sync_google_calendar"
        )
        
    return {"status": "received"}

@router.delete("/disconnect")
async def disconnect(user_id: str, db: AsyncSession = Depends(get_async_db)):
    """Remove Google Calendar connection."""
    from sqlalchemy import delete
    await db.execute(
        delete(ServiceRegistry).filter(
            ServiceRegistry.user_id == user_id,
            ServiceRegistry.service_name == "google_calendar"
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
            ServiceRegistry.service_name == "google_calendar"
        )
    )
    service = result.scalars().first()
    return {"connected": service is not None and service.is_active}
