"""
Database models for AI TaskManagement OS
Implements the LBS (Load Balancing System) schema from BLUEPRINT.md
"""
from datetime import datetime, date
from typing import Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, Boolean, Date, DateTime, Text, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
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


class NodeType(str, Enum):
    """Node type for agent categorization"""
    SYSTEM = "SYSTEM"       # System nodes (router, memory, etc.)
    PROJECT = "PROJECT"     # Main project orchestrator
    MEMBER = "MEMBER"       # Project member agents


class ProjectStatus(str, Enum):
    """Project status"""
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class ScheduledTaskStatus(str, Enum):
    """Status for automated system tasks"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalStatus(str, Enum):
    """Status for HITL approval requests"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    FAILED = "failed"


class ScheduledTask(Base):
    """Automated Execution System (AES) tasks (timers, recurring, etc.)"""
    __tablename__ = "scheduled_tasks"
    
    id = Column(String(36), primary_key=True)               # UUID
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    task_type = Column(String(50), nullable=False)          # e.g., "HARD_DELETE", "AUTO_RESEARCH"
    payload = Column(JSON, default=dict)                    # Arguments for the task
    scheduled_at = Column(DateTime, nullable=False, index=True)
    recurring_rule = Column(String(100), nullable=True)     # Cron format or similar
    status = Column(String(20), default="pending", index=True)
    last_run_at = Column(DateTime, nullable=True)
    error_log = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    project = relationship("Project")


class ApprovalRequest(Base):
    """Pending actions requiring Human-in-the-Loop approval"""
    __tablename__ = "approval_requests"

    id = Column(String(36), primary_key=True)               # UUID
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False)         # e.g. "run_safe_shell"
    payload = Column(JSON, nullable=False)                  # Arguments like {"command": "dir"}
    status = Column(String(20), default="pending", index=True)
    response = Column(JSON, nullable=True)                  # Execution result
    error_log = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project")
    user = relationship("User")




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
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
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

    @property
    def gemini_api_key(self) -> Optional[str]:
        """Automatically decrypt and return the Gemini API key"""
        if not self.ai_config:
            print("[UserSettings] ai_config is empty/None")
            return None
            
        encrypted_key = self.ai_config.get("gemini_api_key")
        if not encrypted_key:
             print("[UserSettings] gemini_api_key missing in ai_config")
             return None
        
        if encrypted_key == "********":
             print("[UserSettings] Key is masked '********' (not real key)")
             return None
            
        from utils.encryption import decrypt_string
        try:
            val = decrypt_string(encrypted_key)
            if not val:
                 print("[UserSettings] Decrypted key is empty")
            return val
        except Exception as e:
            print(f"[UserSettings] Decryption failed: {e}")
            return None


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
    
    @property
    def api_key(self) -> Optional[str]:
        """Automatically decrypt and return the service API key"""
        if not self.api_key_encrypted:
            return None
            
        from utils.encryption import decrypt_string
        try:
            return decrypt_string(self.api_key_encrypted)
        except Exception:
            return None
    
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


class Project(Base):
    """Project/Workspace - container for nodes, sessions, and files"""
    __tablename__ = "projects"
    
    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)  # Display name
    strategy_id = Column(String(36), nullable=True)  # Optional strategy reference
    status = Column(String(20), default="active")  # active/paused/archived
    priority = Column(Integer, default=3)  # 1-5, default 3
    review_cadence = Column(String(50), nullable=True)  # Review schedule
    lbs_access_level = Column(String(50), default="READ_ONLY")  # READ_ONLY, WRITE
    notes = Column(Text, nullable=True)  # Project notes
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="projects")
    nodes = relationship("Node", back_populates="project", cascade="all, delete-orphan")
    sessions = relationship("ChatSession", back_populates="project", cascade="all, delete-orphan")
    files = relationship("UploadedFile", back_populates="project", cascade="all, delete-orphan")


class Node(Base):
    """Agent node - contains agent configuration and prompt"""
    __tablename__ = "nodes"
    
    id = Column(String(36), primary_key=True)  # UUID
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)  # Null for SYSTEM nodes
    parent_node_id = Column(String(36), ForeignKey("nodes.id"), nullable=True)  # Hierarchy for member nodes
    node_type = Column(String(20), default="PROJECT")  # SYSTEM/PROJECT/MEMBER
    role_name = Column(String(50), nullable=True)  # e.g. "orchestrator", "researcher"
    display_name = Column(String(200), nullable=False, index=True)
    description = Column(String(500), nullable=True)  # Short summary of expertise
    system_prompt = Column(Text, nullable=True)  # Agent prompt
    tools = Column(JSON, default=list)  # List of tool names
    meta_payload = Column(JSON, default=dict)  # Metadata for dynamic behavior (e.g. trigger_patterns)
    status = Column(String(20), default="active")  # active/paused/archived
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="nodes")
    parent = relationship("Node", remote_side=[id], backref="children")

    from sqlalchemy import UniqueConstraint
    __table_args__ = (
        UniqueConstraint('project_id', 'role_name', name='uix_project_role'),
    )



class ChatSession(Base):
    """Grouped conversation history"""
    __tablename__ = "chat_sessions"
    
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    parent_session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=True)
    title = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    is_archived = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="sessions")
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


class ArchivedContext(Base):
    """Archived conversation contexts and summaries"""
    __tablename__ = "archived_contexts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    node_id = Column(String(36), ForeignKey("nodes.id"), nullable=True, index=True)
    archived_at = Column(DateTime, default=datetime.utcnow)
    summary_path = Column(Text, nullable=True)
    log_path = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)
    
    # Relationships
    user = relationship("User")
    project = relationship("Project")
    node = relationship("Node")


class RagMetadata(Base):
    """Tracking metadata for RAG-indexed files"""
    __tablename__ = "rag_metadata"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_hash = Column(String(128), nullable=True)
    indexed_at = Column(DateTime, default=datetime.utcnow)
    chunk_count = Column(Integer, default=0)
    
    # Relationship
    project = relationship("Project")


class UploadedFile(Base):
    """Files associated with a Project"""
    __tablename__ = "uploaded_files"
    
    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    storage_path = Column(String(512), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    vector_status = Column(String(50), default="PENDING")  # PENDING, COMPLETED
    kc_sync_status = Column(String(50), default="PENDING")  # PENDING, SYNCED
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="files")
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
    # Remove as columns are removed from model
    pass

    # Migration: Create approval_requests table is handled by create_all, but check if we need to manually add it?
    # No, Base.metadata.create_all handles new tables.
    pass

    # Migration: Add role_name, display_name, tools to agent_profiles if missing
    if 'agent_profiles' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('agent_profiles')]
        if 'role_name' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE agent_profiles ADD COLUMN role_name VARCHAR(50)"))
                conn.execute(text("ALTER TABLE agent_profiles ADD COLUMN display_name VARCHAR(200)"))
                conn.execute(text("ALTER TABLE agent_profiles ADD COLUMN tools JSON"))
                conn.commit()
                print("[INFO] Migration: Added role_name, display_name, and tools columns to agent_profiles")

    # Migration: Add description to nodes if missing
    if 'nodes' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('nodes')]
        if 'description' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN description VARCHAR(500)"))
                conn.commit()
                print("[INFO] Migration: Added description column to nodes")
    
    # Migration: Add meta_payload to nodes if missing
    if 'nodes' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('nodes')]
        if 'meta_payload' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE nodes ADD COLUMN meta_payload JSON"))
                conn.commit()
                print("[INFO] Migration: Added meta_payload column to nodes")
    # Migration: Rename project_name/source_project to project_id in multiple tables
    for table, old_col, new_col in [
        ('rag_metadata', 'project_name', 'project_id'),
        ('archived_contexts', 'project_name', 'project_id'),
    ]:
        if table in inspector.get_table_names():
            columns = [col['name'] for col in inspector.get_columns(table)]
            if old_col in columns and new_col not in columns:
                with engine.connect() as conn:
                    try:
                        conn.execute(text(f"ALTER TABLE {table} RENAME COLUMN {old_col} TO {new_col}"))
                        conn.commit()
                        print(f"[INFO] Migration: Renamed {old_col} to {new_col} in {table}")
                    except Exception as e:
                        print(f"[ERROR] Migration: Failed to rename {old_col} to {new_col} in {table}: {str(e)}")
    # Migration: Add unique constraint uix_project_role to nodes if missing
    if 'nodes' in inspector.get_table_names():
        constraints = inspector.get_unique_constraints('nodes')
        if not any(c['name'] == 'uix_project_role' for c in constraints):
            with engine.connect() as conn:
                try:
                    # Note: Using IF NOT EXISTS for extra safety
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uix_project_role ON nodes (COALESCE(project_id, 'SYSTEM'), role_name)"))
                    conn.commit()
                    print("[INFO] Migration: Added unique index uix_project_role to nodes")
                except Exception as e:
                    print(f"[WARN] Migration failed for uix_project_role: {str(e)}")


def get_session(engine):
    """Get database session"""
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def get_async_engine(db_url: str = None):
    """Get async database engine"""
    if db_url is None:
        from config import settings
        db_url = settings.database_url
    
    if not db_url:
        raise ValueError("DATABASE_URL is required.")
        
    # Convert postgresql:// to postgresql+asyncpg:// if necessary
    if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    return create_async_engine(db_url, echo=False)


def get_async_session_maker(engine):
    """Get async session maker"""
    return async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)


async def get_async_db():
    """FastAPI dependency for async database session"""
    engine = get_async_engine()
    async_session = get_async_session_maker(engine)
    async with async_session() as session:
        yield session

# Create global async session maker for direct usage (non-FastAPI)
async_engine_global = get_async_engine()
AsyncSessionLocal = get_async_session_maker(async_engine_global)
