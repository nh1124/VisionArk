
import httpx
import time
from typing import Optional, List, Dict, Any, Union
import uuid

from .exceptions import (
    KnowledgeCoreError,
    AuthenticationError,
    ValidationError,
    ResourceNotFoundError,
    RateLimitError,
    InternalServerError
)
from .models import (
    LoginRequest, RegisterRequest, TokenResponse, UserResponse,
    APIKeyCreateRequest, APIKeyResponse, APIKeyNewResponse,
    PasswordChangeRequest, SystemConfigResponse, SystemConfigRequest,
    UserSettingsRequest, MemoryCreateRequest, MemoryUpdateRequest,
    MemoryResponse, MemoryListResponse, IngestRequest, IngestResponse,
    ContextRequest, ContextResponse
)

class KnowledgeCoreClient:
    """A comprehensive Python client for the KnowledgeCore API."""

    def __init__(self, base_url: str = "http://localhost:8200", timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.token: Optional[str] = None
        self.api_key: Optional[str] = None
        self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif self.api_key:
            headers["X-API-KEY"] = self.api_key
        return headers

    def _handle_response(self, response: httpx.Response) -> Dict[str, Any]:
        try:
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code
            try:
                error_data = e.response.json()
                message = error_data.get("error", {}).get("message", str(e))
                details = error_data.get("error", {}).get("details", {})
            except Exception:
                message = str(e)
                details = {"text": e.response.text}

            if status_code == 401:
                raise AuthenticationError(message, status_code, details)
            elif status_code == 403:
                raise AuthenticationError(f"Forbidden: {message}", status_code, details)
            elif status_code == 404:
                raise ResourceNotFoundError(message, status_code, details)
            elif status_code == 422:
                raise ValidationError(message, status_code, details)
            elif status_code == 429:
                raise RateLimitError(message, status_code, details)
            elif status_code >= 500:
                raise InternalServerError(message, status_code, details)
            else:
                raise KnowledgeCoreError(message, status_code, details)
        except Exception as e:
            raise KnowledgeCoreError(str(e))

    def _request(self, method: str, path: str, **kwargs) -> Dict[str, Any]:
        headers = self._get_headers()
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))
        
        response = self._client.request(method, path, headers=headers, **kwargs)
        return self._handle_response(response)

    # --- Authentication & User Management ---

    def login(self, email: str, password: str) -> TokenResponse:
        """Authenticate and get a JWT token."""
        data = self._request("POST", "/v1/auth/login", json={"email": email, "password": password})
        res = TokenResponse(**data)
        self.token = res.access_token
        self.api_key = None
        return res

    def register(self, email: str, password: str, gemini_api_key: str, name: Optional[str] = None, is_admin: bool = False) -> Dict[str, Any]:
        """Register a new user."""
        return self._request("POST", "/v1/auth/register", json={
            "email": email,
            "password": password,
            "gemini_api_key": gemini_api_key,
            "name": name,
            "is_admin": is_admin
        })

    def set_api_key(self, api_key: str):
        """Set the API key for subsequent requests."""
        self.api_key = api_key
        self.token = None

    def create_api_key(self, name: str, client_id: Optional[str] = None, scopes: List[str] = None, is_admin: bool = False) -> APIKeyNewResponse:
        """Create a new API key (requires JWT)."""
        payload = {"name": name, "is_admin": is_admin}
        if client_id: payload["client_id"] = client_id
        if scopes: payload["scopes"] = scopes
        data = self._request("POST", "/v1/auth/keys", json=payload)
        return APIKeyNewResponse(**data)

    def list_api_keys(self) -> List[APIKeyResponse]:
        """List active API keys for the current user."""
        data = self._request("GET", "/v1/auth/keys")
        return [APIKeyResponse(**item) for item in data]

    def revoke_api_key(self, key_id: Union[str, uuid.UUID]) -> Dict[str, str]:
        """Revoke an API key."""
        return self._request("DELETE", f"/v1/auth/keys/{key_id}")

    def get_my_profile(self) -> UserResponse:
        """Return current user profile (requires local Bearer token)."""
        data = self._request("GET", "/v1/auth/me")
        return UserResponse(**data)

    def get_my_key_info(self) -> APIKeyResponse:
        """Return current API key profile (requires X-API-KEY)."""
        data = self._request("GET", "/v1/auth/keys/me")
        return APIKeyResponse(**data)

    def change_password(self, current_password: str, new_password: str) -> Dict[str, str]:
        """Change the current user's password."""
        return self._request("POST", "/v1/auth/password/change", json={
            "current_password": current_password,
            "new_password": new_password
        })

    def update_user_settings(self, gemini_api_key: Optional[str] = None) -> Dict[str, str]:
        """Update per-user settings (Gemini API key)."""
        payload = {}
        if gemini_api_key is not None: payload["gemini_api_key"] = gemini_api_key
        return self._request("PATCH", "/v1/auth/settings", json=payload)

    def delete_account(self) -> Dict[str, Any]:
        """Delete the current user account and all associated data."""
        return self._request("POST", "/v1/auth/delete-account")

    # --- System Administration ---

    def get_system_config(self) -> SystemConfigResponse:
        """Fetch system configuration (Admin only)."""
        data = self._request("GET", "/v1/auth/config")
        return SystemConfigResponse(**data)

    def update_system_config(self, log_level: Optional[str] = None, debug: Optional[bool] = None) -> Dict[str, str]:
        """Update system configuration (Admin only)."""
        payload = {}
        if log_level is not None: payload["log_level"] = log_level
        if debug is not None: payload["debug"] = debug
        return self._request("POST", "/v1/auth/config", json=payload)

    def get_db_triggers(self) -> List[Dict[str, str]]:
        """Debug endpoint to list all triggers in the DB."""
        return self._request("GET", "/v1/auth/debug/triggers")

    # --- Ingestion ---

    def ingest_text(self, text: str, source: str = "api", scope: str = "global", 
                   agent_id: Optional[str] = None, event_time: Optional[Any] = None, 
                   skip_dedup: bool = False) -> IngestResponse:
        """Analyze raw text in the background and create memories."""
        payload = {
            "text": text,
            "source": source,
            "scope": scope,
            "agent_id": agent_id,
            "skip_dedup": skip_dedup
        }
        if event_time: payload["event_time"] = event_time.isoformat() if hasattr(event_time, 'isoformat') else event_time
        data = self._request("POST", "/v1/ingest", json=payload)
        return IngestResponse(**data)

    def get_ingest_status(self, ingest_id: str) -> Dict[str, Any]:
        """Get status of an ingestion job."""
        return self._request("GET", f"/v1/ingest/{ingest_id}")

    def wait_for_ingestion(self, ingest_id: str, timeout: int = 60, interval: int = 2) -> Dict[str, Any]:
        """Poll the server until the ingestion job is completed or failed."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_ingest_status(ingest_id)
            if status.get("status") in ["completed", "failed"]:
                return status
            time.sleep(interval)
        raise KnowledgeCoreError(f"Ingestion job {ingest_id} timed out after {timeout} seconds")

    # --- Memories ---

    def create_memory(self, content: str, memory_type: str = "fact", importance: int = 3, 
                     tags: List[str] = None, confidence: float = 1.0, 
                     source: Optional[str] = None, skip_dedup: bool = False) -> MemoryResponse:
        """Directly create a memory (bypass AI analysis)."""
        payload = {
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
            "tags": tags or [],
            "confidence": confidence,
            "source": source,
            "skip_dedup": skip_dedup
        }
        data = self._request("POST", "/v1/memories", json=payload)
        return MemoryResponse(**data)

    def list_memories(self, memory_type: Optional[str] = None, tags: Optional[str] = None, 
                      query: Optional[str] = None, limit: int = 50) -> MemoryListResponse:
        """Search and retrieve memories."""
        params = {"limit": limit}
        if memory_type: params["memory_type"] = memory_type
        if tags: params["tags"] = tags
        if query: params["q"] = query
        data = self._request("GET", "/v1/memories", params=params)
        return MemoryListResponse(**data)

    def get_memory(self, memory_id: Union[str, uuid.UUID]) -> MemoryResponse:
        """Get a single memory by ID."""
        data = self._request("GET", f"/v1/memories/{memory_id}")
        return MemoryResponse(**data)

    def update_memory(self, memory_id: Union[str, uuid.UUID], content: Optional[str] = None, 
                      tags: Optional[List[str]] = None, importance: Optional[int] = None, 
                      confidence: Optional[float] = None) -> MemoryResponse:
        """Update a memory's content, tags, importance, or confidence."""
        payload = {}
        if content is not None: payload["content"] = content
        if tags is not None: payload["tags"] = tags
        if importance is not None: payload["importance"] = importance
        if confidence is not None: payload["confidence"] = confidence
        data = self._request("PATCH", f"/v1/memories/{memory_id}", json=payload)
        return MemoryResponse(**data)

    def delete_memory(self, memory_id: Union[str, uuid.UUID], hard: bool = False) -> Dict[str, Any]:
        """Delete a memory."""
        return self._request("DELETE", f"/v1/memories/{memory_id}", params={"hard": hard})

    def dump_memories(self, format: str = "json") -> Dict[str, Any]:
        """Export all memories."""
        return self._request("GET", "/v1/dump", params={"format": format})

    # --- Context ---

    def get_context(self, query: str, k: int = 10, include_global: bool = True, 
                    app_context: Optional[str] = None, return_evidence: bool = True) -> ContextResponse:
        """Synthesize context from memories for a given query."""
        payload = {
            "query": query,
            "k": k,
            "include_global": include_global,
            "app_context": app_context,
            "return_evidence": return_evidence
        }
        data = self._request("POST", "/v1/context", json=payload)
        return ContextResponse(**data)
