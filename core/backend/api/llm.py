"""LLM model catalog API."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domains.identity.auth import Identity, resolve_identity
from infrastructure.llm.model_catalog import catalog_to_dict
from shared.database import UserSettings, get_async_db

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.get("/models")
async def get_model_catalog(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Return model catalog filtered by providers with configured API keys."""
    data = catalog_to_dict()
    result = await db.execute(
        select(UserSettings).filter(UserSettings.user_id == identity.user_id)
    )
    settings = result.scalars().first()

    configured_providers: set[str] = set()
    if settings:
        if settings.gemini_api_key:
            configured_providers.add("gemini")
        if settings.openai_api_key:
            configured_providers.add("openai")
        if settings.anthropic_api_key:
            configured_providers.add("anthropic")

    groups = [
        g for g in (data.get("groups") or [])
        if g.get("provider") in configured_providers
    ]
    all_model_ids = [
        m.get("id")
        for g in groups
        for m in (g.get("models") or [])
        if m.get("id")
    ]

    default_model = data.get("default_model")
    if default_model not in all_model_ids:
        default_model = all_model_ids[0] if all_model_ids else ""

    return {
        "default_model": default_model,
        "groups": groups,
    }
