"""
Security utilities for API key authentication
HMAC-SHA256 hashing with pepper for secure key storage
"""
import hmac
import hashlib
import secrets
from typing import Optional


def get_pepper() -> bytes:
    """Get the pepper secret from settings (lazy import to avoid circular imports)"""
    from config import settings
    return settings.atmos_api_key_pepper.encode()


def hash_api_key(api_key: str) -> str:
    """
    Hash API key with HMAC-SHA256 using pepper.
    
    Args:
        api_key: The raw API key to hash
        
    Returns:
        Hex-encoded HMAC-SHA256 hash
    """
    pepper = get_pepper()
    return hmac.new(pepper, api_key.encode(), hashlib.sha256).hexdigest()


def verify_api_key(api_key: str, stored_hash: str) -> bool:
    """
    Verify API key using constant-time comparison.
    
    Args:
        api_key: The raw API key to verify
        stored_hash: The stored hash to compare against
        
    Returns:
        True if keys match, False otherwise
    """
    computed = hash_api_key(api_key)
    return hmac.compare_digest(computed, stored_hash)


def generate_api_key(prefix: str = "atmos") -> str:
    """
    Generate a secure random API key.
    
    Args:
        prefix: Prefix for the key (default: "atmos")
        
    Returns:
        A secure random API key in format: <prefix>_<random_token>
    """
    return f"{prefix}_{secrets.token_urlsafe(32)}"
