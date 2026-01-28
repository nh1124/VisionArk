import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from models.database import Base

class LineLinkingToken(Base):
    """
    Temporary tokens for linking LINE user IDs to VisionArk accounts.
    Migrated from ServiceRegistry.config to a dedicated integration table.
    """
    __tablename__ = "integr_line_linking_tokens"
    
    token = Column(String(100), primary_key=True)
    line_user_id = Column(String(100), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
