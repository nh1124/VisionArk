"""Shared service helper functions for accessing external services."""

from typing import Optional, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


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
