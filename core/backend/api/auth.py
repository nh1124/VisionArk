"""
Authentication API endpoints for Phase 1 (Session-based auth)
Supports username/password registration and login with JWT tokens
"""
import uuid
import logging
import shutil
from fastapi import APIRouter, Depends, HTTPException, Response, Request
from pydantic import BaseModel, EmailStr, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import or_

from models.database import User, ServiceRegistry, UserSettings
from config import settings
from services.auth import get_db, resolve_identity, Identity
from utils.password import hash_password, verify_password, MIN_PASSWORD_LENGTH
from utils.jwt import create_access_token, decode_access_token
from utils.paths import get_user_hub_dir, get_user_spokes_dir, get_user_global_assets_dir, get_default_assets_dir
from utils.encryption import encrypt_string
import os
import httpx

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["Auth"])


# Request/Response models
class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    lbs_api_key: str
    gemini_api_key: str
    
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
    token_type: str = "bearer"
    user_id: str
    username: str


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


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """
    Register a new user account.
    
    Returns an access token on successful registration.
    """
    # Check if username already exists
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    
    # Check if email already exists (if provided)
    if req.email:
        existing_email = db.query(User).filter(User.email == req.email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="Email already registered")
    
    # Validate LBS key before creating account
    lbs_url = (settings.lbs_service_url or "http://localhost:8100/api/lbs")
    if "localhost" in lbs_url and os.path.exists("/.dockerenv"):
        lbs_url = lbs_url.replace("localhost", "host.docker.internal")
    
    if not lbs_url.startswith("http"):
        lbs_url = f"http://{lbs_url}"

    health_url = f"{lbs_url.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url, headers={"x-api-key": req.lbs_api_key})
            if resp.status_code != 200:
                raise HTTPException(status_code=400, detail=f"Invalid LBS API Key (LBS returned {resp.status_code})")
    except Exception as e:
        logger.error(f"LBS validation failed during registration: {str(e)}")
        raise HTTPException(status_code=400, detail="LBS service unreachable. Please ensure LBS is running.")

    # Create user
    user_id = str(uuid.uuid4())
    try:
        password_hash = hash_password(req.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    user = User(
        id=user_id,
        username=req.username,
        email=req.email,
        password_hash=password_hash,
        is_active=True
    )
    
    # Create LBS service registry entry
    lbs_service = ServiceRegistry(
        user_id=user_id,
        service_name="lbs",
        base_url=lbs_url,
        api_key_encrypted=encrypt_string(req.lbs_api_key),
        is_active=True
    )
    
    # Create UserSettings with Gemini API Key
    user_settings = UserSettings(
        user_id=user_id,
        ai_config={
            "gemini_api_key": encrypt_string(req.gemini_api_key)
        }
    )
    
    try:
        db.add(user)
        db.add(lbs_service)
        db.add(user_settings)
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create account: {str(e)}")
    
    # Generate access token
    access_token = create_access_token(user_id=user_id, username=req.username)
    
    # Create user directories for spokes, hub_data, and global_assets
    try:
        get_user_hub_dir(user_id)  # Creates /hub_data/{user_id}/
        get_user_spokes_dir(user_id)  # Creates /spokes/{user_id}/
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
        user_id=user_id,
        username=req.username
    )

@router.post("/test-lbs-connection")
async def test_lbs_connection(test: ConnectionTest):
    """
    Public endpoint to test LBS connection before/during registration.
    """
    lbs_url = test.base_url or settings.lbs_service_url or "http://localhost:8100/api/lbs"
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


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate user and return access token.
    
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
    
    # Generate access token
    access_token = create_access_token(user_id=user.id, username=user.username)
    
    return AuthResponse(
        access_token=access_token,
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
