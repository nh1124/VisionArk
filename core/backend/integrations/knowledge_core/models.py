
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

# --- Auth Models ---

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    is_admin: bool = False
    gemini_api_key: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID

class UserResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: Optional[str]
    is_admin: bool
    is_active: bool
    auth_method: Optional[str] = None
    has_gemini_key: bool = False

class APIKeyCreateRequest(BaseModel):
    name: str
    client_id: Optional[str] = None
    scopes: List[str] = ["memories:read", "context"]
    is_admin: bool = False

class APIKeyResponse(BaseModel):
    id: uuid.UUID
    client_id: Optional[str] = None
    name: Optional[str]
    scopes: List[str]
    is_active: bool
    is_admin: bool
    created_at: str
    last_used_at: Optional[str] = None

class APIKeyNewResponse(BaseModel):
    status: str
    api_key: str
    details: APIKeyResponse

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str

class SystemConfigResponse(BaseModel):
    log_level: str
    debug: bool

class SystemConfigRequest(BaseModel):
    log_level: Optional[str] = None
    debug: Optional[bool] = None

class UserSettingsRequest(BaseModel):
    gemini_api_key: Optional[str] = None

# --- Memory Models ---

class MemoryCreateRequest(BaseModel):
    content: str
    memory_type: str = "fact"
    importance: int = 3
    tags: List[str] = []
    confidence: float = 1.0
    source: Optional[str] = None
    skip_dedup: bool = False

class MemoryUpdateRequest(BaseModel):
    content: Optional[str] = None
    tags: Optional[List[str]] = None
    importance: Optional[int] = None
    confidence: Optional[float] = None

class MemoryResponse(BaseModel):
    id: Optional[uuid.UUID] = None
    content: Optional[str] = None
    memory_type: Optional[str] = None
    importance: Optional[int] = None
    confidence: Optional[float] = None
    tags: List[str] = []
    user_id: Optional[uuid.UUID] = None
    scope: Optional[str] = None
    agent_id: Optional[str] = None
    source: Optional[str] = None
    input_channel: Optional[str] = None
    event_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    warnings: Optional[List[str]] = None

class MemoryListResponse(BaseModel):
    memories: List[MemoryResponse]
    total: int
    warnings: Optional[List[str]] = None

# --- Ingest Models ---

class IngestRequest(BaseModel):
    text: str
    source: str = "api"
    scope: str = "global"
    agent_id: Optional[str] = None
    event_time: Optional[datetime] = None
    skip_dedup: bool = False

class IngestResponse(BaseModel):
    ingest_id: str
    status: str = "started"
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    memory_ids: List[str] = []
    warnings: Optional[List[str]] = None

# --- Context Models ---

class ContextRequest(BaseModel):
    query: str
    k: int = 10
    include_global: bool = True
    app_context: Optional[str] = None
    return_evidence: bool = True

class ContextResponse(BaseModel):
    context: Dict[str, Any]
    evidence: Optional[List[Dict[str, Any]]] = None
    warnings: Optional[List[str]] = None
