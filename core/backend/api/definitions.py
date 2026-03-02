"""Definitions API — manage tool/skill registries.

Endpoints:
  POST /api/definitions/refresh          Refresh all definitions from core + integrations
  POST /api/definitions/refresh/core     Refresh core definitions only
  POST /api/definitions/refresh/integrations  Refresh integration definitions only
  GET  /api/definitions/tools            List all tool registry entries for the current user
  GET  /api/definitions/skills           List all skill registry entries for the current user
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_async_db, ToolRegistry, SkillRegistry
from domains.identity.auth import resolve_identity, Identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/definitions", tags=["definitions"])


# ---------------------------------------------------------------------------
# Refresh endpoints
# ---------------------------------------------------------------------------

@router.post("/refresh")
async def refresh_all_definitions(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Trigger a full refresh: re-seed core tools/skills and re-load integration definitions."""
    from domains.orchestration2.bootstrap.definition_refresh_service import refresh_all

    result = await refresh_all(identity.user_id, db)
    return {"ok": True, **result}


@router.post("/refresh/core")
async def refresh_core_definitions(
    identity: Identity = Depends(resolve_identity),
):
    """Re-seed core (static) tool and skill definitions into DB."""
    import asyncio
    from shared.database import get_engine
    from domains.orchestration2.bootstrap.definition_refresh_service import refresh_core_sync

    engine = get_engine()
    await asyncio.to_thread(refresh_core_sync, engine, identity.user_id)
    return {"ok": True, "source": "core"}


@router.post("/refresh/integrations")
async def refresh_integration_definitions(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Re-load tool and skill definitions from all active integrations."""
    from domains.orchestration2.bootstrap.definition_refresh_service import refresh_integrations

    result = await refresh_integrations(identity.user_id, db)
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# List endpoints
# ---------------------------------------------------------------------------

@router.get("/tools")
async def list_tools(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    origin_type: str | None = None,
    active_only: bool = True,
):
    """Return all tool registry entries for the current user."""
    stmt = select(ToolRegistry).where(ToolRegistry.user_id == identity.user_id)
    if active_only:
        stmt = stmt.where(ToolRegistry.is_active == True)  # noqa: E712
    if origin_type:
        stmt = stmt.where(ToolRegistry.origin_type == origin_type)
    stmt = stmt.order_by(ToolRegistry.origin_type, ToolRegistry.name)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "name": r.name,
            "description": r.description,
            "origin_type": r.origin_type,
            "origin_id": r.origin_id,
            "status": r.status,
            "is_active": r.is_active,
            "version_hash": r.version_hash,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


@router.get("/skills")
async def list_skills(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    origin_type: str | None = None,
    active_only: bool = True,
):
    """Return all skill registry entries for the current user."""
    stmt = select(SkillRegistry).where(SkillRegistry.user_id == identity.user_id)
    if active_only:
        stmt = stmt.where(SkillRegistry.is_active == True)  # noqa: E712
    if origin_type:
        stmt = stmt.where(SkillRegistry.origin_type == origin_type)
    stmt = stmt.order_by(SkillRegistry.origin_type, SkillRegistry.name)

    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        {
            "name": r.name,
            "description": r.description,
            "tools": r.tools,
            "origin_type": r.origin_type,
            "origin_id": r.origin_id,
            "status": r.status,
            "is_active": r.is_active,
            "is_builtin": r.is_builtin,
            "version_hash": r.version_hash,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]
