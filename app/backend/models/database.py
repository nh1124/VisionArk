"""
Database models for AI TaskManagement OS
Implements the LBS (Load Balancing System) schema from BLUEPRINT.md
"""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, Text, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from enum import Enum

Base = declarative_base()


class RuleType(str, Enum):
    """Task recurrence rule types"""
    ONCE = "ONCE"
    WEEKLY = "WEEKLY"
    EVERY_N_DAYS = "EVERY_N_DAYS"
    MONTHLY_DAY = "MONTHLY_DAY"
    MONTHLY_NTH_WEEKDAY = "MONTHLY_NTH_WEEKDAY"


class ExceptionType(str, Enum):
    """Task exception types"""
    SKIP = "SKIP"
    OVERRIDE_LOAD = "OVERRIDE_LOAD"
    FORCE_DO = "FORCE_DO"


class TaskStatus(str, Enum):
    """Task execution status"""
    PLANNED = "planned"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class InboxQueue(Base):
    """Async message buffer from Spokes to Hub"""
    __tablename__ = "inbox_queue"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source_spoke = Column(String, nullable=False)
    message_type = Column(String, nullable=False)  # share, complete, alert
    payload = Column(JSON, nullable=False)  # Structured <meta-action> data
    is_processed = Column(Boolean, default=False)
    received_at = Column(DateTime, default=datetime.utcnow)
    processed_at = Column(DateTime, nullable=True)
    error_log = Column(Text, nullable=True)


class User(Base):
    """User account for authentication"""
    __tablename__ = "users"
    
    id = Column(String(36), primary_key=True)                # UUID
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True, index=True)  # Optional but unique
    password_hash = Column(Text, nullable=False)             # bcrypt hash
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)


class APIKey(Base):
    """API Key for authentication (Phase 2) - stores hashed keys only"""
    __tablename__ = "api_keys"
    
    id = Column(String(36), primary_key=True)               # UUID
    key_hash = Column(Text, nullable=False, index=True)     # HMAC-SHA256 hash (never plaintext)
    user_id = Column(String(36), nullable=False, index=True)  # Owner UUID
    client_id = Column(String(100), nullable=False)         # e.g., "hub-agent", "spoke-research"
    name = Column(String(100), nullable=True)               # Human-readable label
    scopes = Column(JSON, default=list)                     # ["tasks:read", "tasks:write", "*"]
    is_active = Column(Boolean, default=False)              # Phase 2: set to True when issued
    created_at = Column(DateTime, default=datetime.utcnow)
    revoked_at = Column(DateTime, nullable=True)            # When key was revoked
    last_used_at = Column(DateTime, nullable=True)          # Last successful auth


# Database setup utilities
def get_engine(db_url: str = None):
    """Get database engine - requires DATABASE_URL to be set"""
    if db_url is None:
        from config import settings
        
        if not settings.database_url:
            raise ValueError(
                "DATABASE_URL is required. Set it in .env file.\n"
                "Example: DATABASE_URL=postgresql://user:pass@localhost:5432/atmos"
            )
        db_url = settings.database_url
    
    return create_engine(db_url, echo=False)


def init_database(database_url: str = None):
    """Initialize database tables"""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def get_session(engine):
    """Get database session"""
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
