"""
Authentication service for session-based auth (Phase 1)
Supports JWT tokens for UI users, with API key fallback for Phase 2
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from fastapi import Header, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from models.database import get_engine, get_session, User, APIKey
from utils.jwt import decode_access_token
from utils.security import hash_api_key
from config import settings

logger = logging.getLogger(__name__)

# HTTP Bearer token scheme for JWT
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class Identity:
    """Resolved identity from authentication"""
    user_id: str
    username: str
    scopes: List[str]
    auth_method: str  # "jwt" | "api_key" | "dev_fallback"
    warnings: List[str] = field(default_factory=list)
    
    def has_scope(self, required_scope: str) -> bool:
        """Check if identity has a specific scope"""
        if "*" in self.scopes:
            return True
        if required_scope in self.scopes:
            return True
        # Check wildcard scopes (e.g., "admin:*" covers "admin:dump")
        scope_prefix = required_scope.split(":")[0]
        if f"{scope_prefix}:*" in self.scopes:
            return True
        return False


def get_db():
    """Get database session dependency"""
    engine = get_engine()
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()


def resolve_identity(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-KEY"),
    x_service_key: Optional[str] = Header(None, alias="X-SERVICE-KEY"),
    x_user_id: Optional[str] = Header(None, alias="X-USER-ID"),
    db: Session = Depends(get_db)
) -> Identity:
    """
    Resolve identity from Service Key, JWT token, API key, or dev fallback.
    
    Authentication order:
    1. X-SERVICE-KEY (Internal, Phase 4)
    2. Authorization: Bearer <JWT> (primary, Phase 1)
    3. X-API-KEY header (Phase 2, for external clients)
    4. Dev fallback (if ATMOS_ENV=dev)
    """
    warnings = []

    # 1. Try Service Key authentication (Internal peer-to-peer)
    if x_service_key and settings.atmos_service_key and x_service_key == settings.atmos_service_key:
        # Service is authentic. Use provided X-User-ID or fallback to a system ID.
        user_id = x_user_id or "system-service"
        logger.debug(f"Service auth successful. Acting as user: {user_id}")
        return Identity(
            user_id=user_id,
            username="InternalService",
            scopes=["*"],
            auth_method="service"
        )
    
    # 2. Try JWT token authentication (Phase 1 primary)
    if credentials and credentials.credentials:
        token = credentials.credentials
        payload = decode_access_token(token)
        
        if payload:
            user_id = payload.get("sub")
            username = payload.get("username")
            
            # Verify user still exists and is active
            user = db.query(User).filter(
                User.id == user_id,
                User.is_active == True
            ).first()
            
            if user:
                logger.debug(f"JWT auth successful: user={username}")
                return Identity(
                    user_id=user_id,
                    username=username,
                    scopes=["*"],  # Full access for authenticated users in Phase 1
                    auth_method="jwt"
                )
            else:
                logger.warning(f"JWT token for inactive/deleted user: {user_id}")
        
        # Invalid token
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token"
        )
    
    # 2. Try API key authentication (Phase 2 - for external clients)
    if x_api_key:
        key_hash = hash_api_key(x_api_key)
        api_key = db.query(APIKey).filter(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True
        ).first()
        
        if api_key:
            # Update last_used_at
            api_key.last_used_at = datetime.utcnow()
            db.commit()
            
            logger.debug(f"API key auth successful: client={api_key.client_id}")
            return Identity(
                user_id=api_key.user_id,
                username=api_key.client_id,
                scopes=api_key.scopes or [],
                auth_method="api_key"
            )
        else:
            logger.warning("Invalid API key attempted")
            raise HTTPException(
                status_code=401,
                detail="Invalid or revoked API key"
            )
    
    # 3. Dev fallback mode (only in dev environment)
    if settings.atmos_env == "dev":
        logger.warning("DEV_FALLBACK: No auth provided, using default user")
        warnings.append("dev_fallback_used")
        
        return Identity(
            user_id=settings.atmos_default_user_id,
            username="dev_user",
            scopes=["*"],  # Full access in dev mode
            auth_method="dev_fallback",
            warnings=warnings
        )
    
    # No authentication provided and not in dev mode
    raise HTTPException(
        status_code=401,
        detail="Authentication required. Provide Authorization: Bearer <token>"
    )


def require_scope(required_scope: str):
    """
    Dependency factory for scope-based authorization.
    
    Usage:
        @router.get("/admin/dump")
        def dump(identity: Identity = Depends(require_scope("admin:dump"))):
            ...
    """
    def scope_checker(identity: Identity = Depends(resolve_identity)) -> Identity:
        if not identity.has_scope(required_scope):
            logger.warning(f"Scope denied: {identity.username} missing {required_scope}")
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient permissions. Required scope: {required_scope}"
            )
        return identity
    return scope_checker


# Convenience dependencies for common scope requirements
require_tasks_read = require_scope("tasks:read")
require_tasks_write = require_scope("tasks:write")
require_admin = require_scope("admin:*")
