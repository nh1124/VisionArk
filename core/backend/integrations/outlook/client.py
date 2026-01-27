import httpx
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Union
from models.database import ServiceRegistry
from utils.encryption import decrypt_string, encrypt_string
from sqlalchemy import select

class OutlookClient:
    """
    Asynchronous client for Microsoft Graph API (Outlook).
    Handles token refresh and basic event operations.
    """
    AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

    def __init__(self, user_id: str, db_session: Any):
        self.user_id = user_id
        self.db = db_session
        self.access_token = None
        self.refresh_token = None
        self.client_id = None
        self.client_secret = None

    async def _ensure_auth(self):
        """Fetch tokens from DB and refresh if necessary."""
        result = await self.db.execute(
            select(ServiceRegistry).filter(
                ServiceRegistry.user_id == self.user_id,
                ServiceRegistry.service_name == "outlook"
            )
        )
        service = result.scalars().first()
        if not service:
            raise Exception("Outlook service not configured for user.")

        config = service.config or {}
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        
        if service.access_token_encrypted:
            self.access_token = decrypt_string(service.access_token_encrypted)
        if service.refresh_token_encrypted:
            self.refresh_token = decrypt_string(service.refresh_token_encrypted)

        return service

    async def _refresh_access_token(self):
        """Use refresh token to get a new access token."""
        if not self.refresh_token:
            raise Exception("No refresh token available.")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.AUTH_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                    "scope": "https://graph.microsoft.com/Calendars.ReadWrite offline_access"
                },
            )
            if resp.status_code != 200:
                raise Exception(f"Failed to refresh token: {resp.text}")
            
            data = resp.json()
            self.access_token = data["access_token"]
            
            # Update DB
            result = await self.db.execute(
                select(ServiceRegistry).filter(
                    ServiceRegistry.user_id == self.user_id,
                    ServiceRegistry.service_name == "outlook"
                )
            )
            service = result.scalars().first()
            if service:
                service.access_token_encrypted = encrypt_string(self.access_token)
                await self.db.commit()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        await self._ensure_auth()
        
        attempts = 0
        while attempts < 2:
            headers = {"Authorization": f"Bearer {self.access_token}"}
            if "headers" in kwargs:
                headers.update(kwargs.pop("headers"))

            async with httpx.AsyncClient(base_url=self.GRAPH_BASE_URL) as client:
                resp = await client.request(method, path, headers=headers, **kwargs)

            if resp.status_code == 401:
                await self._refresh_access_token()
                attempts += 1
                continue
            
            resp.raise_for_status()
            return resp.json() if resp.status_code != 204 else None

    async def list_events(self, time_min: Optional[datetime] = None, time_max: Optional[datetime] = None) -> List[Dict]:
        """List events from the user's default calendar."""
        query = ""
        if time_min and time_max:
            # Graph API uses $filter for date range
            start_str = time_min.isoformat() + "Z"
            end_str = time_max.isoformat() + "Z"
            query = f"?$filter=start/dateTime ge '{start_str}' and end/dateTime le '{end_str}'"
            
        data = await self._request("GET", f"/me/events{query}")
        return data.get("value", [])

    async def create_event(self, event_data: Dict) -> Dict:
        """Create a new event."""
        return await self._request("POST", "/me/events", json=event_data)

    async def update_event(self, event_id: str, event_data: Dict) -> Dict:
        """Update an existing event."""
        return await self._request("PATCH", f"/me/events/{event_id}", json=event_data)

    async def delete_event(self, event_id: str) -> None:
        """Delete an event."""
        await self._request("DELETE", f"/me/events/{event_id}")

async def get_outlook_client(user_id: str, db: Any) -> OutlookClient:
    return OutlookClient(user_id, db)
