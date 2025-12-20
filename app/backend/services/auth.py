"""
Authentication service for API key-based auth
Central dependency for all protected endpoints
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from fastapi import Header, HTTPException, Depends
from sqlalchemy.orm import Session

from models.database import get_engine, get_session, APIKey
from utils.security import hash_api_key
from config import settings

logger = logging.getLogger(__name__)


@dataclass
class Identity:
    """Resolved identity from authentication"""
    user_id: str
    client_id: str
    scopes: List[str]
    auth_method: str  # "api_key" | "dev_fallback" | "legacy_env_key"
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
    x_api_key: Optional[str] = Header(None, alias="X-API-KEY"),
    db: Session = Depends(get_db)
) -> Identity:
    """
    Resolve identity from API key or dev fallback.
    
    This is the central authentication dependency for all protected endpoints.
    
    Authentication order:
    1. X-API-KEY header (primary, DB lookup)
    2. Dev fallback (if ATMOS_REQUIRE_API_KEY=false)
    
    Returns:
        Identity object with user_id, client_id, scopes, auth_method
        
    Raises:
        HTTPException 401: If API key is required but not provided/invalid
    """
    warnings = []
    
    # Try API key authentication
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
                client_id=api_key.client_id,
                scopes=api_key.scopes or [],
                auth_method="api_key"
            )
        else:
            # Invalid or revoked key
            logger.warning(f"Invalid API key attempted")
            raise HTTPException(
                status_code=401,
                detail="Invalid or revoked API key"
            )
    
    # No API key provided - check if required
    if settings.atmos_require_api_key:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide X-API-KEY header."
        )
    
    # Dev fallback mode
    logger.warning("DEV_FALLBACK: No API key provided, using default user")
    warnings.append("dev_fallback_used")
    
    return Identity(
        user_id=settings.atmos_default_user_id,
        client_id="dev_fallback",
        scopes=["*"],  # Full access in dev mode
        auth_method="dev_fallback",
        warnings=warnings
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
            logger.warning(f"Scope denied: {identity.client_id} missing {required_scope}")
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
