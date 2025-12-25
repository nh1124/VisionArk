from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from pydantic import BaseModel, Field
from datetime import datetime
import httpx

from models.database import User, UserSettings, ServiceRegistry, ExternalIdentity
from services.auth import get_db, resolve_identity, Identity
from utils.password import hash_password, verify_password
from utils.encryption import encrypt_string, decrypt_string
from config import settings

router = APIRouter(prefix="/api/settings", tags=["Settings"])

# --- Schemas ---

class AIConfigUpdate(BaseModel):
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    default_model: Optional[str] = None

class ServiceRegister(BaseModel):
    service_name: str
    base_url: str
    api_key: Optional[str] = None

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
    
class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class SettingsSummary(BaseModel):
    ai_config: Dict
    services: List[ServiceResponse]
    integrations: List[Dict]

# --- Endpoints ---

@router.get("", response_model=SettingsSummary)
def get_settings(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get all user settings, services, and integrations"""
    # 1. AI Config
    settings = db.query(UserSettings).filter(UserSettings.user_id == identity.user_id).first()
    ai_config = settings.ai_config if settings else {}
    
    # Mask API keys in response
    masked_ai_config = ai_config.copy()
    for key in ["gemini_api_key"]:
        if masked_ai_config.get(key):
            masked_ai_config[key] = "********"
            
    # 2. Services
    services = db.query(ServiceRegistry).filter(ServiceRegistry.user_id == identity.user_id).all()
    
    # 3. Integrations
    integrations = db.query(ExternalIdentity).filter(ExternalIdentity.user_id == identity.user_id).all()
    integration_list = [
        {"issuer": i.issuer, "subject": i.subject, "linked_at": i.linked_at}
        for i in integrations
    ]
    
    return {
        "ai_config": masked_ai_config,
        "services": services,
        "integrations": integration_list
    }

@router.patch("/ai")
def update_ai_settings(
    update: AIConfigUpdate,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Update AI provider settings with encryption"""
    from sqlalchemy.orm.attributes import flag_modified
    
    settings = db.query(UserSettings).filter(UserSettings.user_id == identity.user_id).first()
    if not settings:
        settings = UserSettings(user_id=identity.user_id, ai_config={})
        db.add(settings)
    
    current_config = dict(settings.ai_config) if settings.ai_config else {}
    
    if update.gemini_api_key:
        # Only update if it's not the masked value
        if update.gemini_api_key != "********":
            encrypted = encrypt_string(update.gemini_api_key)
            current_config["gemini_api_key"] = encrypted
        
    settings.ai_config = current_config
    # Force SQLAlchemy to detect the JSON change
    flag_modified(settings, "ai_config")
    db.commit()
    return {"message": "AI settings updated"}

@router.post("/services", response_model=ServiceResponse)
def register_service(
    reg: ServiceRegister,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Register or update a microservice connection"""
    # Check if exists
    service = db.query(ServiceRegistry).filter(
        ServiceRegistry.user_id == identity.user_id,
        ServiceRegistry.service_name == reg.service_name
    ).first()
    
    encrypted_key = encrypt_string(reg.api_key) if reg.api_key else None
    
    if service:
        service.base_url = reg.base_url
        if encrypted_key:
            service.api_key_encrypted = encrypted_key
    else:
        service = ServiceRegistry(
            user_id=identity.user_id,
            service_name=reg.service_name,
            base_url=reg.base_url,
            api_key_encrypted=encrypted_key
        )
        db.add(service)
    
    db.commit()
    db.refresh(service)
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
    
    health_url = f"{base_url.rstrip('/')}/health"
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
    db: Session = Depends(get_db)
):
    """Trigger a health check for a service"""
    service = db.query(ServiceRegistry).filter(
        ServiceRegistry.id == service_id,
        ServiceRegistry.user_id == identity.user_id
    ).first()
    
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    
    base_url = service.base_url
    if not base_url.startswith("http"):
        base_url = f"http://{base_url}"
        
    health_url = f"{base_url.rstrip('/')}/health"
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
    db.commit()
    return {"status": service.health_status, "last_check": service.last_health_check}

@router.post("/account/password")
def change_password(
    pc: PasswordChange,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Change the current user's password"""
    user = db.query(User).filter(User.id == identity.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    if not verify_password(pc.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid current password")
    
    user.password_hash = hash_password(pc.new_password)
    db.commit()
    return {"message": "Password changed successfully"}
