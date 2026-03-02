"""Definitions API — manage tool/skill registries and user modules.

Module CRUD (primary interface for user-defined tools/skills):
  GET    /api/definitions/modules            List all uploaded modules
  POST   /api/definitions/modules            Upload a new module (directory)
  GET    /api/definitions/modules/{name}     Get module details + file contents
  PUT    /api/definitions/modules/{name}     Replace module files (re-register)
  DELETE /api/definitions/modules/{name}     Delete module and its tools/skills

Skill Pack CRUD:
  GET    /api/definitions/skill-packs              List all packs
  POST   /api/definitions/skill-packs              Upload new pack (201)
  GET    /api/definitions/skill-packs/{name}       Get pack details + raw content
  PUT    /api/definitions/skill-packs/{name}       Replace pack content
  DELETE /api/definitions/skill-packs/{name}       Delete pack + its skills

MCP Server CRUD:
  GET    /api/definitions/mcp/servers                  List all servers
  POST   /api/definitions/mcp/servers                  Register server (201)
  GET    /api/definitions/mcp/servers/{name}           Get server details
  PUT    /api/definitions/mcp/servers/{name}           Update server config
  DELETE /api/definitions/mcp/servers/{name}           Delete server + its tools
  POST   /api/definitions/mcp/servers/{name}/sync      Re-sync tools from server

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

from shared.database import get_async_db, ToolRegistry, SkillRegistry, MCPServerConfig
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


class SkillPackUploadRequest(BaseModel):
    pack_name: str
    filename: str
    content: str


class SkillPackUpdateRequest(BaseModel):
    filename: str
    content: str


class MCPServerCreateRequest(BaseModel):
    name: str
    display_name: str | None = None
    url: str
    headers: dict = {}


class MCPServerUpdateRequest(BaseModel):
    display_name: str | None = None
    url: str | None = None
    headers: dict | None = None
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


# ---------------------------------------------------------------------------
# Skill Pack CRUD
# ---------------------------------------------------------------------------


@router.get("/skill-packs")
async def list_skill_packs(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """List all skill packs for the current user."""
    from domains.orchestration2.integrations.skill_pack_import_service import list_skill_packs as _list
    return await _list(identity.user_id, db)


@router.post("/skill-packs", status_code=201)
async def create_skill_pack(
    body: SkillPackUploadRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Upload a new skill pack (YAML or Markdown). Fails if pack_name already exists."""
    from domains.orchestration2.integrations.skill_pack_import_service import import_skill_pack

    result = await import_skill_pack(
        user_id=identity.user_id,
        pack_name=body.pack_name,
        content=body.content,
        filename=body.filename,
        db=db,
        replace=False,
    )
    if not result.ok:
        raise HTTPException(
            status_code=409 if "already exists" in (result.error or "") else 422,
            detail=result.error,
        )
    return {"ok": True, "pack_name": body.pack_name, "skills": result.skill_names}


@router.get("/skill-packs/{name}")
async def get_skill_pack(
    name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Get skill pack details (skills list) and raw file content."""
    from domains.orchestration2.integrations.skill_pack_import_service import (
        list_skill_packs as _list,
        get_skill_pack_content,
    )

    all_packs = await _list(identity.user_id, db)
    pack = next((p for p in all_packs if p["pack_name"] == name), None)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"Skill pack '{name}' not found")

    content = await get_skill_pack_content(identity.user_id, name)
    return {**pack, "content": content}


@router.put("/skill-packs/{name}")
async def update_skill_pack(
    name: str,
    body: SkillPackUpdateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Replace a skill pack's content and re-register its skills."""
    from domains.orchestration2.integrations.skill_pack_import_service import import_skill_pack

    result = await import_skill_pack(
        user_id=identity.user_id,
        pack_name=name,
        content=body.content,
        filename=body.filename,
        db=db,
        replace=True,
    )
    if not result.ok:
        raise HTTPException(status_code=422, detail=result.error)
    return {"ok": True, "pack_name": name, "skills": result.skill_names}


@router.delete("/skill-packs/{name}")
async def delete_skill_pack(
    name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete a skill pack and all its associated skills."""
    from domains.orchestration2.integrations.skill_pack_import_service import delete_skill_pack as _delete

    try:
        await _delete(identity.user_id, name, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "deleted_pack": name}


# ---------------------------------------------------------------------------
# MCP Server CRUD
# ---------------------------------------------------------------------------


@router.get("/mcp/servers")
async def list_mcp_servers(
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """List all registered MCP servers with tool counts."""
    from domains.orchestration2.integrations.mcp_import_service import list_mcp_servers as _list
    return await _list(identity.user_id, db)


@router.post("/mcp/servers", status_code=201)
async def create_mcp_server(
    body: MCPServerCreateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Register a new MCP server. Does not auto-sync; call /sync after creation."""
    import uuid as _uuid
    from datetime import datetime

    # Check for name conflict
    result = await db.execute(
        select(MCPServerConfig).where(
            MCPServerConfig.user_id == identity.user_id,
            MCPServerConfig.name == body.name,
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"MCP server '{body.name}' already exists")

    now = datetime.utcnow()
    server = MCPServerConfig(
        id=str(_uuid.uuid4()),
        user_id=identity.user_id,
        name=body.name,
        display_name=body.display_name,
        url=body.url,
        headers=body.headers,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(server)
    await db.commit()
    return {"ok": True, "name": body.name}


@router.get("/mcp/servers/{name}")
async def get_mcp_server(
    name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Get MCP server config details and tool list."""
    from domains.orchestration2.integrations.mcp_import_service import list_mcp_servers as _list
    from sqlalchemy import text

    all_servers = await _list(identity.user_id, db)
    server = next((s for s in all_servers if s["name"] == name), None)
    if server is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    # Fetch tools for this server
    tool_rows = await db.execute(
        text("""
            SELECT name, description, is_active, updated_at
            FROM tool_registry
            WHERE user_id = :user_id AND origin_type = 'mcp' AND origin_id = :name
            ORDER BY name
        """),
        {"user_id": identity.user_id, "name": name},
    )
    tools = [
        {"name": r.name, "description": r.description, "is_active": r.is_active}
        for r in tool_rows.fetchall()
    ]
    return {**server, "tools": tools}


@router.put("/mcp/servers/{name}")
async def update_mcp_server(
    name: str,
    body: MCPServerUpdateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Update MCP server config (URL, headers, display_name, is_active)."""
    from datetime import datetime

    result = await db.execute(
        select(MCPServerConfig).where(
            MCPServerConfig.user_id == identity.user_id,
            MCPServerConfig.name == name,
        )
    )
    server = result.scalar_one_or_none()
    if server is None:
        raise HTTPException(status_code=404, detail=f"MCP server '{name}' not found")

    if body.display_name is not None:
        server.display_name = body.display_name
    if body.url is not None:
        server.url = body.url
    if body.headers is not None:
        server.headers = body.headers
    if body.is_active is not None:
        server.is_active = body.is_active
    server.updated_at = datetime.utcnow()

    await db.commit()
    return {"ok": True, "name": name}


@router.delete("/mcp/servers/{name}")
async def delete_mcp_server(
    name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Delete an MCP server and all its synced tools."""
    from domains.orchestration2.integrations.mcp_import_service import delete_mcp_server as _delete

    try:
        await _delete(identity.user_id, name, db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "deleted_server": name}


@router.post("/mcp/servers/{name}/sync")
async def sync_mcp_server(
    name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    """Connect to an MCP server and sync its tool list into tool_registry."""
    from domains.orchestration2.integrations.mcp_import_service import sync_mcp_server as _sync

    result = await _sync(identity.user_id, name, db)
    if not result.ok:
        raise HTTPException(status_code=502, detail=result.error)
    return {"ok": True, "server_name": name, "tools": result.tool_names}
