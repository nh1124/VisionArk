import httpx
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.database import ServiceRegistry

class LineClient:
    """Wrapper for LINE Messaging API"""
    
    BASE_URL = "https://api.line.me/v2/bot"
    
    def __init__(self, channel_access_token: str, channel_secret: str = None):
        self.channel_access_token = channel_access_token
        self.channel_secret = channel_secret
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.channel_access_token}"
        }

    async def push_message(self, to_user_id: str, text: str) -> Dict[str, Any]:
        """Send a push message to a specific LINE user ID."""
        url = f"{self.BASE_URL}/message/push"
        payload = {
            "to": to_user_id,
            "messages": [{"type": "text", "text": text}]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def reply_message(self, reply_token: str, text: str) -> Dict[str, Any]:
        """Reply to an incoming message using a reply token."""
        url = f"{self.BASE_URL}/message/reply"
        payload = {
            "replyToken": reply_token,
            "messages": [{"type": "text", "text": text}]
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def get_profile(self, user_id: str) -> Dict[str, Any]:
        """Fetch user profile information (display name, etc)."""
        url = f"{self.BASE_URL}/profile/{user_id}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=self.headers)
            resp.raise_for_status()
            return resp.json()

async def get_line_client(user_id: str, db: AsyncSession) -> Optional[LineClient]:
    """Factory to create a LineClient from a user's service registry or global env."""
    import os
    channel_secret = os.getenv("LINE_CHANNEL_SECRET")
    channel_access_token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
    
    # Priority 1: Shared App (Environment Variables)
    if channel_access_token:
        return LineClient(channel_access_token, channel_secret)
        
    # Priority 2: Individual App (Service Registry)
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == user_id,
        ServiceRegistry.service_name == "line",
        ServiceRegistry.is_active == True
    ))
    service = result.scalars().first()
    if not service:
        return None
    
    channel_secret = service.config.get("channel_secret") if service.config else None
    return LineClient(service.api_key, channel_secret)
