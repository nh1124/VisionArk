from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from functools import lru_cache
from typing import Optional, Any
import os

class Settings(BaseSettings):
    """Application settings using Pydantic Settings and .env"""
    
    # API Settings
    backend_port: int = 8000
    frontend_port: int = 3000
    host: str = "127.0.0.1"  # Default to localhost for security; set to 0.0.0.0 for Docker
    lbs_service_url: str = "http://localhost:8001/api/lbs"
    knowledge_core_url: str = "http://localhost:8200"
    
    # Auth Settings (Legacy API Key - Phase 2)
    atmos_env: str = "dev"                    # dev | prod
    atmos_service_key: str = ""               # Shared key for service-to-service auth
    atmos_default_user_id: str = "00000000-0000-0000-0000-000000000001"  # Dev fallback user
    atmos_api_key_pepper: str = "dev_pepper_change_in_prod"  # HMAC secret (MUST change in prod)
    
    # JWT Settings (Phase 1 Session Auth)
    jwt_secret_key: str = "dev_jwt_secret_change_in_production_must_be_32_chars"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours
    
    # Database Settings (PostgreSQL required)
    database_url: str = ""  # postgresql://user:pass@host:5432/dbname
    
    # LLM Settings
    max_tool_turns: Optional[int] = 30
    
    @field_validator("max_tool_turns", mode="before")
    @classmethod
    def parse_optional_int(cls, v: Any) -> Optional[int]:
        """Coerce string 'None' or 'null' to None, else cast to int if needed"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.lower() in ("none", "null", ""):
                return None
            try:
                return int(v)
            except ValueError:
                return None
        return v
    
    # Model configuration
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(__file__), "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

@lru_cache()
def get_settings():
    """Create and cache settings instance"""
    return Settings()

# Global settings instance
settings = get_settings()
