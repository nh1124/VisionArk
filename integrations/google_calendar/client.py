import httpx
from datetime import datetime, date
from typing import List, Optional, Dict, Any, Union
from shared.database import ServiceRegistry
from shared.encryption import decrypt_string, encrypt_string
from sqlalchemy import select

class GoogleCalendarClient:
    """
    Asynchronous client for Google Calendar API.
    Handles token refresh and basic event operations.
    """
    AUTH_URL = "https://oauth2.googleapis.com/token"
    CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3"

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
                ServiceRegistry.service_name == "google_calendar"
            )
        )
        service = result.scalars().first()
        if not service:
            raise Exception("Google Calendar service not configured for user.")

        config = service.config or {}
        self.client_id = config.get("client_id")
        self.client_secret = config.get("client_secret")
        
        # Use getattr to be safe against stale class definitions in memory
        acc_enc = getattr(service, "access_token_encrypted", None)
        ref_enc = getattr(service, "refresh_token_encrypted", None)

        if acc_enc:
            self.access_token = decrypt_string(acc_enc)
        if ref_enc:
            self.refresh_token = decrypt_string(ref_enc)

        # Basic token check (could check expiry, but for now we'll rely on 401 handling)
        return service

    async def _refresh_access_token(self):
        """Use refresh token to get a new access token."""
        if not self.refresh_token:
            raise Exception("No refresh token available. Please re-link your Google Calendar account in Settings.")

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.AUTH_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
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
                    ServiceRegistry.service_name == "google_calendar"
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
            if not self.access_token:
                # If we have no token, try to refresh immediately before the first request
                try:
                    await self._refresh_access_token()
                except Exception as e:
                    raise Exception(f"Google Calendar authentication failed: No access token available and refresh failed: {e}")

            if not self.access_token:
                 raise Exception("Google Calendar authentication failed: Access token is empty after refresh attempt.")

            headers = {"Authorization": f"Bearer {self.access_token}"}
            if "headers" in kwargs:
                headers.update(kwargs.pop("headers"))

            async with httpx.AsyncClient(base_url=self.CALENDAR_BASE_URL) as client:
                resp = await client.request(method, path, headers=headers, **kwargs)

            if resp.status_code == 401:
                await self._refresh_access_token()
                attempts += 1
                continue
            
            if resp.status_code == 403:
                error_msg = f"403 Forbidden: Google Calendar API Access Denied. Check scopes and ensuring API is enabled in Cloud Console. Details: {resp.text}"
                raise Exception(error_msg)
            
            if resp.status_code == 400:
                error_msg = f"400 Bad Request: Google Calendar API rejected the request. Details: {resp.text}"
                raise Exception(error_msg)

            resp.raise_for_status()
            return resp.json() if resp.status_code != 204 else None

    async def list_events(self, calendar_id: str = "primary", time_min: Optional[datetime] = None, time_max: Optional[datetime] = None) -> List[Dict]:
        """List events from a calendar."""
        params = {"singleEvents": "true", "orderBy": "startTime"}
        if time_min:
            params["timeMin"] = time_min.isoformat() + "Z"
        if time_max:
            params["timeMax"] = time_max.isoformat() + "Z"
            
        data = await self._request("GET", f"/calendars/{calendar_id}/events", params=params)
        return data.get("items", [])

    async def create_event(self, calendar_id: str, event_data: Dict, params: Optional[Dict] = None) -> Dict:
        """Create a new event."""
        return await self._request("POST", f"/calendars/{calendar_id}/events", json=event_data, params=params)

    async def update_event(self, calendar_id: str, event_id: str, event_data: Dict) -> Dict:
        """Update an existing event."""
        return await self._request("PATCH", f"/calendars/{calendar_id}/events/{event_id}", json=event_data)

    async def delete_event(self, calendar_id: str, event_id: str) -> None:
        """Delete an event."""
        await self._request("DELETE", f"/calendars/{calendar_id}/events/{event_id}")

async def get_google_calendar_client(user_id: str, db: Any) -> GoogleCalendarClient:
    return GoogleCalendarClient(user_id, db)
