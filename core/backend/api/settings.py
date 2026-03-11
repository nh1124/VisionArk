from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime
import httpx
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from shared.database import User, UserSettings, ServiceRegistry, ExternalIdentity, get_async_db
from domains.identity.auth import resolve_identity, Identity
from shared.password import hash_password, verify_password
from shared.encryption import encrypt_string, decrypt_string
from app.config import settings
from va_sdk.discovery import get_integration_catalog

router = APIRouter(prefix="/api/settings", tags=["Settings"])
logger = logging.getLogger(__name__)

@router.get("/integrations/hub")
async def get_integration_hub_catalog():
    """Returns the dynamic integration catalog discovered from integrations/ folder"""
    return get_integration_catalog()

# --- Schemas ---

class AIConfigUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    default_model: Optional[str] = None

class GeneralSettingsUpdate(BaseModel):
    language: Optional[str] = None
    timezone: Optional[str] = None
    location: Optional[str] = None
    notification_sound: Optional[str] = None

class ServiceRegister(BaseModel):
    service_name: str
    base_url: str = ""
    api_key: Optional[str] = None
    config: Optional[Dict] = None   # None = leave existing config untouched
    is_active: Optional[bool] = None

class ConnectionTest(BaseModel):
    base_url: str
    api_key: str

class ServiceResponse(BaseModel):
    id: int
    service_name: str
    base_url: str
    is_active: bool
    health_status: Optional[str]
    last_health_check: Optional[datetime]
    config: Optional[Dict] = {}
    
class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class UserProfile(BaseModel):
    id: str
    username: str
    email: Optional[str]

class SettingsSummary(BaseModel):
    profile: UserProfile
    ai_config: Dict
    general_settings: Dict
    services: List[ServiceResponse]
    integrations: List[Dict]

# --- Endpoints ---

@router.get("", response_model=SettingsSummary)
async def get_settings(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get all user settings, services, and integrations"""
    # 1. AI Config & General Settings
    result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
    settings_obj = result.scalars().first()
    ai_config = settings_obj.ai_config if settings_obj else {}
    general_settings_data = settings_obj.general_settings if settings_obj else {}
    
    # Mask API keys in response
    masked_ai_config = ai_config.copy()
    for key in ["gemini_api_key", "openai_api_key", "anthropic_api_key"]:
        if masked_ai_config.get(key):
            masked_ai_config[key] = "********"
            
    # 2. Services
    result = await db.execute(select(ServiceRegistry).filter(ServiceRegistry.user_id == identity.user_id))
    services = result.scalars().all()
    
    # 3. Integrations
    result = await db.execute(select(ExternalIdentity).filter(ExternalIdentity.user_id == identity.user_id))
    integrations = result.scalars().all()
    integration_list = [
        {"issuer": i.issuer, "subject": i.subject, "linked_at": i.linked_at}
        for i in integrations
    ]
    
    # 4. Profile
    result = await db.execute(select(User).filter(User.id == identity.user_id))
    user = result.scalars().first()
    profile = {
        "id": user.id,
        "username": user.username,
        "email": user.email
    } if user else {"id": identity.user_id, "username": "Unknown", "email": None}
    
    return {
        "profile": profile,
        "ai_config": masked_ai_config,
        "general_settings": general_settings_data,
        "services": services,
        "integrations": integration_list
    }

@router.get("/sounds")
async def get_available_sounds():
    """List available notification sound files in the assets directory."""
    from shared.paths import Path
    # In Docker, this is /app/assets/static/sounds
    # Locally, it's VisionArk/assets/static/sounds
    current_file = Path(__file__).resolve()
    if current_file.parts and 'app' in current_file.parts:
        sounds_dir = Path("/app/assets/static/sounds")
    else:
        # Local development path resolution
        from shared.paths import PROJECT_ROOT
        sounds_dir = PROJECT_ROOT / "assets" / "static" / "sounds"
    
    sounds = []
    if sounds_dir.exists():
        for f in sounds_dir.iterdir():
            if f.suffix.lower() in [".mp3", ".wav", ".ogg"]:
                # name is the key for settings, display_name is for UI
                name = f.stem
                display_name = name.replace("_", " ").replace("-", " ").title()
                sounds.append({"id": name, "label": display_name})
    
    # Fallback to defaults if directory is empty or missing
    if not sounds:
        sounds = [
            {"id": "timer", "label": "Standard Beep"},
            {"id": "bell", "label": "Ringing Bell"},
            {"id": "chime", "label": "Soft Chime"},
            {"id": "digital", "label": "Digital Alert"}
        ]
        
    return sorted(sounds, key=lambda x: x["label"])


@router.patch("/general")
async def update_general_settings(
    update: GeneralSettingsUpdate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update general localization settings"""
    from sqlalchemy.orm.attributes import flag_modified
    
    result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
    settings_obj = result.scalars().first()
    if not settings_obj:
        # Default initialization
        settings_obj = UserSettings(
            user_id=identity.user_id, 
            ai_config={}, 
            general_settings={"language": "en", "timezone": "UTC", "location": ""}
        )
        db.add(settings_obj)
    
    current_general = dict(settings_obj.general_settings) if settings_obj.general_settings else {}
    
    if update.language is not None:
        current_general["language"] = update.language
    if update.timezone is not None:
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo(update.timezone)
            current_general["timezone"] = update.timezone
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid timezone: '{update.timezone}'. Must be a valid IANA timezone (e.g. 'Asia/Tokyo').")
    if update.location is not None:
        current_general["location"] = update.location
    if update.notification_sound is not None:
        current_general["notification_sound"] = update.notification_sound
        
    settings_obj.general_settings = current_general
    flag_modified(settings_obj, "general_settings")
    await db.commit()
    return {"message": "General settings updated"}

@router.patch("/ai")
async def update_ai_settings(
    update: AIConfigUpdate,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update AI provider settings with encryption"""
    from sqlalchemy.orm.attributes import flag_modified
    
    result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
    settings_obj = result.scalars().first()
    if not settings_obj:
        settings_obj = UserSettings(user_id=identity.user_id, ai_config={})
        db.add(settings_obj)
    
    current_config = dict(settings_obj.ai_config) if settings_obj.ai_config else {}
    
    for key_name in ["gemini_api_key", "openai_api_key", "anthropic_api_key"]:
        key_value = getattr(update, key_name, None)
        if key_value and key_value != "********":
            current_config[key_name] = encrypt_string(key_value)

    if update.default_model is not None:
        current_config["default_model"] = update.default_model

    settings_obj.ai_config = current_config
    # Force SQLAlchemy to detect the JSON change
    flag_modified(settings_obj, "ai_config")
    await db.commit()
    return {"message": "AI settings updated"}

@router.post("/services", response_model=ServiceResponse)
async def register_service(
    reg: ServiceRegister,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Register or update a microservice connection"""
    if reg.service_name == "lbs":
        raise HTTPException(
            status_code=403,
            detail="LBS is managed by the server administrator (.env + server-issued key) and cannot be changed from UI.",
        )

    # Check if exists
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == identity.user_id,
        ServiceRegistry.service_name == reg.service_name
    ))
    service = result.scalars().first()
    
    encrypted_key = encrypt_string(reg.api_key) if reg.api_key else None
    
    if service:
        if reg.base_url:
            service.base_url = reg.base_url
        if encrypted_key:
            service.api_key_encrypted = encrypted_key
        if reg.config is not None:
            service.config = reg.config
            flag_modified(service, "config")
        if reg.is_active is not None:
            service.is_active = reg.is_active
    else:
        service = ServiceRegistry(
            user_id=identity.user_id,
            service_name=reg.service_name,
            base_url=reg.base_url or "local",
            api_key_encrypted=encrypted_key,
            config=reg.config or {},
            is_active=reg.is_active if reg.is_active is not None else True,
        )
        db.add(service)
    
    await db.commit()
    await db.refresh(service)

    # Refresh core + integration definitions so new/changed services reflect in tool/skill registry.
    try:
        import asyncio
        from shared.database import get_engine as _get_engine
        from domains.orchestration2.bootstrap.definition_refresh_service import (
            refresh_core_sync,
            refresh_integrations,
        )
        await asyncio.to_thread(refresh_core_sync, _get_engine(), identity.user_id)
        await refresh_integrations(identity.user_id, db)
    except Exception as _exc:
        logger.warning("Definition refresh after service register failed: %s", _exc)

    return service

@router.post("/test-connection")
async def test_connection(
    test: ConnectionTest,
    identity: Identity = Depends(resolve_identity)
):
    """Test a connection to an external service (like LBS) using Base URL and API Key"""
    base_url = test.base_url
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
    
    # Smart health check pathing: strip common API path suffixes for the health check
    health_base = base_url.rstrip("/")
    for suffix in ["/api/lbs", "/api/v1", "/v1"]:
        if health_base.endswith(suffix):
            health_base = health_base[:-len(suffix)]
            break
            
    health_url = f"{health_base.rstrip('/')}/health"
    headers = {"x-api-key": test.api_key}
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url, headers=headers)
            if resp.status_code == 200:
                return {"status": "success", "message": "Connection successful"}
            else:
                return {"status": "error", "message": f"Service returned status {resp.status_code}"}
    except Exception as e:
        return {"status": "error", "message": f"Could not reach service: {str(e)}"}

@router.get("/services/{service_id}/health")
async def check_service_health(
    service_id: int,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Trigger a health check for a service"""
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.id == service_id,
        ServiceRegistry.user_id == identity.user_id
    ))
    service = result.scalars().first()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    base_url = service.base_url
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
        
    # Smart health check pathing: strip common API path suffixes for the health check
    health_base = base_url
    for suffix in ["/api/lbs", "/api/v1", "/v1"]:
        if health_base.endswith(suffix):
            health_base = health_base[:-len(suffix)]
            break
            
    health_url = f"{health_base.rstrip('/')}/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url)
            status_code = resp.status_code
            if status_code == 200:
                service.health_status = "healthy"
            else:
                service.health_status = f"error_{status_code}"
    except Exception as e:
        service.health_status = "unreachable"
        
    service.last_health_check = datetime.utcnow()
    await db.commit()
    return {"status": service.health_status, "last_check": service.last_health_check}

@router.post("/account/password")
async def change_password(
    pc: PasswordChange,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Change the current user's password"""
    result = await db.execute(select(User).filter(User.id == identity.user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not verify_password(pc.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid current password")
    
    user.password_hash = hash_password(pc.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}

@router.get("/status")
async def get_system_status(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Check if all mandatory services (at least one LLM, LBS, KnowledgeCore) are configured"""
    # 1. Check LLM providers
    result = await db.execute(select(UserSettings).filter(UserSettings.user_id == identity.user_id))
    settings_obj = result.scalars().first()
    gemini_configured = False
    openai_configured = False
    anthropic_configured = False
    configured_providers: list[str] = []
    if settings_obj and settings_obj.ai_config:
        if settings_obj.ai_config.get("gemini_api_key"):
            gemini_configured = True
            configured_providers.append("gemini")
        if settings_obj.ai_config.get("openai_api_key"):
            openai_configured = True
            configured_providers.append("openai")
        if settings_obj.ai_config.get("anthropic_api_key"):
            anthropic_configured = True
            configured_providers.append("anthropic")

    llm_configured = gemini_configured or openai_configured or anthropic_configured

    # 2. Check Services
    result = await db.execute(select(ServiceRegistry).filter(ServiceRegistry.user_id == identity.user_id))
    services = result.scalars().all()
    
    status_map = {
        "llm": {
            "configured": llm_configured,
            "providers": configured_providers,
        },
        "lbs": {"configured": False, "url": None},
        "knowledge_core": {"configured": False, "url": None}
    }
    
    for s in services:
        if s.service_name in status_map:
            status_map[s.service_name]["configured"] = True
            status_map[s.service_name]["url"] = s.base_url
    
    # Overall summary
    all_mandatory_met = llm_configured and status_map["lbs"]["configured"] and status_map["knowledge_core"]["configured"]
    
    return {
        "all_mandatory_met": all_mandatory_met,
        "details": status_map
    }
