import os
import uuid
from pathlib import Path
from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared.paths import get_project_dir

async def get_user_api_key(user_id: str, session: AsyncSession) -> Optional[str]:
    """Helper to fetch Gemini API key for a user from the database."""
    if not user_id or not session:
        return None
    try:
        from shared.database import UserSettings
        res = await session.execute(select(UserSettings).filter(UserSettings.user_id == user_id))
        settings = res.scalars().first()
        return settings.gemini_api_key if settings else None
    except Exception as e:
        print(f"Error fetching API key for user {user_id}: {e}")
        return None

def get_kc_service(user_id: str, session: AsyncSession) -> Any:
    """Lazy import and return KnowledgeCoreService."""
    from integrations.knowledge_core.service import KnowledgeCoreService
    return KnowledgeCoreService(session, user_id)

async def get_lbs_client(user_id: str, session: AsyncSession) -> Any:
    """Lazy import and return LBS client."""
    from integrations.lbs.client import get_lbs_client
    return await get_lbs_client(user_id, session)

async def get_project_display_name_from_id(user_id: str, project_id: str, session: AsyncSession) -> str:
    """Get display name for a project by its ID."""
    if not project_id or project_id == 'root': return 'Hub'
    try:
        uuid.UUID(project_id, version=4)
        if session:
            from shared.database import Project
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
    from domains.workspace.file_service import FileService
    from shared.database import UserSettings
    res = await session.execute(select(UserSettings).filter(UserSettings.user_id==user_id))
    settings = res.scalars().first()
    key = settings.gemini_api_key if settings else None
    return FileService(session, user_id, api_key=key)

async def get_gemini_client(user_id: str, session: AsyncSession):
    from google.genai import Client
    from shared.database import UserSettings
    res = await session.execute(select(UserSettings).filter(UserSettings.user_id==user_id))
    settings = res.scalars().first()
    if not settings: raise ValueError("User settings not found")
    key = settings.gemini_api_key
    if not key: raise ValueError("No Gemini API Key")
    return Client(api_key=key, http_options={'api_version': 'v1alpha'})
