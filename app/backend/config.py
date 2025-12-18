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
