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


class AgentType(str, Enum):
    """Agent type for categorization"""
    SYSTEM = "SYSTEM"       # System agents (router, memory, etc.)
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


class NotificationType(str, Enum):
    """Types of user notifications"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    TIMER = "timer"


class TaskType(str, Enum):
    """Types of asynchronous tasks in the queue"""
    USER_MESSAGE = "user_message"
    AES_SYSTEM_TASK = "aes_system_task"


class ScheduledTask(Base):
    """Automated Execution System (AES) tasks (timers, recurring, etc.)"""
    __tablename__ = "scheduled_tasks"
    
    id = Column(String(36), primary_key=True)               # UUID
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    task_type = Column(String(50), nullable=False)          # e.g., "HARD_DELETE", "POST_MESSAGE", "SYSTEM_TIMER"
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
    run_id = Column(String(36), nullable=True)              # orchestration2 run tracking
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


class Notification(Base):
    """User notifications across the system"""
    __tablename__ = "notifications"

    id = Column(String(36), primary_key=True)               # UUID
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    type = Column(String(20), default="info")               # From NotificationType
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    link = Column(String(255), nullable=True)               # Optional link to related entity
    is_read = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    user = relationship("User")
    project = relationship("Project")


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
            
        from shared.encryption import decrypt_string
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
    access_token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    remote_user_id = Column(String(100), nullable=True)  # User ID in the remote service (for user mapping)
    is_active = Column(Boolean, default=True)
    last_health_check = Column(DateTime, nullable=True)
    health_status = Column(String(50), nullable=True)  # "healthy", "unreachable", "error"
    config = Column(JSON, nullable=True, default=dict) # Flexible configuration for external systems
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)
    
    @property
    def api_key(self) -> Optional[str]:
        """Automatically decrypt and return the service API key"""
        if not self.api_key_encrypted:
            return None
            
        from shared.encryption import decrypt_string
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
    project_id = Column(String(36), ForeignKey('projects.id'), nullable=True, index=True) # Dedicated project for this identity
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
    agents = relationship("ProjectAgent", back_populates="project", cascade="all, delete-orphan")
    sessions = relationship("ChatSession", back_populates="project", cascade="all, delete-orphan")
    files = relationship("UploadedFile", back_populates="project", cascade="all, delete-orphan")


class ProjectAgent(Base):
    """Project agent - contains agent configuration and prompt"""
    __tablename__ = "project_agents"

    id = Column(String(36), primary_key=True)  # UUID
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)  # Null for SYSTEM agents
    parent_agent_id = Column(String(36), ForeignKey("project_agents.id"), nullable=True)  # Hierarchy for member agents
    agent_type = Column(String(20), default="PROJECT")  # SYSTEM/PROJECT/MEMBER
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
    project = relationship("Project", back_populates="agents")
    parent = relationship("ProjectAgent", remote_side=[id], backref="children")

    from sqlalchemy import UniqueConstraint
    __table_args__ = (
        UniqueConstraint('project_id', 'role_name', name='uix_project_role'),
    )


class Skill(Base):
    """Reusable packages of instructions and domain logic"""
    __tablename__ = "skills"
    
    id = Column(String(100), primary_key=True)               # UUID or skill-id-v1
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True) # Null for Global skills
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)                  # The body of SKILL.md
    metadata_payload = Column(JSON, default=dict)           # YAML Frontmatter details
    is_active = Column(Boolean, default=True)
    is_draft = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")


class ProjectSkill(Base):
    """Many-to-many relationship between ProjectAgents and Skills"""
    __tablename__ = "project_skills"

    agent_id = Column(String(36), ForeignKey("project_agents.id"), primary_key=True)
    skill_id = Column(String(100), ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True)

    # Relationships
    agent = relationship("ProjectAgent", backref="attached_skills")
    skill = relationship("Skill")

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
    sub_messages = relationship("ChatSubMessage", back_populates="message", cascade="all, delete-orphan")


class ChatSubMessage(Base):
    """Structured sub-messages for intermediate thinking turns and tool calls"""
    __tablename__ = "chat_sub_messages"

    id = Column(String(36), primary_key=True)
    message_id = Column(String(36), ForeignKey("chat_messages.id"), nullable=False, index=True)
    turn_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=True)                  # Thought/Text
    kind = Column(String(20), nullable=True)               # 'text', 'tool_call', 'tool_result', 'reasoning'
    run_id = Column(String(36), nullable=True)             # orchestration2 run tracking
    step_id = Column(String(36), nullable=True)            # orchestration2 step tracking
    meta_payload = Column(JSON, nullable=True)              # Tool calls, usage, metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    message = relationship("ChatMessage", back_populates="sub_messages")
    tool_calls = relationship("ToolUsage", back_populates="sub_message", cascade="all, delete-orphan")


class ToolUsage(Base):
    """Structured log of tool/function execution within a message or sub-message"""
    __tablename__ = "tool_usages"

    id = Column(String(36), primary_key=True)
    message_id = Column(String(36), ForeignKey("chat_messages.id"), nullable=False, index=True)
    sub_message_id = Column(String(36), ForeignKey("chat_sub_messages.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False)             # Tool name
    call_id = Column(String(100), nullable=True)           # orchestration2 correlation ID
    args = Column(JSON, nullable=True)                     # Input args
    result = Column(Text, nullable=True)                   # Output string
    is_success = Column(Boolean, default=True)
    meta_payload = Column(JSON, nullable=True)             # Additional metadata (attachments, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    sub_message = relationship("ChatSubMessage", back_populates="tool_calls")


class ArchivedContext(Base):
    """Archived conversation contexts and summaries"""
    __tablename__ = "archived_contexts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False, index=True)
    agent_id = Column(String(36), ForeignKey("project_agents.id"), nullable=True, index=True)
    archived_at = Column(DateTime, default=datetime.utcnow)
    summary_path = Column(Text, nullable=True)
    log_path = Column(Text, nullable=True)
    token_count = Column(Integer, nullable=True)

    # Relationships
    user = relationship("User")
    project = relationship("Project")
    agent = relationship("ProjectAgent")


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
    directory = Column(String(50), nullable=True)  # 'refs', 'artifacts', or 'files'
    is_directory = Column(Boolean, default=False)
    storage_path = Column(String(512), nullable=False)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    vector_status = Column(String(50), default="PENDING")  # PENDING, COMPLETED
    kc_sync_status = Column(String(50), default="PENDING")  # PENDING, SYNCED
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    project = relationship("Project", back_populates="files")
    chunks = relationship("FileChunk", back_populates="file", cascade="all, delete-orphan")




class Note(Base):
    """Personal or project-specific notes with optional audio attachment"""
    __tablename__ = "notes"
    
    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    title = Column(String(255), nullable=True)
    content = Column(Text, nullable=True)
    audio_file_id = Column(String(36), ForeignKey("uploaded_files.id"), nullable=True)
    tags = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User")
    project = relationship("Project")
    audio_file = relationship("UploadedFile")


class OrchestrationRun(Base):
    """Persistent storage for orchestration2 RunRecord"""
    __tablename__ = "orchestration_runs"

    run_id = Column(String(36), primary_key=True)
    status = Column(String(30), nullable=False, index=True)
    agent_name = Column(String(200), nullable=False)
    graph_name = Column(String(200), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    session_id = Column(String(36), ForeignKey("chat_sessions.id"), nullable=True, index=True)
    current_step_id = Column(String(100), nullable=True)
    context_json = Column(JSON, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    pending_approval_ids = Column(JSON, default=list)
    pending_delegation_ids = Column(JSON, default=list)
    history_json = Column(JSON, nullable=True)
    input_message_json = Column(JSON, nullable=True)
    output_message_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project")
    user = relationship("User")
    session = relationship("ChatSession")


class OrchestrationPendingAction(Base):
    """Persistent storage for orchestration2 PendingAction (approval requests)"""
    __tablename__ = "orchestration_pending_actions"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("orchestration_runs.run_id"), nullable=False, index=True)
    step_id = Column(String(100), nullable=True)
    action_type = Column(String(50), nullable=True)
    action_name = Column(String(200), nullable=True)
    status = Column(String(30), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    run = relationship("OrchestrationRun")


class OrchestrationDelegation(Base):
    """Persistent storage for orchestration2 DelegationRequest/Result"""
    __tablename__ = "orchestration_delegations"

    id = Column(String(36), primary_key=True)
    parent_run_id = Column(String(36), ForeignKey("orchestration_runs.run_id"), nullable=False, index=True)
    child_agent_name = Column(String(200), nullable=True)
    child_run_id = Column(String(36), nullable=True)
    task = Column(Text, nullable=True)
    status = Column(String(30), default="pending")
    output_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    timeout_sec = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    parent_run = relationship("OrchestrationRun")


class OrchestrationEvent(Base):
    """Event log for orchestration2 runs"""
    __tablename__ = "orchestration_events"

    id = Column(String(36), primary_key=True)
    run_id = Column(String(36), ForeignKey("orchestration_runs.run_id"), nullable=False, index=True)
    step_id = Column(String(100), nullable=True)
    event_type = Column(String(50), nullable=False)
    source = Column(String(50), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    run = relationship("OrchestrationRun")


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


# Global engine instances (Singletons for connection pooling)
_engine = None
_async_engine = None

def get_engine(db_url: str = None):
    """Get database engine - uses global singleton for connection pooling"""
    global _engine
    
    if _engine is not None:
        return _engine

    if db_url is None:
        from app.config import settings
        
        if not settings.database_url:
            raise ValueError(
                "DATABASE_URL is required. Set it in .env file.\n"
                "Example: DATABASE_URL=postgresql://user:pass@localhost:5432/atmos"
            )
        db_url = settings.database_url
    
    # Convert async URL to sync for regular sqlalchemy engine
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://", 1)

    _engine = create_engine(db_url, echo=False, pool_pre_ping=True)
    return _engine


def init_database(database_url: str = None):
    """Initialize database tables and run migrations"""
    # 1. Discover integration-specific models (Pattern A)
    from va_sdk.discovery import discover_integration_models
    discover_integration_models()
    
    # 2. Setup engine and create core tables
    engine = get_engine(database_url)

    # Pre-migration: drop legacy tables that conflict with renamed tables
    from sqlalchemy import text, inspect
    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    if 'nodes' in existing_tables:
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS node_skills CASCADE"))
            conn.execute(text("DROP TABLE IF EXISTS nodes CASCADE"))
            print("[INFO] Pre-migration: Dropped legacy 'nodes' and 'node_skills' tables")

    Base.metadata.create_all(engine)
    
    # 3. Run schema migrations for existing tables
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
    
    # Migration: Add config column to service_registry if missing
    if 'service_registry' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('service_registry')]
        if 'config' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE service_registry ADD COLUMN config JSON"))
                conn.commit()
                print("✅ Migration: Added config column to service_registry")
    
    # Migration: Add directory and is_directory columns to uploaded_files if missing
    if 'uploaded_files' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('uploaded_files')]
        if 'directory' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE uploaded_files ADD COLUMN directory VARCHAR(50)"))
                # Default existing ones to 'refs' if they look like they belong there
                conn.execute(text("UPDATE uploaded_files SET directory = 'refs' WHERE directory IS NULL"))
                conn.commit()
                print("✅ Migration: Added directory column to uploaded_files")
        
        if 'is_directory' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE uploaded_files ADD COLUMN is_directory BOOLEAN DEFAULT FALSE"))
                conn.commit()
                print("✅ Migration: Added is_directory column to uploaded_files")

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

    # Migration: Add description to project_agents if missing
    if 'project_agents' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('project_agents')]
        if 'description' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE project_agents ADD COLUMN description VARCHAR(500)"))
                conn.commit()
                print("[INFO] Migration: Added description column to project_agents")

    # Migration: Add meta_payload to project_agents if missing
    if 'project_agents' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('project_agents')]
        if 'meta_payload' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE project_agents ADD COLUMN meta_payload JSON"))
                conn.commit()
                print("[INFO] Migration: Added meta_payload column to project_agents")
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
    
    # Migration: Add project_id to external_identities if missing
    if 'external_identities' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('external_identities')]
        if 'project_id' not in columns:
            with engine.connect() as conn:
                try:
                    conn.execute(text("ALTER TABLE external_identities ADD COLUMN project_id VARCHAR(36) REFERENCES projects(id)"))
                    conn.commit()
                    print("[INFO] Migration: Added project_id column to external_identities")
                except Exception as e:
                    print(f"[WARN] Migration failed for external_identities.project_id: {str(e)}")
    # Migration: Add unique constraint uix_project_role to project_agents if missing
    if 'project_agents' in inspector.get_table_names():
        constraints = inspector.get_unique_constraints('project_agents')
        if not any(c['name'] == 'uix_project_role' for c in constraints):
            with engine.connect() as conn:
                try:
                    conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uix_project_role ON project_agents (COALESCE(project_id, 'SYSTEM'), role_name)"))
                    conn.commit()
                    print("[INFO] Migration: Added unique index uix_project_role to project_agents")
                except Exception as e:
                    print(f"[WARN] Migration failed for uix_project_role: {str(e)}")

    # Migration: Initialize general_settings in user_settings if null
    if 'user_settings' in inspector.get_table_names():
        with engine.connect() as conn:
            try:
                # Initialize rows where general_settings is null
                conn.execute(text(
                    "UPDATE user_settings SET general_settings = '{\"language\": \"en\", \"timezone\": \"UTC\", \"location\": \"\"}' "
                    "WHERE general_settings IS NULL OR general_settings::text = '{}'"
                ))
                conn.commit()
                print("[INFO] Migration: Initialized general_settings in user_settings")
            except Exception as e:
                print(f"[WARN] Migration failed for user_settings initialization: {str(e)}")

    # Migration: Increase Skill ID column lengths
    if 'skills' in inspector.get_table_names():
        columns = {col['name']: col for col in inspector.get_columns('skills')}
        # Check if the 'id' column exists and if it's currently shorter than 100
        # The type object from inspector might vary, but length is a common attribute for String/VARCHAR
        try:
            current_length = columns['id']['type'].length
            if current_length and current_length < 100:
                with engine.connect() as conn:
                    conn.execute(text("ALTER TABLE skills ALTER COLUMN id TYPE VARCHAR(100)"))
                    if 'project_skills' in inspector.get_table_names():
                        conn.execute(text("ALTER TABLE project_skills ALTER COLUMN skill_id TYPE VARCHAR(100)"))
                    conn.commit()
                    print("✅ Migration: Increased Skill ID column lengths to 100")
        except (AttributeError, KeyError) as e:
            # Fallback if length attribute is missing or structure is different
            print(f"[DEBUG] Migration check for Skill ID skipped or failed: {str(e)}")

    # Migration: Update project_skills foreign key to use CASCADE delete
    if 'project_skills' in inspector.get_table_names():
        with engine.connect() as conn:
            try:
                conn.execute(text("""
                    ALTER TABLE project_skills
                    DROP CONSTRAINT IF EXISTS project_skills_skill_id_fkey,
                    ADD CONSTRAINT project_skills_skill_id_fkey
                    FOREIGN KEY (skill_id) REFERENCES skills(id) ON DELETE CASCADE
                """))
                conn.commit()
                print("✅ Migration: Updated project_skills foreign key to CASCADE delete")
            except Exception as e:
                print(f"[WARN] Migration failed for project_skills cascade: {str(e)}")
            
    # Migration: Add tags column to notes if missing
    if 'notes' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('notes')]
        if 'tags' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE notes ADD COLUMN tags JSON DEFAULT '[]'"))
                conn.commit()
                print("✅ Migration: Added tags column to notes")

    # Migration: Add sub_message_id to tool_usages if missing
    if 'tool_usages' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('tool_usages')]
        if 'sub_message_id' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tool_usages ADD COLUMN sub_message_id VARCHAR(36) REFERENCES chat_sub_messages(id)"))
                conn.commit()
                print("✅ Migration: Added sub_message_id column to tool_usages")
        
        if 'arguments' in columns and 'args' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tool_usages RENAME COLUMN arguments TO args"))
                conn.commit()
                print("✅ Migration: Renamed tool_usages.arguments to tool_usages.args")
        elif 'args' not in columns:
             # Just in case it's newly created but without args? Unlikely but safer.
             with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tool_usages ADD COLUMN args JSON"))
                conn.commit()
                print("✅ Migration: Added args column to tool_usages")

        if 'meta_payload' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tool_usages ADD COLUMN meta_payload JSON"))
                conn.commit()
                print("✅ Migration: Added meta_payload column to tool_usages")

        if 'call_id' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE tool_usages ADD COLUMN call_id VARCHAR(100)"))
                conn.commit()
                print("✅ Migration: Added call_id column to tool_usages")

    # Migration: Add orchestration2 columns to chat_sub_messages
    if 'chat_sub_messages' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('chat_sub_messages')]
        if 'kind' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE chat_sub_messages ADD COLUMN kind VARCHAR(20)"))
                conn.commit()
                print("✅ Migration: Added kind column to chat_sub_messages")
        if 'run_id' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE chat_sub_messages ADD COLUMN run_id VARCHAR(36)"))
                conn.commit()
                print("✅ Migration: Added run_id column to chat_sub_messages")
        if 'step_id' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE chat_sub_messages ADD COLUMN step_id VARCHAR(36)"))
                conn.commit()
                print("✅ Migration: Added step_id column to chat_sub_messages")

    # Migration: Add new columns to orchestration_runs for state persistence
    if 'orchestration_runs' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('orchestration_runs')]
        new_cols = {
            'pending_approval_ids': "JSON DEFAULT '[]'",
            'pending_delegation_ids': "JSON DEFAULT '[]'",
            'history_json': "JSON",
            'input_message_json': "JSON",
            'output_message_json': "JSON",
        }
        for col_name, col_type in new_cols.items():
            if col_name not in columns:
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE orchestration_runs ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
                    print(f"✅ Migration: Added {col_name} column to orchestration_runs")

    # Migration: Add run_id to approval_requests for orchestration2 tracking
    if 'approval_requests' in inspector.get_table_names():
        columns = [col['name'] for col in inspector.get_columns('approval_requests')]
        if 'run_id' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE approval_requests ADD COLUMN run_id VARCHAR(36)"))
                conn.commit()
                print("✅ Migration: Added run_id column to approval_requests")


# Global sync session maker
_SessionLocal = None

def get_session(engine=None):
    """Get database session - uses global singleton sessionmaker"""
    global _SessionLocal
    if _SessionLocal is not None and engine is None:
        return _SessionLocal()
        
    if engine is None:
        engine = get_engine()
        
    _SessionLocal = sessionmaker(bind=engine)
    return _SessionLocal()


def get_async_engine(db_url: str = None):
    """Get async database engine - uses global singleton for connection pooling"""
    global _async_engine
    
    if _async_engine is not None:
        return _async_engine

    if db_url is None:
        from app.config import settings
        db_url = settings.database_url
    
    if not db_url:
        raise ValueError("DATABASE_URL is required.")
        
    # Convert postgresql:// to postgresql+asyncpg:// if necessary
    if db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
    _async_engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    return _async_engine


# Global async session maker
_AsyncSessionLocal = None

def get_async_session_maker(engine=None):
    """Get async session maker"""
    global _AsyncSessionLocal
    if _AsyncSessionLocal is not None and engine is None:
        return _AsyncSessionLocal
        
    if engine is None:
        engine = get_async_engine()
        
    _AsyncSessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    return _AsyncSessionLocal


async def get_async_db():
    """FastAPI dependency for async database session"""
    async_session = get_async_session_maker()
    async with async_session() as session:
        yield session

# Initialize global AsyncSessionLocal for legacy usage in worker
AsyncSessionLocal = get_async_session_maker()
