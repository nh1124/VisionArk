"""
JWT token utilities for session authentication
"""
from datetime import datetime, timedelta
from typing import Optional
from jose import jwt, JWTError

from app.config import settings


def create_access_token(
    user_id: str, 
    username: str, 
    expires_delta: Optional[timedelta] = None,
    token_type: str = "access"
) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: User's UUID
        username: User's username
        expires_delta: Custom expiration time (default: from settings)
        
    Returns:
        Encoded JWT token string
    """
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    
    expire = datetime.utcnow() + expires_delta
    
    payload = {
        "sub": user_id,
        "username": username,
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": token_type
    }
    
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, required_type: Optional[str] = "access") -> Optional[dict]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: JWT token string
        required_type: If provided, ensures the token has this 'type'
        
    Returns:
        Token payload dict if valid, None if invalid/expired
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        # Verify token type if required
        if required_type and payload.get("type") != required_type:
            return None
            
        return payload
    except JWTError:
        return None


def decode_access_token(token: str) -> Optional[dict]:
    """
    Legacy wrapper for decoding standard access tokens.
    """
    return decode_token(token, required_type="access")
