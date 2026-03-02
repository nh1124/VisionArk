"""Definitions API — manage tool/skill registries and user modules.

Module CRUD (primary interface for user-defined tools/skills):
  GET    /api/definitions/modules            List all uploaded modules
  POST   /api/definitions/modules            Upload a new module (directory)
  GET    /api/definitions/modules/{name}     Get module details + file contents
  PUT    /api/definitions/modules/{name}     Replace module files (re-register)
  DELETE /api/definitions/modules/{name}     Delete module and its tools/skills

Individual is_active toggles:
  PATCH  /api/definitions/tools/{name}       Toggle a tool on/off
  PATCH  /api/definitions/skills/{name}      Toggle a skill on/off

Registry list (read-only, all origins):
  GET    /api/definitions/tools              List tools (all origins)
  GET    /api/definitions/skills             List skills (all origins)

Refresh (core + integration definitions):
  POST   /api/definitions/refresh            Refresh all (core + integrations)
  POST   /api/definitions/refresh/core       Refresh core only
  POST   /api/definitions/refresh/integrations  Refresh integrations only
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_async_db, ToolRegistry, SkillRegistry
from domains.identity.auth import resolve_identity, Identity

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/definitions", tags=["definitions"])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class ModuleUploadRequest(BaseModel):
    module_name: str
    files: dict[str, str]  # filename -> Python source


class ModuleUpdateRequest(BaseModel):
    files: dict[str, str]


class ToolPatchRequest(BaseModel):
    is_active: bool | None = None


class SkillPatchRequest(BaseModel):
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# Module CRUD
# ---------------------------------------------------------------------------


@router.get("/modules")
async def list_modules(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """List all uploaded modules with their tools and skills."""
    from domains.orchestration2.bootstrap.definition_import_service import list_modules as _list
    return await _list(identity.user_id, db)


@router.post("/modules", status_code=201)
async def create_module(
    body: ModuleUploadRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Upload a new module directory. Fails if a module with this name already exists.

    Body: { module_name: str, files: { "filename.py": "source code" } }
    __init__.py is required. Other .py files are optional.
    """
    from domains.orchestration2.bootstrap.definition_import_service import import_user_module

    result = await import_user_module(
        user_id=identity.user_id,
        module_name=body.module_name,
        files=body.files,
        db=db,
        replace=False,
    )
    if not result.ok:
        raise HTTPException(
            status_code=409 if "already exists" in (result.error or "") else 422,
            detail=result.error,
        )
    return {
        "ok": True,
        "module_name": body.module_name,
        "tools": result.tool_names,
        "skills": result.skill_names,
    }


@router.get("/modules/{name}")
async def get_module(
    name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Get module details including file contents and registered tools/skills."""
    from domains.orchestration2.bootstrap.definition_import_service import (
        list_modules as _list,
        get_module_files,
    )

    all_modules = await _list(identity.user_id, db)
    module = next((m for m in all_modules if m["module_name"] == name), None)
    if module is None:
        raise HTTPException(status_code=404, detail=f"Module '{name}' not found")

    files = get_module_files(identity.user_id, name)
    return {**module, "files": files}


@router.put("/modules/{name}")
async def update_module(
    name: str,
    body: ModuleUpdateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Replace a module's files and re-register its tools/skills.

    The module must already exist. All previous tools/skills for this module
    are removed and re-created from the new code.
    """
    from domains.orchestration2.bootstrap.definition_import_service import import_user_module

    result = await import_user_module(
        user_id=identity.user_id,
        module_name=name,
        files=body.files,
        db=db,
        replace=True,
    )
    if not result.ok:
        raise HTTPException(status_code=422, detail=result.error)
    return {
        "ok": True,
        "module_name": name,
        "tools": result.tool_names,
        "skills": result.skill_names,
    }


@router.delete("/modules/{name}")
async def delete_module(
    name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete an uploaded module and all its associated tools and skills."""
    from domains.orchestration2.bootstrap.definition_import_service import delete_user_module

    try:
        await delete_user_module(identity.user_id, name, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "deleted_module": name}


# ---------------------------------------------------------------------------
# Individual is_active toggles
# ---------------------------------------------------------------------------


@router.patch("/tools/{name}")
async def patch_tool(
    name: str,
    body: ToolPatchRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Toggle a tool on/off (is_active). Works for any origin_type."""
    result = await db.execute(
        select(ToolRegistry).where(
            ToolRegistry.user_id == identity.user_id,
            ToolRegistry.name == name,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Tool '{name}' not found")

    if body.is_active is not None:
        row.is_active = body.is_active

    from datetime import datetime
    row.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "name": name, "is_active": row.is_active}


@router.patch("/skills/{name}")
async def patch_skill(
    name: str,
    body: SkillPatchRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Toggle a skill on/off (is_active). Works for any origin_type."""
    result = await db.execute(
        select(SkillRegistry).where(
            SkillRegistry.user_id == identity.user_id,
            SkillRegistry.name == name,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    if body.is_active is not None:
        row.is_active = body.is_active

    from datetime import datetime
    row.updated_at = datetime.utcnow()
    await db.commit()
    return {"ok": True, "name": name, "is_active": row.is_active}


# ---------------------------------------------------------------------------
# Registry list (read-only, all origins)
# ---------------------------------------------------------------------------


@router.get("/tools")
async def list_tools(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
    origin_type: str | None = None,
    active_only: bool = True,
):
    """Return tool registry entries for the current user."""
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
    """Return skill registry entries for the current user."""
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
            "is_active": r.is_active,
            "is_builtin": r.is_builtin,
            "version_hash": r.version_hash,
            "updated_at": r.updated_at,
        }
        for r in rows
    ]


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
