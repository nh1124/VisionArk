from sqlalchemy import Column, String, JSON, DateTime
from datetime import datetime
from shared.database import Base

class LBSTaskExtension(Base):
    """Sidecar table for LBS tasks to store VisionArk-specific metadata"""
    __tablename__ = "integr_lbs_task_extensions"

    lbs_task_id = Column(String(36), primary_key=True)       # The UUID from LBS microservice
    meta_payload = Column(JSON, default=dict)                # { "steps": [...], "is_my_day": true, ... }
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
