"""
Authentication API endpoints for Phase 1 (Session-based auth)
Supports username/password registration and login with JWT tokens
"""
import uuid
import secrets
import logging
import shutil
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from shared.database import User, ServiceRegistry, UserSettings, Agent as UserAgent, get_engine
from shared.seed import seed_user_definitions
from app.config import settings
from domains.identity.auth import get_db, resolve_identity, Identity
from shared.password import hash_password, verify_password, MIN_PASSWORD_LENGTH
from shared.jwt import create_access_token, decode_access_token, decode_token, create_refresh_token
from datetime import timedelta
from shared.paths import get_user_projects_dir, get_project_dir, get_user_global_assets_dir, get_default_assets_dir
from shared.encryption import encrypt_string
import os
import httpx

logger = logging.getLogger(__name__)


class LBSProvisioningEmailConflictError(Exception):
    """Raised when LBS user creation fails due to duplicate email."""


def _resolve_service_url(url: str) -> str:
    """Normalize service URL and apply Docker hostname substitution."""
    if "localhost" in url and os.path.exists("/.dockerenv"):
        url = url.replace("localhost", "host.docker.internal")
    if not url.startswith("http"):
        url = f"http://{url}"
    return url.rstrip("/")


async def _auto_provision_lbs(username: str, service_email: str, service_password: str, lbs_url: str) -> Optional[str]:
    """
    Create a per-user LBS account and provision an API key.
    Uses the system-level LBS_API_KEY (admin) to create the user,
    then logs in as that user to provision a dedicated key.
    Returns the provisioned API key string, or None on failure.
    """
    try:
        from domains.lbs.client import LBSClient
        # Admin client (uses LBS_API_KEY from env or settings)
        admin_client = LBSClient(base_url=lbs_url)
        await admin_client.create_user(email=service_email, name=username, password=service_password)

        # User client — login to obtain JWT, then provision key
        user_client = LBSClient(base_url=lbs_url, api_key=None)
        await user_client.login(username_or_email=service_email, password=service_password)
        result = await user_client.provision_api_key(scopes=["read", "write"])
        return result.get("api_key") or result.get("key")
    except Exception as e:
        msg = str(e)
        if "400" in msg and "Email already registered" in msg:
            raise LBSProvisioningEmailConflictError(service_email) from e
        logger.warning("LBS auto-provisioning failed for %s: %s", username, e)
        return None


async def _auto_provision_kc(username: str, service_email: str, service_password: str, kc_url: str, gemini_api_key: Optional[str]) -> Optional[str]:
    """
    Register a per-user KnowledgeCore account and create an API key.
    Returns the API key string, or None on failure.
    """
    try:
        from integrations.knowledge_core.client import KnowledgeCoreClient
        async with KnowledgeCoreClient(base_url=kc_url) as kc:
            await kc.register(
                email=service_email,
                password=service_password,
                gemini_api_key=gemini_api_key or "",
                name=username,
            )
            await kc.login(email=service_email, password=service_password)
            key_resp = await kc.create_api_key(name=f"visionark-{username}")
            return key_resp.api_key
    except Exception as e:
        logger.warning("KnowledgeCore auto-provisioning failed for %s: %s", username, e)
        return None

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# Request/Response models
class RegisterRequest(BaseModel):
    username: str
    password: str
    email: EmailStr
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None
    
    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if len(v) > 50:
            raise ValueError('Username must be at most 50 characters')
        if not v.isalnum() and '_' not in v and '-' not in v:
            raise ValueError('Username can only contain letters, numbers, underscores, and hyphens')
        return v.lower()  # Normalize to lowercase
    
    @field_validator('password')
    @classmethod
    def validate_password(cls, v):
        if len(v) < MIN_PASSWORD_LENGTH:
            raise ValueError(f'Password must be at least {MIN_PASSWORD_LENGTH} characters')
        return v


class LoginRequest(BaseModel):
    username: str  # Can be username or email
    password: str


class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"
    user_id: str
    username: str


class FileTokenResponse(BaseModel):
    file_token: str
    expires_in: int = 300  # 5 minutes


class UserProfile(BaseModel):
    user_id: str
    username: str
    email: str | None
    is_active: bool


class MessageResponse(BaseModel):
    message: str

class ConnectionTest(BaseModel):
    api_key: str
    base_url: str | None = None


class AuthRefreshRequest(BaseModel):
    refresh_token: str

@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user account.
    
    Returns an access token and refresh token on successful registration.
    """
    # Check if username already exists
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")

    # Check if email already exists
    existing_email = db.query(User).filter(User.email == req.email).first()
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate at least one LLM key is provided
    if not any([req.gemini_api_key, req.openai_api_key, req.anthropic_api_key]):
        raise HTTPException(status_code=400, detail="At least one LLM API key is required (Gemini, OpenAI, or Anthropic)")

    # Build user (commit later, after external provisioning checks)
    user_id = str(uuid.uuid4())
    try:
        password_hash = hash_password(req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    user = User(
        id=user_id,
        username=req.username,
        email=str(req.email),
        password_hash=password_hash,
        is_active=True
    )

    # Create UserSettings with all provided LLM API keys
    ai_config = {}
    if req.gemini_api_key:
        ai_config["gemini_api_key"] = encrypt_string(req.gemini_api_key)
    if req.openai_api_key:
        ai_config["openai_api_key"] = encrypt_string(req.openai_api_key)
    if req.anthropic_api_key:
        ai_config["anthropic_api_key"] = encrypt_string(req.anthropic_api_key)

    user_settings = UserSettings(
        user_id=user_id,
        ai_config=ai_config
    )

    # Create user-level default Agent (one per user, shared across all projects)
    # skill_ids=[] → engine treats as ALL_SKILL_NAMES; graph_id=None → direct_assistant
    default_agent = UserAgent(
        id=str(uuid.uuid4()),
        user_id=user_id,
        display_name="Default Agent",
        description=None,
        skill_ids=[],
        graph_id=None,
        status="active",
    )

    # --- Auto-provision LBS and KnowledgeCore accounts ---
    # Use a dedicated service email and a generated strong password.
    service_email = str(req.email)
    service_password = secrets.token_urlsafe(24)

    lbs_url = _resolve_service_url(settings.lbs_service_url or "http://localhost:8001/api/lbs")
    kc_url = _resolve_service_url(settings.knowledge_core_url or "http://localhost:8200")

    try:
        lbs_api_key = await _auto_provision_lbs(req.username, service_email, service_password, lbs_url)
    except LBSProvisioningEmailConflictError:
        raise HTTPException(
            status_code=409,
            detail=(
                "The email address is already registered on LBS. "
                "Please use a different email address."
            ),
        )
    kc_api_key = await _auto_provision_kc(req.username, service_email, service_password, kc_url, req.gemini_api_key)

    # Persist VisionArk user and service registry entries
    try:
        db.add(user)
        db.add(user_settings)
        db.add(default_agent)

        lbs_service = ServiceRegistry(
            user_id=user_id,
            service_name="lbs",
            base_url=lbs_url,
            api_key_encrypted=encrypt_string(lbs_api_key) if lbs_api_key else None,
            is_active=bool(lbs_api_key),
        )
        kc_service = ServiceRegistry(
            user_id=user_id,
            service_name="knowledge_core",
            base_url=kc_url,
            api_key_encrypted=encrypt_string(kc_api_key) if kc_api_key else None,
            is_active=bool(kc_api_key),
        )
        db.add(lbs_service)
        db.add(kc_service)
        db.commit()
    except Exception as e:
        logger.warning("Failed to store service registry entries for %s: %s", user_id, e)
        db.rollback()

    # Seed per-user skill_registry and graph_registry
    # (done after commit so the user row exists before FK constraints are checked)
    try:
        seed_user_definitions(get_engine(), user_id)
    except Exception as e:
        logger.warning("Skill/graph seeding failed for user %s: %s", user_id, e)
    
    # Generate access and refresh tokens
    access_token = create_access_token(user_id=user_id, username=req.username)
    refresh_token = create_refresh_token(user_id=user_id, username=req.username)
    
    # Create user directories for projects and hub
    try:
        get_user_projects_dir(user_id)  # Creates /projects/{user_id}/
        
        # Create 'hub' project directory (The Root Project)
        get_project_dir(user_id, "hub")  # Creates /projects/{user_id}/hub/
        
        user_global_assets = get_user_global_assets_dir(user_id)  # Creates /global_assets/{user_id}/
        
        # Populate default assets
        default_assets_src = get_default_assets_dir()
        if default_assets_src.exists():
            global_prompt_src = default_assets_src / "system_prompt_global.md"
            if global_prompt_src.exists():
                shutil.copy2(global_prompt_src, user_global_assets / "system_prompt_global.md")
                logger.info(f"Copied default global prompt to user {user_id}")
        
        logger.info(f"Created and populated user directories for {user_id}")
    except Exception as e:
        logger.warning(f"Failed to create/populate user directories: {e}")
    
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user_id,
        username=req.username
    )

@router.post("/test-lbs-connection")
async def test_lbs_connection(test: ConnectionTest):
    """
    Public endpoint to test LBS connection before/during registration.
    """
    lbs_url = test.base_url or settings.lbs_service_url or "http://localhost:8001/api/lbs"
    if "localhost" in lbs_url and os.path.exists("/.dockerenv"):
        lbs_url = lbs_url.replace("localhost", "host.docker.internal")
    
    if not lbs_url.startswith("http"):
        lbs_url = f"http://{lbs_url}"

    health_url = f"{lbs_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url, headers={"x-api-key": test.api_key})
            if resp.status_code == 200:
                return {"status": "success", "message": "Valid LBS API Key!"}
            else:
                return {"status": "error", "message": f"Invalid Key (LBS status {resp.status_code})"}
    except Exception as e:
        return {"status": "error", "message": f"LBS Unreachable: {str(e)}"}


@router.post("/test-kc-connection")
async def test_kc_connection(test: ConnectionTest):
    """
    Public endpoint to test KnowledgeCore connection before/during registration.
    """
    kc_url = test.base_url or settings.knowledge_core_url or "http://localhost:8200"
    if "localhost" in kc_url and os.path.exists("/.dockerenv"):
        kc_url = kc_url.replace("localhost", "host.docker.internal")
    
    if not kc_url.startswith("http"):
        kc_url = f"http://{kc_url}"

    # Health is at root.
    kc_root = kc_url.rstrip("/")
    health_url = f"{kc_root}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url, headers={"x-api-key": test.api_key})
            if resp.status_code == 200:
                return {"status": "success", "message": "Valid KnowledgeCore API Key!"}
            else:
                return {"status": "error", "message": f"Invalid Key (KC status {resp.status_code})"}
    except Exception as e:
        return {"status": "error", "message": f"KnowledgeCore Unreachable: {str(e)}"}


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return access token and refresh token.
    
    Accepts username or email as the 'username' field.
    """
    # Find user by username or email
    user = db.query(User).filter(
        or_(
            User.username == req.username.lower(),
            User.email == req.username.lower()
        ),
        User.is_active == True
    ).first()
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Verify password
    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Generate access and refresh tokens
    access_token = create_access_token(user_id=user.id, username=user.username)
    refresh_token = create_refresh_token(user_id=user.id, username=user.username)
    
    return AuthResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=user.id,
        username=user.username
    )


@router.post("/refresh", response_model=AuthResponse)
async def refresh_token(req: AuthRefreshRequest, db: Session = Depends(get_db)):
    """
    Issue a new pair of access and refresh tokens based on a valid refresh token.
    """
    payload = decode_token(req.refresh_token, required_type="refresh")
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        
    user_id = payload.get("sub")
    username = payload.get("username")
    
    if not user_id or not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
        
    # Verify user still exists and is active
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
        
    # Issue new tokens
    new_access_token = create_access_token(user_id=user.id, username=user.username)
    new_refresh_token = create_refresh_token(user_id=user.id, username=user.username)
    
    return AuthResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        user_id=user.id,
        username=user.username
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(identity: Identity = Depends(resolve_identity)):
    """
    Logout current user.
    
    Note: With JWT tokens, actual invalidation requires token blacklisting
    which is deferred. For now, client should discard the token.
    """
    # TODO: Implement token blacklisting in Phase 2 if needed
    return MessageResponse(message="Logged out successfully. Please discard your token.")


@router.get("/me", response_model=UserProfile)
async def get_current_user(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Get current authenticated user's profile.
    """
    user = db.query(User).filter(User.id == identity.user_id).first()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserProfile(
        user_id=user.id,
        username=user.username,
        email=user.email,
        is_active=user.is_active
    )


@router.get("/file-token", response_model=FileTokenResponse)
async def get_file_token(identity: Identity = Depends(resolve_identity)):
    """
    Generate a short-lived token for file downloads/previews.
    Valid for 5 minutes and limited to 'file_download' scope.
    """
    token = create_access_token(
        user_id=identity.user_id,
        username=identity.username,
        expires_delta=timedelta(minutes=5),
        token_type="file_download"
    )
    return FileTokenResponse(file_token=token)
