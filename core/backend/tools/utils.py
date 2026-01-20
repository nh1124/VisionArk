import os
import uuid
from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.database import Node, ServiceRegistry, UserSettings
from services.lbs_client import LBSClient
from services.knowledge_core_service import KnowledgeCoreService
from utils.paths import get_project_dir

async def get_lbs_client(user_id: str, session: AsyncSession) -> LBSClient:
    from utils.encryption import decrypt_string
    lbs_api_key = None
    lbs_url = None
    res = await session.execute(select(ServiceRegistry).filter(ServiceRegistry.user_id==user_id, ServiceRegistry.service_name=="lbs"))
    service = res.scalars().first()
    if service:
        lbs_url = service.base_url
        if service.api_key_encrypted:
            try: lbs_api_key = decrypt_string(service.api_key_encrypted)
            except: pass
    return LBSClient(base_url=lbs_url, api_key=lbs_api_key)

def get_kc_service(user_id: str, session: AsyncSession) -> KnowledgeCoreService:
    return KnowledgeCoreService(session, user_id)

async def get_project_display_name_from_id(user_id: str, project_id: str, session: AsyncSession) -> str:
    """Get display name for a project by its ID."""
    if not project_id or project_id == 'root': return 'Hub'
    try:
        uuid.UUID(project_id, version=4)
        if session:
            from models.database import Project
            res = await session.execute(select(Project.name).filter(Project.id==project_id, Project.user_id==user_id))
            name = res.scalar()
            if name: return name
    except: pass
    return project_id

async def resolve_project_artifacts_dir(user_id: str, project_id: str, session: AsyncSession = None) -> Path:
    # Use project_id directly for directory resolution
    d = get_project_dir(user_id, project_id) / "artifacts"
    d.mkdir(parents=True, exist_ok=True)
    return d

async def get_file_service(user_id: str, session: AsyncSession):
    from services.file_service import FileService
    res = await session.execute(select(UserSettings).filter(UserSettings.user_id==user_id))
    settings = res.scalars().first()
    key = settings.gemini_api_key if settings else None
    return FileService(session, user_id, api_key=key)

async def get_gemini_client(user_id: str, session: AsyncSession):
    from google.genai import Client
    res = await session.execute(select(UserSettings).filter(UserSettings.user_id==user_id))
    settings = res.scalars().first()
    if not settings: raise ValueError("User settings not found")
    key = settings.gemini_api_key
    if not key: raise ValueError("No Gemini API Key")
    return Client(api_key=key, http_options={'api_version': 'v1alpha'})
