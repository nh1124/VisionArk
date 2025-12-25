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
    """Async message buffer from Spokes to Hub (per-user)"""
    __tablename__ = "inbox_queue"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, index=True)  # Owner user
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
    
    # Relationships
    nodes = relationship("Node", back_populates="user", cascade="all, delete-orphan")
    service_connections = relationship("ServiceRegistry", back_populates="user", cascade="all, delete-orphan")


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


class UserSettings(Base):
    """User-specific configurations and AI provider keys"""
    __tablename__ = "user_settings"
    
    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    ai_config = Column(JSON, default=dict)        # { "gemini_api_key": "...", "openai_api_key": "...", "default_model": "..." }
    general_settings = Column(JSON, default=dict) # { "theme": "dark", "language": "en" }
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ServiceRegistry(Base):
    """Registry of connected microservices (LBS, Knowledge Core, etc.)"""
    __tablename__ = "service_registry"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    service_name = Column(String(100), nullable=False) # e.g., "lbs", "knowledge_core"
    base_url = Column(String(255), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)    # Optional - stored encrypted
    remote_user_id = Column(String(100), nullable=True)  # User ID in the remote service (for user mapping)
    is_active = Column(Boolean, default=True)
    last_health_check = Column(DateTime, nullable=True)
    health_status = Column(String(50), nullable=True)  # "healthy", "unreachable", "error"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Relationship
    user = relationship("User", back_populates="service_connections")


class ExternalIdentity(Base):
    """Linked identities from external systems (for SSO and cross-service sync)"""
    __tablename__ = "external_identities"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    issuer = Column(String(255), nullable=False)   # e.g., "google", "lbs"
    subject = Column(String(255), nullable=False)  # The unique ID in the external system
    linked_at = Column(DateTime, default=datetime.utcnow)
    last_login_at = Column(DateTime, nullable=True)


class Node(Base):
    """Agent Nodes (Contexts) - HUB or SPOKE"""
    __tablename__ = "nodes"
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # Slug
    display_name = Column(String(200), nullable=False)
    node_type = Column(String(50), nullable=False)  # HUB, SPOKE
    lbs_access_level = Column(String(50), default="READ_ONLY")  # READ_ONLY, WRITE
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="nodes")
    sessions = relationship("ChatSession", back_populates="node", cascade="all, delete-orphan")
    files = relationship("UploadedFile", back_populates="node", cascade="all, delete-orphan")
    profiles = relationship("AgentProfile", back_populates="node", cascade="all, delete-orphan")


class AgentProfile(Base):
    """Agent Persona and configuration"""
    __tablename__ = "agent_profiles"
    
    id = Column(String(36), primary_key=True)
    node_id = Column(String(36), ForeignKey("nodes.id"), nullable=False, index=True)
    version = Column(Integer, default=1)
    system_prompt = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    node = relationship("Node", back_populates="profiles")


class ChatSession(Base):
    """Grouped conversation history"""
    __tablename__ = "chat_sessions"
    
    id = Column(String(36), primary_key=True)
    node_id = Column(String(36), ForeignKey("nodes.id"), nullable=False, index=True)
    parent_session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=True)
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    # Relationships
    node = relationship("Node", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    parent = relationship("ChatSession", remote_side=[id], backref="child_sessions")


class ChatMessage(Base):
    """Structured message logs"""
    __tablename__ = "chat_messages"
    
    id = Column(String(36), primary_key=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    meta_payload = Column(JSON, nullable=True)  # Action data / Tool calls
    is_excluded = Column(Boolean, default=False)  # Hide from context
    token_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    session = relationship("ChatSession", back_populates="messages")


class UploadedFile(Base):
    """Files associated with a Node (Local RAG)"""
    __tablename__ = "uploaded_files"
    
    id = Column(String(36), primary_key=True)
    node_id = Column(String(36), ForeignKey("nodes.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    vector_status = Column(String(50), default="PENDING")  # PENDING, COMPLETED
    kc_sync_status = Column(String(50), default="PENDING")  # PENDING, SYNCED
    gemini_file_uri = Column(String(512), nullable=True)   # Gemini File API URI
    gemini_file_name = Column(String(255), nullable=True)  # Gemini file name reference
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    node = relationship("Node", back_populates="files")
    chunks = relationship("FileChunk", back_populates="file", cascade="all, delete-orphan")


class FileChunk(Base):
    """Vectorized chunks of files for RAG"""
    __tablename__ = "file_chunks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    file_id = Column(String(36), ForeignKey("uploaded_files.id"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    # embedding column would be added via pgvector migration if needed, 
    # but let's stick to core SQL for now or use a placeholder
    # embedding = Column(Vector(1536)) # requires pgvector
    metadata_json = Column(JSON, nullable=True)
    
    # Relationship
    file = relationship("UploadedFile", back_populates="chunks")


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
    """Initialize database tables and run migrations"""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    
    # Run schema migrations for existing tables
    _run_migrations(engine)
    
    return engine


def _run_migrations(engine):
    """Run schema migrations to update existing tables"""
    from sqlalchemy import text, inspect
    
    inspector = inspect(engine)
    
    # Migration: Add remote_user_id to service_registry if missing
    if 'service_registry' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('service_registry')]
        if 'remote_user_id' not in columns:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE service_registry ADD COLUMN remote_user_id VARCHAR(100)"
                ))
                conn.commit()
                print("✅ Migration: Added remote_user_id column to service_registry")
    
    # Migration: Add Gemini File API columns to uploaded_files if missing
    if 'uploaded_files' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('uploaded_files')]
        if 'gemini_file_uri' not in columns:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE uploaded_files ADD COLUMN gemini_file_uri VARCHAR(512)"
                ))
                conn.execute(text(
                    "ALTER TABLE uploaded_files ADD COLUMN gemini_file_name VARCHAR(255)"
                ))
                conn.commit()
                print("✅ Migration: Added Gemini File API columns to uploaded_files")


def get_session(engine):
    """Get database session"""
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
