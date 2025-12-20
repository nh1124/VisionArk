from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache
import os

class Settings(BaseSettings):
    """Application settings using Pydantic Settings and .env"""
    
    # API Settings
    backend_port: int = 8000
    frontend_port: int = 3000
    host: str = "0.0.0.0"
    debug: bool = True
    
    # Auth Settings
    atmos_env: str = "dev"                    # dev | prod
    atmos_require_api_key: bool = False       # True in prod, False allows dev fallback
    atmos_enable_legacy_env_key: bool = True  # Allow env-based key during migration
    atmos_default_user_id: str = "00000000-0000-0000-0000-000000000001"  # Dev fallback user
    atmos_api_key_pepper: str = "dev_pepper_change_in_prod"  # HMAC secret (MUST change in prod)
    
    # Database Settings
    database_url: str = ""  # PostgreSQL: postgresql://user:pass@host:5432/dbname, empty = SQLite
    
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
