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


class SystemConfig(Base):
    """Global LBS configuration (ALPHA, BETA, CAP, SWITCH_COST)"""
    __tablename__ = "system_config"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    description = Column(Text)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Task(Base):
    """Master task definitions with complex recurrence rules"""
    __tablename__ = "tasks"
    
    # Primary identification
    task_id = Column(String, primary_key=True)  # T-UUID
    task_name = Column(String, nullable=False)
    context = Column(String, nullable=False)  # Spoke name (project tag)
    base_load_score = Column(Float, nullable=False)  # 0.0 - 10.0
    active = Column(Boolean, default=True)
    
    # Rule definition
    rule_type = Column(String, nullable=False)  # ONCE, WEEKLY, EVERY_N, etc.
    due_date = Column(Date, nullable=True)  # For ONCE tasks
    
    # Recurrence details
    mon = Column(Boolean, default=False)
    tue = Column(Boolean, default=False)
    wed = Column(Boolean, default=False)
    thu = Column(Boolean, default=False)
    fri = Column(Boolean, default=False)
    sat = Column(Boolean, default=False)
    sun = Column(Boolean, default=False)
    
    interval_days = Column(Integer, nullable=True)  # For EVERY_N_DAYS
    anchor_date = Column(Date, nullable=True)  # Recurrence start reference
    month_day = Column(Integer, nullable=True)  # 1-31 for MONTHLY_DAY
    nth_in_month = Column(Integer, nullable=True)  # 1-5 or -1 for last
    weekday_mon1 = Column(Integer, nullable=True)  # 1=Mon...7=Sun
    
    # Validity period
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    
    # Metadata
    notes = Column(Text)
    external_sync_id = Column(String, nullable=True)  # Microsoft ToDo ID
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    exceptions = relationship("TaskException", back_populates="task", cascade="all, delete-orphan")
    daily_caches = relationship("LBSDailyCache", back_populates="task", cascade="all, delete-orphan")


class TaskException(Base):
    """Exceptions to task recurrence rules (holidays, overrides)"""
    __tablename__ = "task_exceptions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, ForeignKey("tasks.task_id"), nullable=False)
    target_date = Column(Date, nullable=False)
    exception_type = Column(String, nullable=False)  # SKIP, OVERRIDE_LOAD, FORCE_DO
    override_load_value = Column(Float, nullable=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    task = relationship("Task", back_populates="exceptions")


class LBSDailyCache(Base):
    """Materialized daily task view (expanded from rules + exceptions)"""
    __tablename__ = "lbs_daily_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    target_date = Column(Date, nullable=False, index=True)
    task_id = Column(String, ForeignKey("tasks.task_id"), nullable=False)
    calculated_load = Column(Float, nullable=False)  # After exceptions & coefficients
    rule_type_snapshot = Column(String)
    status = Column(String, default="planned")  # planned, completed, skipped
    is_overflow = Column(Boolean, default=False)  # CAP exceeded flag
    generated_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    task = relationship("Task", back_populates="daily_caches")


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


# Database setup utilities
def get_engine(db_url: str = None):
    """Get database engine with automatic path detection"""
    if db_url is None:
        # Use centralized path management
        from utils.paths import HUB_DATA_DIR
        
        db_dir = HUB_DATA_DIR
        db_dir.mkdir(parents=True, exist_ok=True)
        
        db_path = db_dir / "lbs_master.db"
        db_url = f"sqlite:///{db_path}"
    
    return create_engine(db_url, echo=False)


def init_database(database_url: str = None):
    """Initialize database with default configuration"""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    
    # Create session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    # Insert default system config if not exists
    defaults = [
        SystemConfig(key="ALPHA", value="0.1", description="Urgency multiplier coefficient"),
        SystemConfig(key="BETA", value="1.2", description="Task count penalty exponent"),
        SystemConfig(key="CAP", value="8.0", description="Daily capacity limit"),
        SystemConfig(key="SWITCH_COST", value="0.5", description="Context switch penalty per additional context"),
    ]
    
    for config in defaults:
        existing = session.query(SystemConfig).filter_by(key=config.key).first()
        if not existing:
            session.add(config)
    
    session.commit()
    session.close()
    
    return engine


def get_session(engine):
    """Get database session"""
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
